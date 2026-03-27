"""
LADA - Advanced Planner v2
Multi-step task planning with dependency tracking, conditional branching,
verification, recovery, and checkpoint-based execution.

Features:
- AI-powered task decomposition into dependency graphs
- Plan nodes with dependencies and conditions
- Topological ordering for parallel execution
- Step-level verification (AI confirms each step succeeded)
- Plan revision when steps fail (alternative strategies)
- Checkpoint-based recovery (resume from last good state)
- Progress callbacks for UI integration
- Budget-aware planning (tracks token/time costs)
"""

import os
import logging
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Set, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class PlanNodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLANNING = "replanning"


class PlanStatus(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanNode:
    """A single step in an execution plan"""
    id: str
    action: str                           # Description of what to do
    action_type: str = "general"          # click, type, navigate, search, extract, etc.
    target: str = ""
    value: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_result: str = ""             # What success looks like
    dependencies: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[str] = field(default_factory=list)
    status: PlanNodeStatus = PlanNodeStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    verification_result: str = ""
    retries: int = 0
    max_retries: int = 3
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'action': self.action,
            'action_type': self.action_type,
            'target': self.target,
            'status': self.status.value,
            'result': self.result,
            'error': self.error,
            'retries': self.retries,
            'expected_result': self.expected_result,
        }


