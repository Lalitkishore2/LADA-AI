"""
LADA Task Integration Bridge

Provides adapters to integrate existing task modules with the unified task registry:
- TaskOrchestrator adapter
- TaskAutomation adapter
- WorkflowPipelines adapter

These adapters allow existing code to continue working while tasks are
stored in the unified registry for durability and cross-module visibility.
"""

import ast
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from modules.tasks.task_registry import (
    TaskRegistry,
    RegistryTask,
    TaskStep,
    TaskStatus,
    TaskPriority,
    StepStatus,
    StepResult,
    StepType,
    get_registry,
)

from modules.tasks.task_flow_registry import (
    TaskFlowRegistry,
    TaskFlow,
    FlowStepConfig,
    ExecutionMode,
    get_flow_registry,
)

logger = logging.getLogger(__name__)


def _safe_eval_condition(condition: str, outputs: Dict[str, Any]) -> bool:
    """Safely evaluate simple condition expressions against flow outputs.

    Supports comparisons, boolean ops, `len(...)`, and `outputs.get(...)`/subscripting.
    Disallows arbitrary function calls, attribute access, imports, and execution.
    """

    parsed = ast.parse(condition, mode="eval")
    data = outputs or {}

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id == "outputs":
                return data
            raise ValueError(f"Unsupported name in condition: {node.id}")

        if isinstance(node, ast.List):
            return [_eval(elt) for elt in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(_eval(elt) for elt in node.elts)

        if isinstance(node, ast.Dict):
            return {_eval(k): _eval(v) for k, v in zip(node.keys, node.values)}

        if isinstance(node, ast.Subscript):
            value = _eval(node.value)
            key = _eval(node.slice)
            return value[key]

        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            if isinstance(node.op, ast.Not):
                return not bool(value)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value
            raise ValueError("Unsupported unary operator in condition")

        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            raise ValueError("Unsupported binary operator in condition")

        if isinstance(node, ast.BoolOp):
            values = node.values
            if isinstance(node.op, ast.And):
                return all(bool(_eval(v)) for v in values)
            if isinstance(node.op, ast.Or):
                return any(bool(_eval(v)) for v in values)
            raise ValueError("Unsupported boolean operator in condition")

        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval(comparator)
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                elif isinstance(op, ast.Is):
                    ok = left is right
                elif isinstance(op, ast.IsNot):
                    ok = left is not right
                else:
                    raise ValueError("Unsupported comparison operator in condition")
                if not ok:
                    return False
                left = right
            return True

        if isinstance(node, ast.Call):
            # Allow len(<expr>)
            if isinstance(node.func, ast.Name) and node.func.id == "len":
                if len(node.args) != 1 or node.keywords:
                    raise ValueError("len() condition call shape is invalid")
                return len(_eval(node.args[0]))

            # Allow outputs.get(key[, default])
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "outputs"
            ):
                args = [_eval(arg) for arg in node.args]
                if len(args) == 1:
                    return data.get(args[0])
                if len(args) == 2:
                    return data.get(args[0], args[1])
                raise ValueError("outputs.get() condition call shape is invalid")

            raise ValueError("Unsupported function call in condition")

        raise ValueError(f"Unsupported expression in condition: {type(node).__name__}")

    return bool(_eval(parsed))


# ============================================================================
# Task Orchestrator Adapter
# ============================================================================

class OrchestratorAdapter:
    """
    Adapter for task_orchestrator.py to use the unified registry.
    
    Maps TaskOrchestrator's Task objects to RegistryTask.
    """
    
    def __init__(
        self,
        registry: Optional[TaskRegistry] = None,
        agent_id: str = "default",
    ):
        self._registry = registry or get_registry()
        self._agent_id = agent_id
        self._action_handlers: Dict[str, Callable] = {}
    
    def register_action(self, action: str, handler: Callable):
        """Register a handler for an action type."""
        self._action_handlers[action] = handler
    
    def submit_task(
        self,
        name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegistryTask:
        """
        Submit a task to the unified registry.
        
        Compatible with TaskOrchestrator.submit_task() signature.
        """
        task = self._registry.create(
            name=name,
            action=action,
            params=params or {},
            dependencies=dependencies or [],
            priority=priority,
            timeout_seconds=timeout_seconds,
            agent_id=self._agent_id,
            metadata={
                "source": "orchestrator",
                "max_retries": max_retries,
                **(metadata or {}),
            },
        )
        task.max_retries = max_retries
        self._registry.update(task)
        
        # Auto-queue if no dependencies or all dependencies complete
        if self._registry.check_dependencies(task.id):
            self._registry.queue(task.id)
        
        return task
    
    def get_task(self, task_id: str) -> Optional[RegistryTask]:
        """Get task by ID."""
        return self._registry.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        return self._registry.cancel(task_id)
    
    def pause_task(self, task_id: str) -> Optional[str]:
        """Pause a task and return resume token."""
        return self._registry.pause(task_id)
    
    def resume_task(self, token_or_id: str) -> Optional[RegistryTask]:
        """Resume a paused task."""
        # Try as token first
        task = self._registry.resume(token_or_id)
        if task:
            return task
        
        # Try as task_id
        task = self._registry.get(token_or_id)
        if task and task.resume_token:
            return self._registry.resume(task.resume_token)
        
        return None
    
    def get_ready_tasks(self) -> List[RegistryTask]:
        """Get tasks ready for execution (dependencies met)."""
        return self._registry.get_ready_tasks(agent_id=self._agent_id)
    
    def execute_task(self, task: RegistryTask) -> Dict[str, Any]:
        """
        Execute a task using registered action handler.
        
        Returns result dict with status, result/error.
        """
        handler = self._action_handlers.get(task.action)
        if not handler:
            error = f"No handler registered for action: {task.action}"
            self._registry.fail(task.id, error)
            return {"success": False, "error": error}
        
        self._registry.start(task.id)
        
        try:
            result = handler(task.params)
            self._registry.complete(task.id, result)
            return {"success": True, "result": result}
        except Exception as e:
            error = str(e)
            
            # Check retries
            task = self._registry.get(task.id)
            if task.retry_count < task.max_retries:
                if self._registry.retry(task.id):
                    return {"success": False, "error": error, "retrying": True}
            
            self._registry.fail(task.id, error)
            return {"success": False, "error": error}
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        tasks = self._registry.list_tasks(agent_id=self._agent_id)
        
        status_counts = {}
        for task in tasks:
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_tasks": len(tasks),
            "status_counts": status_counts,
            "ready_tasks": len(self.get_ready_tasks()),
        }


