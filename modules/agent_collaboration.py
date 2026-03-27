"""
LADA v11.0 - Multi-Agent Collaboration Framework
Enables agents to delegate, share context, and collaborate on complex tasks.

Architecture:
- AgentCollaborationHub: Central message bus for inter-agent communication
- CollaborativeAgent: Mixin that adds collaboration capabilities to any agent
- TaskDelegation: Structured task delegation between agents
- SharedContext: Shared memory/context accessible by all agents in a collaboration
"""

import os
import json
import time
import uuid
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from enum import Enum
from typing import List, Dict, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Roles an agent can take in a collaboration."""
    ORCHESTRATOR = "orchestrator"  # Plans and delegates
    SPECIALIST = "specialist"      # Executes specific tasks
    REVIEWER = "reviewer"          # Validates results
    RESEARCHER = "researcher"      # Gathers information
    SUMMARIZER = "summarizer"      # Consolidates findings


class TaskStatus(Enum):
    PENDING = "pending"
    DELEGATED = "delegated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWING = "reviewing"


@dataclass
class AgentMessage:
    """Message passed between agents."""
    from_agent: str
    to_agent: str  # Use "*" for broadcast
    message_type: str  # "task", "result", "query", "context", "status"
    content: Dict[str, Any]
    conversation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class DelegatedTask:
    """A task delegated from one agent to another."""
    task_id: str
    description: str
    from_agent: str
    to_agent: str
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "status": self.status.value,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class SharedContext:
    """
    Shared memory accessible by all agents in a collaboration session.
    Thread-safe key-value store with change tracking.
    """

    def __init__(self, session_id: str = ""):
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self._store: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, source_agent: str = ""):
        with self._lock:
            old = self._store.get(key)
            self._store[key] = value
            self._history.append({
                "key": key, "old_value": old, "new_value": value,
                "source": source_agent, "timestamp": time.time(),
            })

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._store.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._store)

    def get_summary(self, max_items: int = 20) -> str:
        """Get context as formatted string for LLM injection."""
        with self._lock:
            items = list(self._store.items())[:max_items]
            if not items:
                return ""
            parts = ["[Shared Context:]"]
            for k, v in items:
                val_str = str(v)[:200]
                parts.append(f"- {k}: {val_str}")
            return "\n".join(parts)

    def has_key(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def clear(self):
        with self._lock:
            self._store.clear()


class AgentCollaborationHub:
    """
    Central hub for multi-agent collaboration.

    Features:
    - Agent registration with capability declaration
    - Message routing between agents
    - Task delegation and tracking
    - Shared context management
    - Collaboration session lifecycle
    - Agent capability matching for auto-delegation
    """

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._message_handlers: Dict[str, Callable] = {}
        self._message_queue: List[AgentMessage] = []
        self._tasks: Dict[str, DelegatedTask] = {}
        self._sessions: Dict[str, SharedContext] = {}
        self._agent_capabilities: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self._stats = {
            "messages_routed": 0,
            "tasks_delegated": 0,
            "tasks_completed": 0,
            "sessions_created": 0,
        }

    def register_agent(self, agent_name: str,
                       capabilities: List[str] = None,
                       handler: Optional[Callable] = None,
                       metadata: Optional[Dict[str, Any]] = None):
        """
        Register an agent with the collaboration hub.

        Args:
            agent_name: Unique agent identifier
            capabilities: List of capability keywords (e.g., ["web_search", "summarize", "code"])
            handler: Callback function for incoming messages
            metadata: Additional agent metadata
        """
        with self._lock:
            self._agents[agent_name] = {
                "name": agent_name,
                "capabilities": capabilities or [],
                "metadata": metadata or {},
                "registered_at": time.time(),
                "messages_received": 0,
                "tasks_completed": 0,
            }
            self._agent_capabilities[agent_name] = capabilities or []
            if handler:
                self._message_handlers[agent_name] = handler
            logger.info(f"[AgentHub] Registered agent: {agent_name} with capabilities: {capabilities}")

    def unregister_agent(self, agent_name: str):
        """Remove an agent from the hub."""
        with self._lock:
            self._agents.pop(agent_name, None)
            self._message_handlers.pop(agent_name, None)
            self._agent_capabilities.pop(agent_name, None)

    def send_message(self, message: AgentMessage) -> bool:
        """
        Route a message to target agent(s).

        Supports unicast (specific agent) and broadcast ("*").
        """
        with self._lock:
            self._stats["messages_routed"] += 1

            if message.to_agent == "*":
                # Broadcast to all agents except sender
                for name, handler in self._message_handlers.items():
                    if name != message.from_agent:
                        try:
                            handler(message)
                            self._agents[name]["messages_received"] += 1
                        except Exception as e:
                            logger.error(f"[AgentHub] Broadcast error to {name}: {e}")
                return True
            else:
                handler = self._message_handlers.get(message.to_agent)
                if handler:
                    try:
                        handler(message)
                        self._agents[message.to_agent]["messages_received"] += 1
                        return True
                    except Exception as e:
                        logger.error(f"[AgentHub] Message delivery error to {message.to_agent}: {e}")
                        return False
                else:
                    # Queue for later delivery
                    self._message_queue.append(message)
                    return True

    def delegate_task(self, from_agent: str, description: str,
                      to_agent: Optional[str] = None,
                      context: Optional[Dict[str, Any]] = None,
                      constraints: Optional[Dict[str, Any]] = None,
                      required_capability: Optional[str] = None) -> DelegatedTask:
        """
        Delegate a task from one agent to another.

        If to_agent is None and required_capability is specified,
        automatically selects the best agent for the job.
        """
        # Auto-select target agent if not specified
        if to_agent is None and required_capability:
            to_agent = self._find_best_agent(required_capability, exclude=from_agent)

        if to_agent is None:
            to_agent = "orchestrator"  # fallback

        task = DelegatedTask(
            task_id=uuid.uuid4().hex[:12],
            description=description,
            from_agent=from_agent,
            to_agent=to_agent,
            context=context or {},
            constraints=constraints or {},
            status=TaskStatus.DELEGATED,
        )

        with self._lock:
            self._tasks[task.task_id] = task
            self._stats["tasks_delegated"] += 1

        # Notify target agent
        self.send_message(AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task",
            content={
                "task_id": task.task_id,
                "description": description,
                "context": context or {},
                "constraints": constraints or {},
            },
        ))

        logger.info(f"[AgentHub] Task delegated: {from_agent} -> {to_agent}: {description[:80]}")
        return task

    def complete_task(self, task_id: str, result: Dict[str, Any],
                      agent_name: str = "") -> bool:
        """Mark a delegated task as completed with results."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()
            self._stats["tasks_completed"] += 1

            if agent_name in self._agents:
                self._agents[agent_name]["tasks_completed"] += 1

        # Notify delegating agent
        self.send_message(AgentMessage(
            from_agent=task.to_agent,
            to_agent=task.from_agent,
            message_type="result",
            content={
                "task_id": task_id,
                "status": "completed",
                "result": result,
            },
        ))

        return True

    def fail_task(self, task_id: str, error: str, agent_name: str = "") -> bool:
        """Mark a task as failed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.status = TaskStatus.FAILED
            task.result = {"error": error}
            task.completed_at = time.time()

        self.send_message(AgentMessage(
            from_agent=task.to_agent,
            to_agent=task.from_agent,
            message_type="result",
            content={"task_id": task_id, "status": "failed", "error": error},
        ))
        return True

    def _find_best_agent(self, required_capability: str,
                         exclude: str = "") -> Optional[str]:
        """Find the best agent for a given capability."""
        with self._lock:
            candidates = []
            for name, caps in self._agent_capabilities.items():
                if name == exclude:
                    continue
                if required_capability in caps:
                    candidates.append(name)

            if not candidates:
                # Fuzzy match
                for name, caps in self._agent_capabilities.items():
                    if name == exclude:
                        continue
                    for cap in caps:
                        if required_capability.lower() in cap.lower() or cap.lower() in required_capability.lower():
                            candidates.append(name)
                            break

            return candidates[0] if candidates else None

    def create_session(self, session_name: str = "") -> SharedContext:
        """Create a new collaboration session with shared context."""
        session = SharedContext(session_id=session_name or uuid.uuid4().hex[:8])
        with self._lock:
            self._sessions[session.session_id] = session
            self._stats["sessions_created"] += 1
        return session

    def get_session(self, session_id: str) -> Optional[SharedContext]:
        with self._lock:
            return self._sessions.get(session_id)

    def plan_and_delegate(self, user_query: str,
                          orchestrator_agent: str = "orchestrator",
                          ai_router: Any = None) -> List[DelegatedTask]:
        """
        High-level: Break a complex query into sub-tasks and delegate to specialist agents.

        Uses AI to decompose the query, then matches sub-tasks to agent capabilities.
        """
        # Get available agents and capabilities
        with self._lock:
            agent_info = {
                name: info.get("capabilities", [])
                for name, info in self._agents.items()
                if name != orchestrator_agent
            }

        if not agent_info:
            logger.warning("[AgentHub] No specialist agents available for delegation")
            return []

        # Build delegation plan
        agent_list = "\n".join(
            f"- {name}: {', '.join(caps)}"
            for name, caps in agent_info.items()
        )

        plan_prompt = (
            f"Break this task into sub-tasks and assign to available agents.\n\n"
            f"Task: {user_query}\n\n"
            f"Available agents:\n{agent_list}\n\n"
            f"Return a JSON array of objects with 'agent', 'task', 'depends_on' (list of task indices).\n"
            f"Example: [{{'agent': 'research_agent', 'task': 'search for X', 'depends_on': []}}]"
        )

        tasks = []

        if ai_router:
            try:
                response = ai_router.route_query(plan_prompt)
                # Try to parse JSON from response
                import re
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                    session = self.create_session()

                    for i, step in enumerate(plan):
                        task = self.delegate_task(
                            from_agent=orchestrator_agent,
                            to_agent=step.get("agent", ""),
                            description=step.get("task", ""),
                            context={"session_id": session.session_id, "step_index": i},
                        )
                        tasks.append(task)
            except Exception as e:
                logger.error(f"[AgentHub] Plan-and-delegate error: {e}")

        return tasks

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def list_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": name,
                    "capabilities": info.get("capabilities", []),
                    "messages_received": info.get("messages_received", 0),
                    "tasks_completed": info.get("tasks_completed", 0),
                }
                for name, info in self._agents.items()
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "registered_agents": len(self._agents),
                "active_sessions": len(self._sessions),
                "total_tasks": len(self._tasks),
                "pending_tasks": sum(
                    1 for t in self._tasks.values()
                    if t.status in (TaskStatus.PENDING, TaskStatus.DELEGATED, TaskStatus.IN_PROGRESS)
                ),
            }

    def execute_parallel(self, tasks: List[DelegatedTask],
                        max_workers: int = 4,
                        timeout: float = 60.0,
                        executor_fn: Optional[Callable[[DelegatedTask], Dict[str, Any]]] = None
                        ) -> Dict[str, Dict[str, Any]]:
        """
        Execute multiple tasks in parallel with dependency-aware scheduling.

        Tasks are organized into layers where each layer contains tasks
        whose dependencies are satisfied. Layers execute sequentially,
        but tasks within a layer execute in parallel.

        Args:
            tasks: List of DelegatedTask objects to execute
            max_workers: Maximum parallel workers
            timeout: Timeout per task in seconds
            executor_fn: Function to execute each task, receives DelegatedTask, returns result dict

        Returns:
            Dict mapping task_id to result dict
        """
        if not tasks:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        task_map = {t.task_id: t for t in tasks}

        # Build dependency graph from task context
        # Dependencies stored in task.context['depends_on'] as list of task_ids
        dependencies: Dict[str, Set[str]] = {}
        for task in tasks:
            deps = task.context.get('depends_on', [])
            dependencies[task.task_id] = set(deps) if deps else set()

        # Find parallel execution layers using topological sort
        layers = self._topological_layers(task_map, dependencies)

        if executor_fn is None:
            # Default executor: just mark task complete with placeholder result
            def default_executor(task: DelegatedTask) -> Dict[str, Any]:
                time.sleep(0.1)  # Simulate work
                return {"status": "completed", "task_id": task.task_id}
            executor_fn = default_executor

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for layer_idx, layer in enumerate(layers):
                logger.info(f"[AgentHub] Executing layer {layer_idx + 1}/{len(layers)} with {len(layer)} tasks")

                # Submit all tasks in this layer
                futures: Dict[Future, str] = {}
                for task_id in layer:
                    task = task_map[task_id]
                    task.status = TaskStatus.IN_PROGRESS
                    future = executor.submit(self._execute_task_wrapper, task, executor_fn, timeout)
                    futures[future] = task_id

                # Wait for all tasks in layer to complete
                for future in as_completed(futures.keys()):
                    task_id = futures[future]
                    task = task_map[task_id]
                    try:
                        result = future.result(timeout=timeout)
                        results[task_id] = result
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                        task.completed_at = time.time()
                        self._stats["tasks_completed"] += 1
                        logger.info(f"[AgentHub] Task {task_id} completed")
                    except Exception as e:
                        error_msg = str(e)
                        results[task_id] = {"error": error_msg, "status": "failed"}
                        task.status = TaskStatus.FAILED
                        task.result = {"error": error_msg}
                        task.completed_at = time.time()
                        logger.error(f"[AgentHub] Task {task_id} failed: {e}")

        return results

    def _execute_task_wrapper(self, task: DelegatedTask,
                              executor_fn: Callable[[DelegatedTask], Dict[str, Any]],
                              timeout: float) -> Dict[str, Any]:
        """Wrapper to execute a single task with error handling."""
        try:
            return executor_fn(task)
        except Exception as e:
            logger.error(f"[AgentHub] Task execution error: {e}")
            raise

    def _topological_layers(self, task_map: Dict[str, DelegatedTask],
                           dependencies: Dict[str, Set[str]]) -> List[List[str]]:
        """
        Organize tasks into layers for parallel execution.

        Each layer contains tasks whose dependencies are all in previous layers.
        Tasks within a layer can execute in parallel.
        """
        layers: List[List[str]] = []
        remaining = set(task_map.keys())
        completed = set()

        while remaining:
            # Find tasks with no unmet dependencies
            layer = []
            for task_id in remaining:
                deps = dependencies.get(task_id, set())
                # Task is ready if all its dependencies are completed
                if deps.issubset(completed):
                    layer.append(task_id)

            if not layer:
                # Circular dependency or missing dependency - include all remaining
                logger.warning(f"[AgentHub] Possible circular dependency, executing remaining tasks")
                layer = list(remaining)

            layers.append(layer)
            for task_id in layer:
                remaining.discard(task_id)
                completed.add(task_id)

        return layers

    def score_agent_for_capability(self, agent_name: str, required_capability: str) -> float:
        """
        Score how well an agent matches a required capability.

        Returns a score from 0.0 (no match) to 1.0 (exact match).
        """
        with self._lock:
            caps = self._agent_capabilities.get(agent_name, [])
            if not caps:
                return 0.0

            # Exact match
            if required_capability in caps:
                return 1.0

            # Partial/fuzzy match
            req_lower = required_capability.lower()
            for cap in caps:
                cap_lower = cap.lower()
                # Substring match
                if req_lower in cap_lower or cap_lower in req_lower:
                    return 0.7
                # Word overlap
                req_words = set(req_lower.split('_'))
                cap_words = set(cap_lower.split('_'))
                overlap = req_words & cap_words
                if overlap:
                    return 0.3 + 0.1 * len(overlap)

            return 0.0

    def find_best_agents(self, required_capability: str,
                        top_k: int = 3,
                        exclude: Optional[Set[str]] = None) -> List[Tuple[str, float]]:
        """
        Find the best agents for a capability, ranked by score.

        Args:
            required_capability: The capability needed
            top_k: Maximum number of agents to return
            exclude: Set of agent names to exclude

        Returns:
            List of (agent_name, score) tuples, sorted by score descending
        """
        exclude = exclude or set()
        scores = []

        with self._lock:
            for agent_name in self._agents.keys():
                if agent_name in exclude:
                    continue
                score = self.score_agent_for_capability(agent_name, required_capability)
                if score > 0:
                    scores.append((agent_name, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# Singleton
_hub_instance: Optional[AgentCollaborationHub] = None

def get_collaboration_hub() -> AgentCollaborationHub:
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = AgentCollaborationHub()
    return _hub_instance