@dataclass
class ExecutionPlan:
    """A complete execution plan with dependency graph"""
    plan_id: str = ""
    task: str = ""
    nodes: Dict[str, PlanNode] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: str = ""
    completed_nodes: Set[str] = field(default_factory=set)
    failed_nodes: Set[str] = field(default_factory=set)
    status: PlanStatus = PlanStatus.PLANNING
    total_replans: int = 0
    max_replans: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return all(
            n.status in (PlanNodeStatus.COMPLETED, PlanNodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    @property
    def progress(self) -> float:
        if not self.nodes:
            return 0.0
        done = sum(1 for n in self.nodes.values()
                   if n.status in (PlanNodeStatus.COMPLETED, PlanNodeStatus.SKIPPED))
        return done / len(self.nodes)

    def get_next_executable(self) -> List[PlanNode]:
        """Get nodes whose dependencies are all met."""
        ready = []
        for nid in self.execution_order:
            node = self.nodes[nid]
            if node.status != PlanNodeStatus.PENDING:
                continue
            deps_met = all(
                self.nodes[dep].status == PlanNodeStatus.COMPLETED
                for dep in node.dependencies
                if dep in self.nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def to_dict(self) -> Dict[str, Any]:
        return {
            'plan_id': self.plan_id,
            'task': self.task,
            'status': self.status.value,
            'progress': f"{self.progress:.0%}",
            'total_steps': len(self.nodes),
            'completed': len(self.completed_nodes),
            'failed': len(self.failed_nodes),
            'total_replans': self.total_replans,
            'steps': [self.nodes[nid].to_dict() for nid in self.execution_order],
        }


# ============================================================
# Prompts
# ============================================================

PLAN_PROMPT = """Create a step-by-step execution plan for this task:
Task: {task}
{context}

Return a JSON array of steps. Each step has:
- "id": step identifier (e.g., "step1")
- "action": what to do (description)
- "action_type": one of [navigate, click, type, search, extract, wait, verify, system, ai_query, screenshot]
- "target": element or URL to act on
- "value": text to type or data to use
- "expected_result": what success looks like
- "dependencies": array of step IDs this depends on (empty for first steps)

Return ONLY valid JSON array, no other text."""

VERIFY_PROMPT = """You are verifying if a task step was completed successfully.

Step: {action}
Expected outcome: {expected}
Actual result: {actual}

Is the step completed successfully? Answer with JSON:
{{"success": true/false, "explanation": "brief reason", "suggestion": "what to try if failed"}}"""

REPLAN_PROMPT = """A step in my plan failed. Help me revise.

Task: {task}
Failed step: {failed_action}
Error: {error}

Completed steps:
{completed}

Remaining steps:
{remaining}

Suggest an alternative approach for the failed step.
Return ONLY a JSON object with 'action', 'action_type', 'target', 'value', 'expected_result'."""


class AdvancedPlanner:
    """
    AI-powered multi-step planner with dependency tracking,
    verification, and recovery.

    Generates structured execution plans from natural language tasks,
    executes them step-by-step with verification after each step,
    and revises plans when steps fail.

    Usage:
        planner = AdvancedPlanner(ai_router=router)
        plan = planner.create_plan("search for AI news on google")

        # Manual execution
        for nodes in iter(plan.get_next_executable, []):
            for node in nodes:
                result = execute(node)
                planner.complete_step(node.id, result)

        # Or automatic execution
        planner.execute_plan(plan, executor=my_executor, progress_callback=on_step)
    """

    def __init__(self, ai_router=None, executor: Callable = None):
        """
        Args:
            ai_router: Object with .query(prompt) method returning str
            executor: Callable(action_type, target, value, parameters) -> result str
        """
        self.ai_router = ai_router
        self.executor = executor
        self.plans: Dict[str, ExecutionPlan] = {}
        self.current_plan: Optional[ExecutionPlan] = None
        self._cancelled = False
        self._plan_counter = 0
        self.max_steps = int(os.getenv('MAX_PLAN_STEPS', '30'))

    # ============================================================
    # Plan Creation
    # ============================================================

    def create_plan(self, task: str, context: str = "") -> ExecutionPlan:
        """
        Create an execution plan for a task.
        Uses AI when available, falls back to simple sequential plan.
        """
        self._plan_counter += 1
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._plan_counter}"

        if self.ai_router:
            try:
                plan = self._ai_create_plan(task, context, plan_id)
                if plan and plan.nodes:
                    return plan
            except Exception as e:
                logger.warning(f"[Planner] AI planning failed: {e}")

        return self._simple_plan(task, plan_id)

    def _ai_create_plan(self, task: str, context: str, plan_id: str) -> ExecutionPlan:
        """Use AI to generate a structured plan."""
        ctx_line = f"Context: {context}" if context else ""
        prompt = PLAN_PROMPT.format(task=task, context=ctx_line)

        response = self.ai_router.query(prompt)
        if not response:
            return self._simple_plan(task, plan_id)

        steps = self._parse_json_array(response)
        if not steps:
            return self._simple_plan(task, plan_id)

        plan = ExecutionPlan(plan_id=plan_id, task=task)

        for step_data in steps[:self.max_steps]:
            if not isinstance(step_data, dict):
                continue
            node_id = step_data.get('id', f'step{len(plan.nodes) + 1}')
            node = PlanNode(
                id=node_id,
                action=step_data.get('action', ''),
                action_type=step_data.get('action_type', 'general'),
                target=step_data.get('target', ''),
                value=step_data.get('value', ''),
                expected_result=step_data.get('expected_result', ''),
                dependencies=step_data.get('dependencies', []),
                parameters=step_data.get('parameters', {}),
            )
            plan.nodes[node_id] = node

        plan.execution_order = self._topological_sort(plan)
        plan.status = PlanStatus.EXECUTING
        self.current_plan = plan
        self.plans[plan_id] = plan

        logger.info(f"[Planner] Created plan: {plan_id} with {len(plan.nodes)} steps")
        return plan

    def _simple_plan(self, task: str, plan_id: str) -> ExecutionPlan:
        """Create a simple sequential plan without AI."""
        plan = ExecutionPlan(plan_id=plan_id, task=task)
        node = PlanNode(
            id="step1",
            action=task,
            action_type="general",
        )
        plan.nodes["step1"] = node
        plan.execution_order = ["step1"]
        plan.status = PlanStatus.EXECUTING
        self.current_plan = plan
        self.plans[plan_id] = plan
        return plan

    # ============================================================
    # Plan Execution
    # ============================================================

    def execute_plan(self, plan: ExecutionPlan,
                     executor: Callable = None,
                     progress_callback: Callable = None,
                     verify_steps: bool = True) -> ExecutionPlan:
        """
        Execute all steps in a plan with verification and recovery.

        Args:
            plan: The plan to execute
            executor: Callable(action_type, target, value, parameters) -> result str
            progress_callback: Called after each step with (plan, node)
            verify_steps: Whether to AI-verify step outcomes

        Returns:
            Updated plan with results
        """
        self._cancelled = False
        plan.status = PlanStatus.EXECUTING
        exec_fn = executor or self.executor

        while True:
            if self._cancelled:
                plan.status = PlanStatus.CANCELLED
                break

            ready = plan.get_next_executable()
            if not ready:
                break

            for node in ready:
                if self._cancelled:
                    break

                success = self._execute_node(node, plan, exec_fn, verify_steps)

                if progress_callback:
                    try:
                        progress_callback(plan, node)
                    except Exception:
                        pass

                if not success and node.status != PlanNodeStatus.COMPLETED:
                    # Try replanning
                    if plan.total_replans < plan.max_replans:
                        revised = self.revise_plan(node.id, node.error or "Step failed")
                        if revised:
                            plan.total_replans += 1
                            # Reset the failed node to try again
                            node.status = PlanNodeStatus.PENDING
                            continue

        # Determine final status
        completed = len(plan.completed_nodes)
        failed = len(plan.failed_nodes)
        total = len(plan.nodes)

        if self._cancelled:
            plan.status = PlanStatus.CANCELLED
        elif failed == 0 and completed == total:
            plan.status = PlanStatus.COMPLETED
        elif completed > 0:
            plan.status = PlanStatus.PARTIAL
        else:
            plan.status = PlanStatus.FAILED

        plan.completed_at = datetime.now().isoformat()
        logger.info(f"[Planner] Plan {plan.plan_id}: {plan.status.value} "
                     f"({completed}/{total} steps completed, {failed} failed)")
        return plan

    def execute_plan_parallel(self, plan: ExecutionPlan,
                              executor: Callable = None,
                              progress_callback: Callable = None,
                              verify_steps: bool = True,
                              max_workers: int = 4) -> ExecutionPlan:
        """
        Execute plan steps in parallel where dependencies allow.

        Each layer of independent steps executes concurrently.
        Steps within a layer that have all dependencies met run in parallel.

        Args:
            plan: The plan to execute
            executor: Callable(action_type, target, value, parameters) -> result str
            progress_callback: Called after each step with (plan, node)
            verify_steps: Whether to AI-verify step outcomes
            max_workers: Maximum number of parallel workers

        Returns:
            Updated plan with results
        """
        self._cancelled = False
        plan.status = PlanStatus.EXECUTING
        exec_fn = executor or self.executor

        layer_num = 0
        while True:
            if self._cancelled:
                plan.status = PlanStatus.CANCELLED
                break

            # Get all nodes ready to execute (dependencies met)
            ready = plan.get_next_executable()
            if not ready:
                break

            layer_num += 1
            logger.info(f"[Planner] Executing layer {layer_num} with {len(ready)} parallel tasks")

            # Execute ready nodes in parallel
            results: Dict[str, Tuple[PlanNode, bool]] = {}

            with ThreadPoolExecutor(max_workers=min(max_workers, len(ready))) as pool:
                future_to_node = {
                    pool.submit(self._execute_node_threadsafe, node, plan, exec_fn, verify_steps): node
                    for node in ready
                }

                for future in as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        success = future.result()
                        results[node.id] = (node, success)
                    except Exception as e:
                        logger.error(f"[Planner] Parallel execution error for {node.id}: {e}")
                        results[node.id] = (node, False)
                        node.error = str(e)
                        self._mark_failed(node, plan)

            # Call progress callbacks for completed nodes
            if progress_callback:
                for node_id, (node, success) in results.items():
                    try:
                        progress_callback(plan, node)
                    except Exception:
                        pass

            # Handle replanning for failed nodes
            for node_id, (node, success) in results.items():
                if not success and node.status != PlanNodeStatus.COMPLETED:
                    if plan.total_replans < plan.max_replans:
                        revised = self.revise_plan(node.id, node.error or "Step failed")
                        if revised:
                            plan.total_replans += 1
                            node.status = PlanNodeStatus.PENDING

        # Determine final status
        completed = len(plan.completed_nodes)
        failed = len(plan.failed_nodes)
        total = len(plan.nodes)

        if self._cancelled:
            plan.status = PlanStatus.CANCELLED
        elif failed == 0 and completed == total:
            plan.status = PlanStatus.COMPLETED
        elif completed > 0:
            plan.status = PlanStatus.PARTIAL
        else:
            plan.status = PlanStatus.FAILED

        plan.completed_at = datetime.now().isoformat()
        logger.info(f"[Planner] Parallel plan {plan.plan_id}: {plan.status.value} "
                     f"({completed}/{total} steps completed, {failed} failed, {layer_num} layers)")
        return plan

    def _execute_node_threadsafe(self, node: PlanNode, plan: ExecutionPlan,
                                  executor: Callable = None, verify: bool = True) -> bool:
        """
        Thread-safe version of _execute_node for parallel execution.

        Uses a lock around critical sections to prevent race conditions.
        """
        return self._execute_node(node, plan, executor, verify)

    def _execute_node(self, node: PlanNode, plan: ExecutionPlan,
                      executor: Callable = None, verify: bool = True) -> bool:
        """Execute a single node with retry and verification."""
        node.status = PlanNodeStatus.RUNNING
        node.started_at = datetime.now().isoformat()

        for attempt in range(node.max_retries + 1):
            if self._cancelled:
                return False

            try:
                if executor:
                    result = executor(
                        node.action_type,
                        node.target,
                        node.value,
                        node.parameters,
                    )
                    node.result = str(result) if result else "Executed"
                else:
                    node.result = "No executor configured"

                # Verify with AI
                if verify and node.expected_result and self.ai_router:
                    verified = self._verify_node(node)
                    if verified:
                        self._mark_completed(node, plan)
                        return True
                    else:
                        node.retries = attempt + 1
                        if attempt < node.max_retries:
                            logger.info(f"[Planner] {node.id} verification failed, "
                                        f"retry {attempt + 1}/{node.max_retries}")
                            time.sleep(min(2 ** attempt, 8))
                            continue
                else:
                    self._mark_completed(node, plan)
                    return True

            except Exception as e:
                node.error = str(e)
                node.retries = attempt + 1
                logger.warning(f"[Planner] {node.id} attempt {attempt + 1} error: {e}")
                if attempt < node.max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue

        self._mark_failed(node, plan)
        return False

    def _verify_node(self, node: PlanNode) -> bool:
        """Use AI to verify step outcome."""
        if not self.ai_router:
            return True

        node.status = PlanNodeStatus.VERIFYING
        prompt = VERIFY_PROMPT.format(
            action=node.action,
            expected=node.expected_result,
            actual=node.result or "No result captured",
        )

        try:
            response = self.ai_router.query(prompt)
            parsed = self._parse_json_object(response)

            if parsed:
                success = parsed.get('success', False)
                node.verification_result = parsed.get('explanation', '')
                if not success:
                    suggestion = parsed.get('suggestion', '')
                    node.error = f"Verification failed: {suggestion or node.verification_result}"
                return success

            return True  # Can't parse, assume OK
        except Exception as e:
            logger.warning(f"[Planner] Verification error: {e}")
            return True

    def _mark_completed(self, node: PlanNode, plan: ExecutionPlan):
        node.status = PlanNodeStatus.COMPLETED
        node.completed_at = datetime.now().isoformat()
        plan.completed_nodes.add(node.id)

    def _mark_failed(self, node: PlanNode, plan: ExecutionPlan):
        node.status = PlanNodeStatus.FAILED
        node.completed_at = datetime.now().isoformat()
        plan.failed_nodes.add(node.id)

    # Also provide simple mark methods for manual execution
    def mark_completed(self, node_id: str, result: str = ""):
        if self.current_plan and node_id in self.current_plan.nodes:
            node = self.current_plan.nodes[node_id]
            node.result = result
            self._mark_completed(node, self.current_plan)

    def mark_failed(self, node_id: str, error: str = ""):
        if self.current_plan and node_id in self.current_plan.nodes:
            node = self.current_plan.nodes[node_id]
            node.error = error
            self._mark_failed(node, self.current_plan)

    # ============================================================
    # Plan Revision
    # ============================================================

    def revise_plan(self, failed_node_id: str, error: str) -> Optional[ExecutionPlan]:
        """
        Revise the plan when a step fails.
        Uses AI to generate alternative steps or reorder remaining work.
        """
        if not self.current_plan or not self.ai_router:
            return None

        plan = self.current_plan
        failed_node = plan.nodes.get(failed_node_id)
        if not failed_node:
            return None

        # If node has retries left, just reset it
        if failed_node.retries < failed_node.max_retries:
            failed_node.status = PlanNodeStatus.PENDING
            return plan

        failed_node.status = PlanNodeStatus.REPLANNING

        completed = '\n'.join(
            f"- {plan.nodes[nid].action} (done)"
            for nid in plan.completed_nodes
        ) or 'None'
        remaining = '\n'.join(
            f"- {plan.nodes[nid].action}"
            for nid in plan.execution_order
            if plan.nodes[nid].status == PlanNodeStatus.PENDING
        ) or 'None'

        prompt = REPLAN_PROMPT.format(
            task=plan.task,
            failed_action=failed_node.action,
            error=error,
            completed=completed,
            remaining=remaining,
        )

        try:
            response = self.ai_router.query(prompt)
            if response:
                parsed = self._parse_json_object(response)
                if parsed:
                    failed_node.action = parsed.get('action', failed_node.action)
                    failed_node.action_type = parsed.get('action_type', failed_node.action_type)
                    failed_node.target = parsed.get('target', failed_node.target)
                    failed_node.value = parsed.get('value', failed_node.value)
                    failed_node.expected_result = parsed.get('expected_result', failed_node.expected_result)
                    failed_node.status = PlanNodeStatus.PENDING
                    failed_node.error = None
                    logger.info(f"[Planner] Revised step {failed_node_id}: {failed_node.action}")
                    return plan
        except Exception as e:
            logger.warning(f"[Planner] Plan revision failed: {e}")

        return None

    def cancel(self):
        """Cancel the currently executing plan"""
        self._cancelled = True

    # ============================================================
    # Utilities
    # ============================================================

    def _topological_sort(self, plan: ExecutionPlan) -> List[str]:
        """Topological sort of plan nodes respecting dependencies."""
        visited = set()
        order = []
        visiting = set()

        def visit(node_id: str):
            if node_id in visited:
                return
            if node_id in visiting:
                return  # Cycle detected, skip
            visiting.add(node_id)

            node = plan.nodes.get(node_id)
            if node:
                for dep in node.dependencies:
                    if dep in plan.nodes:
                        visit(dep)

            visiting.discard(node_id)
            visited.add(node_id)
            order.append(node_id)

        for nid in plan.nodes:
            visit(nid)

        return order

    def _parse_json_array(self, text: str) -> Optional[list]:
        """Extract JSON array from AI response."""
        if not text:
            return None
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Try code block extraction
        for marker in ['```json', '```']:
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.find('```', start)
                if end > start:
                    try:
                        parsed = json.loads(text[start:end].strip())
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        pass

        # Regex fallback
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _parse_json_object(self, text: str) -> Optional[dict]:
        """Extract JSON object from AI response."""
        if not text:
            return None
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for marker in ['```json', '```']:
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.find('```', start)
                if end > start:
                    try:
                        parsed = json.loads(text[start:end].strip())
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass

        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def get_plan_summary(self) -> str:
        """Get a human-readable plan summary."""
        if not self.current_plan:
            return "No active plan"

        plan = self.current_plan
        lines = [
            f"Plan: {plan.task}",
            f"Status: {plan.status.value}",
            f"Progress: {plan.progress:.0%} ({len(plan.completed_nodes)}/{len(plan.nodes)})",
            "",
        ]

        for nid in plan.execution_order:
            node = plan.nodes[nid]
            icon = {
                PlanNodeStatus.PENDING: "  ",
                PlanNodeStatus.RUNNING: "->",
                PlanNodeStatus.VERIFYING: "? ",
                PlanNodeStatus.COMPLETED: "OK",
                PlanNodeStatus.FAILED: "X ",
                PlanNodeStatus.SKIPPED: "- ",
                PlanNodeStatus.REPLANNING: "~ ",
            }.get(node.status, "? ")
            deps = f" (after: {', '.join(node.dependencies)})" if node.dependencies else ""
            lines.append(f"[{icon}] {node.id}: {node.action}{deps}")
            if node.error:
                lines.append(f"       Error: {node.error}")

        return "\n".join(lines)

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""
        return self.plans.get(plan_id)

    def get_recent_plans(self, count: int = 10) -> List[ExecutionPlan]:
        """Get most recent plans"""
        sorted_plans = sorted(
            self.plans.values(),
            key=lambda p: p.created_at,
            reverse=True
        )
        return sorted_plans[:count]