# ============================================================================
# Task Automation Adapter
# ============================================================================

class AutomationAdapter:
    """
    Adapter for task_automation.py to use the unified registry.
    
    Maps TaskAutomation's multi-step tasks to TaskFlow.
    """
    
    def __init__(
        self,
        flow_registry: Optional[TaskFlowRegistry] = None,
        agent_id: str = "default",
    ):
        self._flow_registry = flow_registry or get_flow_registry()
        self._agent_id = agent_id
        self._step_handlers: Dict[str, Callable] = {}
    
    def register_step_handler(self, action: str, handler: Callable):
        """Register a handler for a step action."""
        self._step_handlers[action] = handler
    
    def create_task(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskFlow:
        """
        Create a multi-step task.
        
        Compatible with TaskAutomation.create_task() pattern.
        """
        # Convert step dicts to FlowStepConfig
        flow_steps = []
        for i, step_data in enumerate(steps):
            step = FlowStepConfig(
                id=step_data.get("id", f"step_{i+1}"),
                name=step_data.get("name", f"Step {i+1}"),
                step_type=StepType.FUNCTION,
                action=step_data.get("action", ""),
                parameters=step_data.get("parameters", {}),
                timeout_seconds=step_data.get("timeout", 300),
                retries=step_data.get("retries", 3),
                dependencies=step_data.get("dependencies", []),
            )
            flow_steps.append(step)
        
        flow = self._flow_registry.create_flow(
            name=name,
            steps=flow_steps,
            execution_mode=ExecutionMode.SEQUENTIAL,
            agent_id=self._agent_id,
            metadata={"source": "automation", "description": description, **(metadata or {})},
        )
        
        return flow
    
    def start_task(self, flow_id: str) -> bool:
        """Start task execution."""
        return self._flow_registry.start_flow(flow_id)
    
    def get_task(self, flow_id: str) -> Optional[TaskFlow]:
        """Get task/flow by ID."""
        return self._flow_registry.get_flow(flow_id)
    
    def execute_step(self, flow_id: str, step_id: str) -> StepResult:
        """
        Execute a single step.
        
        Uses registered step handler for the action.
        """
        flow = self._flow_registry.get_flow(flow_id)
        task = self._flow_registry.get_task(flow_id)
        
        if not flow or not task:
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error="Flow or task not found",
            )
        
        # Find step
        step = None
        for s in task.steps:
            if s.id == step_id:
                step = s
                break
        
        if not step:
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error="Step not found",
            )
        
        # Get handler
        handler = self._step_handlers.get(step.action)
        if not handler:
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=f"No handler for action: {step.action}",
            )
        
        # Execute
        started_at = datetime.now().isoformat()
        try:
            # Pass flow outputs for piping
            result_value = handler(step.parameters, flow.outputs)
            
            result = StepResult(
                step_id=step_id,
                status=StepStatus.SUCCEEDED,
                return_value=result_value,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
            )
        except Exception as e:
            result = StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
            )
        
        # Record result and advance flow
        self._flow_registry.complete_step(flow_id, step_id, result)
        
        return result
    
    def pause_task(self, flow_id: str) -> Optional[str]:
        """Pause task and get resume token."""
        flow = self._flow_registry.get_flow(flow_id)
        if not flow:
            return None
        return self._flow_registry.pause_flow(flow_id, flow.current_step_id)
    
    def resume_task(self, token: str) -> Optional[TaskFlow]:
        """Resume a paused task."""
        return self._flow_registry.resume_flow(token)
    
    def cancel_task(self, flow_id: str) -> bool:
        """Cancel a task."""
        return self._flow_registry.cancel_flow(flow_id)
    
    def list_running_tasks(self) -> List[TaskFlow]:
        """List running tasks."""
        from modules.tasks.task_flow_registry import FlowStatus
        return self._flow_registry.list_flows(
            agent_id=self._agent_id,
            status=FlowStatus.RUNNING,
        )


# ============================================================================
# Pipeline Adapter
# ============================================================================

class PipelineAdapter:
    """
    Adapter for workflow_pipelines.py to use the unified registry.
    
    Preserves workflow_pipelines' deterministic execution model
    while storing state in the unified registry.
    """
    
    def __init__(
        self,
        flow_registry: Optional[TaskFlowRegistry] = None,
        agent_id: str = "default",
    ):
        self._flow_registry = flow_registry or get_flow_registry()
        self._agent_id = agent_id
    
    def create_pipeline(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
    ) -> TaskFlow:
        """
        Create a pipeline.
        
        Steps support:
        - type: exec, function, ai_prompt, approval, condition
        - command/function_name/ai_prompt/approval_message
        - stdin_source for piping
        - continue_on_error
        """
        flow_steps = []
        for i, step_data in enumerate(steps):
            step_type = step_data.get("type", "function")
            step_type_map = {
                "exec": StepType.EXEC,
                "function": StepType.FUNCTION,
                "ai_prompt": StepType.AI_PROMPT,
                "approval": StepType.APPROVAL,
                "condition": StepType.CONDITION,
            }
            
            step = FlowStepConfig(
                id=step_data.get("id", f"step_{i+1}"),
                name=step_data.get("name", f"Step {i+1}"),
                step_type=step_type_map.get(step_type, StepType.FUNCTION),
                action=step_data.get("command") or step_data.get("function_name") or step_data.get("ai_prompt") or "",
                parameters=step_data.get("parameters", {}),
                timeout_seconds=step_data.get("timeout_ms", 300000) // 1000,
                continue_on_error=step_data.get("continue_on_error", False),
                condition=step_data.get("condition"),
                stdin_source=step_data.get("stdin_source"),
                approval_message=step_data.get("approval_message"),
            )
            flow_steps.append(step)
        
        flow = self._flow_registry.create_flow(
            name=name,
            steps=flow_steps,
            execution_mode=ExecutionMode.SEQUENTIAL,
            stop_on_failure=True,
            agent_id=self._agent_id,
            metadata={"source": "pipeline", "description": description},
        )
        
        return flow
    
    def run_pipeline(self, flow_id: str, executor: Callable) -> TaskFlow:
        """
        Execute pipeline steps sequentially.
        
        executor(step, outputs) -> StepResult
        """
        self._flow_registry.start_flow(flow_id)
        
        flow = self._flow_registry.get_flow(flow_id)
        task = self._flow_registry.get_task(flow_id)
        
        if not flow or not task:
            return flow
        
        for step in task.steps:
            # Check condition
            if step.condition:
                # Simple condition evaluation
                try:
                    if not _safe_eval_condition(str(step.condition), flow.outputs):
                        result = StepResult(
                            step_id=step.id,
                            status=StepStatus.SKIPPED,
                        )
                        self._flow_registry.complete_step(flow_id, step.id, result)
                        continue
                except Exception as exc:
                    logger.warning(
                        "[PipelineAdapter] Condition evaluation failed for %s: %s",
                        step.id,
                        exc,
                    )
            
            # Handle approval step
            if step.step_type == StepType.APPROVAL:
                token = self._flow_registry.await_approval(
                    flow_id,
                    step.id,
                    step.approval_message or "Approval required",
                )
                # Return paused flow
                return self._flow_registry.get_flow(flow_id)
            
            # Execute step
            result = executor(step, flow.outputs)
            
            # Record result
            next_step = self._flow_registry.complete_step(flow_id, step.id, result)
            
            if result.status == StepStatus.FAILED and not step.continue_on_error:
                break
            
            # Update flow reference
            flow = self._flow_registry.get_flow(flow_id)
        
        return self._flow_registry.get_flow(flow_id)
    
    def resume(self, token: str, approved: bool = True) -> Optional[TaskFlow]:
        """Resume a paused pipeline."""
        return self._flow_registry.resume_flow(token, approved)
    
    def list_pending_approvals(self) -> List[TaskFlow]:
        """List flows awaiting approval."""
        from modules.tasks.task_flow_registry import FlowStatus
        return self._flow_registry.list_flows(
            agent_id=self._agent_id,
            status=FlowStatus.AWAITING_APPROVAL,
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def get_orchestrator_adapter(agent_id: str = "default") -> OrchestratorAdapter:
    """Get orchestrator adapter for an agent."""
    return OrchestratorAdapter(agent_id=agent_id)


def get_automation_adapter(agent_id: str = "default") -> AutomationAdapter:
    """Get automation adapter for an agent."""
    return AutomationAdapter(agent_id=agent_id)


def get_pipeline_adapter(agent_id: str = "default") -> PipelineAdapter:
    """Get pipeline adapter for an agent."""
    return PipelineAdapter(agent_id=agent_id)
