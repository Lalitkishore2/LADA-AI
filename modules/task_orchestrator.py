"""
LADA v9.0 - Advanced Task Orchestrator
Module 8: Intelligent task execution with parallel processing, 
dependency management, and real-time progress tracking.

Features:
- Parallel task execution with thread pools
- Task dependency graphs (DAG-based scheduling)
- Progress tracking with callbacks
- Subtask decomposition 
- Resource management
- Task prioritization
- Retry with exponential backoff
- Execution history and analytics
"""

import os
import json
import logging
import threading
import queue
import shlex
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from collections import defaultdict
import traceback

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING = "waiting"  # Waiting for dependencies
    PAUSED = "paused"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class Task:
    """Represents an executable task."""
    id: str
    name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    max_retries: int = 3
    retry_count: int = 0
    timeout_seconds: float = 300.0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    progress: float = 0.0  # 0.0 to 1.0
    subtasks: List['Task'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'action': self.action,
            'params': self.params,
            'priority': self.priority.name,
            'status': self.status.name,
            'dependencies': self.dependencies,
            'max_retries': self.max_retries,
            'retry_count': self.retry_count,
            'timeout_seconds': self.timeout_seconds,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': str(self.result)[:500] if self.result else None,
            'error': self.error,
            'progress': self.progress,
            'subtasks': [st.to_dict() for st in self.subtasks],
            'metadata': self.metadata
        }

    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None


@dataclass
class TaskGroup:
    """Group of related tasks."""
    id: str
    name: str
    tasks: List[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    parallel: bool = False  # Execute in parallel or sequential
    stop_on_failure: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskOrchestrator:
    """
    Advanced task orchestration engine.
    Manages parallel execution, dependencies, and progress tracking.
    """
    
    def __init__(self, max_workers: int = 4, history_file: str = None):
        """
        Initialize task orchestrator.
        
        Args:
            max_workers: Maximum parallel task threads
            history_file: Path to save execution history
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Task storage
        self.tasks: Dict[str, Task] = {}
        self.task_groups: Dict[str, TaskGroup] = {}
        self.futures: Dict[str, Future] = {}
        
        # Action registry
        self.actions: Dict[str, Callable] = {}
        
        # Progress callbacks
        self.progress_callbacks: List[Callable[[str, float, str], None]] = []
        self.completion_callbacks: List[Callable[[str, TaskStatus, Any], None]] = []
        
        # Statistics
        self.stats = {
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'total_duration': 0.0
        }
        
        # History
        self.history_file = Path(history_file or "data/task_history.json")
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.execution_history: List[Dict] = []
        self._load_history()
        
        # Thread safety
        self._lock = threading.Lock()
        self._running = True
        
        # Register built-in actions
        self._register_builtin_actions()
        
        logger.info(f"[TaskOrchestrator] Initialized with {max_workers} workers")
    
    def _register_builtin_actions(self):
        """Register built-in task actions."""
        self.register_action('log', self._action_log)
        self.register_action('sleep', self._action_sleep)
        self.register_action('shell', self._action_shell)
        self.register_action('http_request', self._action_http)
        self.register_action('file_read', self._action_file_read)
        self.register_action('file_write', self._action_file_write)
        self.register_action('composite', self._action_composite)
    
    def _action_log(self, message: str = "", level: str = "info", **kwargs) -> Dict:
        """Log a message."""
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"[Task] {message}")
        return {'success': True, 'message': message}
    
    def _action_sleep(self, seconds: float = 1.0, **kwargs) -> Dict:
        """Sleep for specified seconds."""
        time.sleep(seconds)
        return {'success': True, 'slept': seconds}
    
    def _action_shell(self, command: str, timeout: int = 60, **kwargs) -> Dict:
        """Execute a command with shell disabled by default."""
        import subprocess
        try:
            allow_shell = bool(kwargs.get('shell') or kwargs.get('allow_shell'))
            run_target: Any = command

            if allow_shell:
                if not isinstance(command, str):
                    return {
                        'success': False,
                        'error': 'Shell mode requires command as a string'
                    }
            elif isinstance(command, str):
                run_target = shlex.split(command, posix=(os.name != 'nt'))
                if not run_target:
                    return {
                        'success': False,
                        'error': 'Empty command'
                    }

            result = subprocess.run(
                run_target,
                shell=allow_shell,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode,
                'shell': allow_shell,
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out'}
        except ValueError as e:
            return {'success': False, 'error': f'Invalid command: {e}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _action_http(self, url: str, method: str = "GET", **kwargs) -> Dict:
        """Make HTTP request."""
        try:
            import urllib.request
            import urllib.error
            
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=30) as response:
                return {
                    'success': True,
                    'status_code': response.status,
                    'body': response.read().decode('utf-8')[:5000]
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _action_file_read(self, path: str, **kwargs) -> Dict:
        """Read file contents."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {'success': True, 'content': content, 'size': len(content)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _action_file_write(self, path: str, content: str, **kwargs) -> Dict:
        """Write content to file."""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'path': path, 'size': len(content)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _action_composite(self, subtasks: List[Dict], parallel: bool = False, **kwargs) -> Dict:
        """Execute composite task with subtasks."""
        results = []
        if parallel:
            # Execute subtasks in parallel
            group_id = f"composite_{datetime.now().timestamp()}"
            for i, st in enumerate(subtasks):
                task = self.create_task(
                    name=st.get('name', f'Subtask {i+1}'),
                    action=st.get('action', 'log'),
                    params=st.get('params', {}),
                    priority=TaskPriority.NORMAL
                )
                self.submit_task(task)
            # Wait for all
            self._wait_for_tasks([t['id'] for t in subtasks if 'id' in t])
        else:
            # Sequential execution
            for st in subtasks:
                action = st.get('action', 'log')
                if action in self.actions:
                    result = self.actions[action](**st.get('params', {}))
                    results.append(result)
                    if not result.get('success', True):
                        break
        return {'success': True, 'results': results}
    
    def register_action(self, name: str, handler: Callable):
        """
        Register a task action handler.
        
        Args:
            name: Action name
            handler: Callable that takes **params and returns Dict
        """
        self.actions[name] = handler
        logger.debug(f"[TaskOrchestrator] Registered action: {name}")
    
    def register_progress_callback(self, callback: Callable[[str, float, str], None]):
        """Register callback for task progress updates."""
        self.progress_callbacks.append(callback)
    
    def register_completion_callback(self, callback: Callable[[str, TaskStatus, Any], None]):
        """Register callback for task completion."""
        self.completion_callbacks.append(callback)
    
    def create_task(
        self,
        name: str,
        action: str,
        params: Dict[str, Any] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: List[str] = None,
        max_retries: int = 3,
        timeout: float = 300.0,
        metadata: Dict = None
    ) -> Task:
        """
        Create a new task.
        
        Args:
            name: Human-readable task name
            action: Action to execute (must be registered)
            params: Parameters to pass to action
            priority: Task priority
            dependencies: List of task IDs that must complete first
            max_retries: Maximum retry attempts
            timeout: Timeout in seconds
            metadata: Additional metadata
            
        Returns:
            Created Task object
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.tasks)}"
        
        task = Task(
            id=task_id,
            name=name,
            action=action,
            params=params or {},
            priority=priority,
            dependencies=dependencies or [],
            max_retries=max_retries,
            timeout_seconds=timeout,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.tasks[task_id] = task
            self.stats['total_tasks'] += 1
        
        logger.info(f"[TaskOrchestrator] Created task: {name} ({task_id})")
        return task
    
    def create_task_group(
        self,
        name: str,
        tasks: List[Dict[str, Any]],
        parallel: bool = False,
        stop_on_failure: bool = True
    ) -> TaskGroup:
        """
        Create a group of related tasks.
        
        Args:
            name: Group name
            tasks: List of task definitions
            parallel: Execute in parallel or sequential
            stop_on_failure: Stop group on first failure
            
        Returns:
            TaskGroup object
        """
        group_id = f"group_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        task_objects = []
        prev_task_id = None
        
        for i, task_def in enumerate(tasks):
            deps = task_def.get('dependencies', [])
            
            # If sequential, each task depends on previous
            if not parallel and prev_task_id and prev_task_id not in deps:
                deps.append(prev_task_id)
            
            task = self.create_task(
                name=task_def.get('name', f'{name} Step {i+1}'),
                action=task_def.get('action', 'log'),
                params=task_def.get('params', {}),
                priority=TaskPriority[task_def.get('priority', 'NORMAL').upper()],
                dependencies=deps,
                max_retries=task_def.get('max_retries', 3),
                timeout=task_def.get('timeout', 300.0),
                metadata={'group_id': group_id}
            )
            task_objects.append(task)
            prev_task_id = task.id
        
        group = TaskGroup(
            id=group_id,
            name=name,
            tasks=task_objects,
            parallel=parallel,
            stop_on_failure=stop_on_failure
        )
        
        with self._lock:
            self.task_groups[group_id] = group
        
        logger.info(f"[TaskOrchestrator] Created task group: {name} ({len(task_objects)} tasks)")
        return group
    
    def submit_task(self, task: Task) -> str:
        """
        Submit task for execution.
        
        Args:
            task: Task to submit
            
        Returns:
            Task ID
        """
        if task.id not in self.tasks:
            with self._lock:
                self.tasks[task.id] = task
        
        # Check dependencies
        if task.dependencies:
            pending_deps = [
                dep for dep in task.dependencies
                if dep in self.tasks and 
                self.tasks[dep].status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            ]
            if pending_deps:
                task.status = TaskStatus.WAITING
                logger.debug(f"[TaskOrchestrator] Task {task.id} waiting for: {pending_deps}")
                return task.id
        
        # Submit to executor
        task.status = TaskStatus.QUEUED
        future = self.executor.submit(self._execute_task, task)
        
        with self._lock:
            self.futures[task.id] = future
        
        return task.id
    
    def submit_group(self, group: TaskGroup) -> List[str]:
        """
        Submit all tasks in a group.
        
        Returns:
            List of task IDs
        """
        task_ids = []
        for task in group.tasks:
            task_id = self.submit_task(task)
            task_ids.append(task_id)
        return task_ids
    
    def _execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a single task (runs in thread pool)."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        self._notify_progress(task.id, 0.0, f"Starting: {task.name}")
        
        try:
            # Get action handler
            if task.action not in self.actions:
                raise ValueError(f"Unknown action: {task.action}")
            
            handler = self.actions[task.action]
            
            # Execute with timeout
            import concurrent.futures
            with ThreadPoolExecutor(max_workers=1) as exec:
                future = exec.submit(handler, **task.params)
                try:
                    result = future.result(timeout=task.timeout_seconds)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError(f"Task timed out after {task.timeout_seconds}s")
            
            task.result = result
            task.progress = 1.0
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            
            # Update stats
            with self._lock:
                self.stats['completed'] += 1
                if task.duration:
                    self.stats['total_duration'] += task.duration
            
            self._notify_progress(task.id, 1.0, f"Completed: {task.name}")
            self._notify_completion(task.id, TaskStatus.COMPLETED, result)
            
            # Check for waiting tasks that depend on this one
            self._process_waiting_tasks(task.id)
            
            # Record history
            self._record_history(task)
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[TaskOrchestrator] Task {task.id} failed: {error_msg}")
            
            # Retry logic
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                
                # Exponential backoff
                wait_time = 2 ** task.retry_count
                logger.info(f"[TaskOrchestrator] Retrying task {task.id} in {wait_time}s (attempt {task.retry_count})")
                time.sleep(wait_time)
                
                return self._execute_task(task)
            
            # Final failure
            task.status = TaskStatus.FAILED
            task.error = error_msg
            task.completed_at = datetime.now()
            
            with self._lock:
                self.stats['failed'] += 1
            
            self._notify_progress(task.id, task.progress, f"Failed: {task.name}")
            self._notify_completion(task.id, TaskStatus.FAILED, error_msg)
            self._record_history(task)
            
            return {'success': False, 'error': error_msg}
    
    def _process_waiting_tasks(self, completed_task_id: str):
        """Check and run tasks waiting for completed task."""
        with self._lock:
            waiting_tasks = [
                t for t in self.tasks.values()
                if t.status == TaskStatus.WAITING and completed_task_id in t.dependencies
            ]
        
        for task in waiting_tasks:
            # Check if all dependencies are complete
            all_deps_done = all(
                self.tasks.get(dep, Task(id="", name="", action="")).status == TaskStatus.COMPLETED
                for dep in task.dependencies
            )
            if all_deps_done:
                self.submit_task(task)
    
    def _notify_progress(self, task_id: str, progress: float, message: str):
        """Notify progress callbacks."""
        for callback in self.progress_callbacks:
            try:
                callback(task_id, progress, message)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    def _notify_completion(self, task_id: str, status: TaskStatus, result: Any):
        """Notify completion callbacks."""
        for callback in self.completion_callbacks:
            try:
                callback(task_id, status, result)
            except Exception as e:
                logger.warning(f"Completion callback error: {e}")
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get detailed task status."""
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}
        
        return {
            'success': True,
            'id': task.id,
            'name': task.name,
            'status': task.status.value,
            'progress': task.progress,
            'duration': task.duration,
            'result': task.result,
            'error': task.error,
            'retries': task.retry_count
        }
    
    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Cancel a pending or running task."""
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}
        
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return {'success': False, 'error': f'Task already {task.status.value}'}
        
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        
        # Cancel future if exists
        future = self.futures.get(task_id)
        if future:
            future.cancel()
        
        logger.info(f"[TaskOrchestrator] Cancelled task: {task_id}")
        return {'success': True, 'task_id': task_id}
    
    def pause_task(self, task_id: str) -> Dict[str, Any]:
        """Pause a running task (if supported)."""
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}
        
        if task.status != TaskStatus.RUNNING:
            return {'success': False, 'error': 'Task not running'}
        
        task.status = TaskStatus.PAUSED
        return {'success': True, 'task_id': task_id}
    
    def resume_task(self, task_id: str) -> Dict[str, Any]:
        """Resume a paused task."""
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}
        
        if task.status != TaskStatus.PAUSED:
            return {'success': False, 'error': 'Task not paused'}
        
        return self.submit_task(task)
    
    def list_tasks(self, status: TaskStatus = None) -> List[Dict]:
        """List all tasks, optionally filtered by status."""
        tasks = []
        for task in self.tasks.values():
            if status is None or task.status == status:
                tasks.append({
                    'id': task.id,
                    'name': task.name,
                    'status': task.status.value,
                    'priority': task.priority.value,
                    'progress': task.progress,
                    'created_at': task.created_at.isoformat()
                })
        return sorted(tasks, key=lambda x: x['created_at'], reverse=True)
    
    def get_running_tasks(self) -> List[Dict]:
        """Get all currently running tasks."""
        return self.list_tasks(TaskStatus.RUNNING)
    
    def get_pending_tasks(self) -> List[Dict]:
        """Get all pending/queued tasks."""
        return [
            t for t in self.list_tasks()
            if t['status'] in ['pending', 'queued', 'waiting']
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        with self._lock:
            return {
                **self.stats,
                'active_tasks': len(self.get_running_tasks()),
                'pending_tasks': len(self.get_pending_tasks()),
                'success_rate': (
                    self.stats['completed'] / max(1, self.stats['completed'] + self.stats['failed'])
                ) * 100,
                'avg_duration': (
                    self.stats['total_duration'] / max(1, self.stats['completed'])
                )
            }
    
    def wait_for_task(self, task_id: str, timeout: float = None) -> Dict[str, Any]:
        """Wait for a task to complete."""
        future = self.futures.get(task_id)
        if future:
            try:
                result = future.result(timeout=timeout)
                return {'success': True, 'result': result}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': 'Task not found or not submitted'}
    
    def wait_for_all(self, timeout: float = None) -> Dict[str, Any]:
        """Wait for all submitted tasks to complete."""
        start_time = time.time()
        
        while True:
            running = self.get_running_tasks()
            pending = self.get_pending_tasks()
            
            if not running and not pending:
                break
            
            if timeout and (time.time() - start_time) > timeout:
                return {
                    'success': False,
                    'error': 'Timeout waiting for tasks',
                    'running': len(running),
                    'pending': len(pending)
                }
            
            time.sleep(0.5)
        
        return {
            'success': True,
            'stats': self.get_statistics()
        }
    
    def _wait_for_tasks(self, task_ids: List[str], timeout: float = None):
        """Wait for specific tasks to complete."""
        for task_id in task_ids:
            self.wait_for_task(task_id, timeout)
    
    def _record_history(self, task: Task):
        """Record task execution in history."""
        record = {
            'task_id': task.id,
            'name': task.name,
            'action': task.action,
            'status': task.status.value,
            'duration': task.duration,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'retries': task.retry_count,
            'error': task.error
        }
        
        with self._lock:
            self.execution_history.append(record)
            # Keep last 1000 records
            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-1000:]
        
        self._save_history()
    
    def _save_history(self):
        """Save execution history to file."""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.execution_history[-100:], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")
    
    def _load_history(self):
        """Load execution history from file."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.execution_history = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get recent execution history."""
        return self.execution_history[-limit:]
    
    def clear_completed(self):
        """Clear completed tasks from memory."""
        with self._lock:
            to_remove = [
                task_id for task_id, task in self.tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            ]
            for task_id in to_remove:
                del self.tasks[task_id]
                if task_id in self.futures:
                    del self.futures[task_id]
        
        return {'success': True, 'cleared': len(to_remove)}
    
    def shutdown(self, wait: bool = True, timeout: float = 30):
        """Shutdown the orchestrator."""
        self._running = False
        self.executor.shutdown(wait=wait)
        self._save_history()
        logger.info("[TaskOrchestrator] Shutdown complete")
    
    # =====================================================
    # High-Level Task Templates
    # =====================================================
    
    def run_batch(
        self,
        action: str,
        items: List[Any],
        param_key: str = 'item',
        parallel: bool = True,
        max_concurrent: int = None
    ) -> Dict[str, Any]:
        """
        Run the same action on multiple items.
        
        Args:
            action: Action to execute
            items: List of items to process
            param_key: Parameter name for each item
            parallel: Run in parallel
            max_concurrent: Limit concurrent tasks
        """
        tasks = []
        for i, item in enumerate(items):
            task = self.create_task(
                name=f"Batch {i+1}/{len(items)}",
                action=action,
                params={param_key: item}
            )
            tasks.append(task)
        
        if parallel:
            for task in tasks:
                self.submit_task(task)
            self.wait_for_all()
        else:
            for task in tasks:
                self.submit_task(task)
                self.wait_for_task(task.id)
        
        results = [t.result for t in tasks]
        success = all(t.status == TaskStatus.COMPLETED for t in tasks)
        
        return {
            'success': success,
            'total': len(items),
            'completed': sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            'failed': sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            'results': results
        }
    
    def run_pipeline(
        self,
        steps: List[Dict[str, Any]],
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Run a sequential pipeline where each step can use results from previous steps.
        
        Args:
            steps: List of step definitions with 'action', 'params', 'output_key'
            context: Initial context variables
        """
        pipeline_context = context or {}
        results = []
        
        for i, step in enumerate(steps):
            step_name = step.get('name', f'Step {i+1}')
            action = step.get('action')
            params = step.get('params', {}).copy()
            output_key = step.get('output_key')
            
            # Substitute context variables in params
            for key, value in params.items():
                if isinstance(value, str) and value.startswith('$'):
                    var_name = value[1:]
                    if var_name in pipeline_context:
                        params[key] = pipeline_context[var_name]
            
            # Create and run task
            task = self.create_task(
                name=step_name,
                action=action,
                params=params,
                metadata={'pipeline_step': i}
            )
            self.submit_task(task)
            self.wait_for_task(task.id)
            
            if task.status != TaskStatus.COMPLETED:
                return {
                    'success': False,
                    'failed_step': i,
                    'error': task.error,
                    'results': results
                }
            
            results.append(task.result)
            
            # Store output in context
            if output_key and task.result:
                if isinstance(task.result, dict):
                    pipeline_context[output_key] = task.result.get('content', task.result)
                else:
                    pipeline_context[output_key] = task.result
        
        return {
            'success': True,
            'steps': len(steps),
            'results': results,
            'context': pipeline_context
        }
    
    def run_workflow_parallel(
        self,
        branches: List[List[Dict[str, Any]]],
        join_action: str = None,
        join_params: Dict = None
    ) -> Dict[str, Any]:
        """
        Run multiple workflow branches in parallel, then optionally join results.
        
        Args:
            branches: List of pipelines to run in parallel
            join_action: Optional action to run with all branch results
            join_params: Parameters for join action
        """
        branch_tasks = []
        
        # Submit all branches
        for i, branch in enumerate(branches):
            group = self.create_task_group(
                name=f"Branch {i+1}",
                tasks=branch,
                parallel=False
            )
            self.submit_group(group)
            branch_tasks.append(group)
        
        # Wait for all branches
        self.wait_for_all()
        
        # Collect results
        branch_results = []
        for group in branch_tasks:
            group_results = [t.result for t in group.tasks if t.status == TaskStatus.COMPLETED]
            branch_results.append(group_results)
        
        # Run join action if specified
        join_result = None
        if join_action:
            params = join_params or {}
            params['branch_results'] = branch_results
            
            join_task = self.create_task(
                name="Join Results",
                action=join_action,
                params=params
            )
            self.submit_task(join_task)
            self.wait_for_task(join_task.id)
            join_result = join_task.result
        
        return {
            'success': True,
            'branches': len(branches),
            'branch_results': branch_results,
            'join_result': join_result
        }


# Singleton instance
_orchestrator = None

def get_task_orchestrator(max_workers: int = 4) -> TaskOrchestrator:
    """Get or create task orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TaskOrchestrator(max_workers=max_workers)
    return _orchestrator

def create_task_orchestrator(max_workers: int = 4) -> TaskOrchestrator:
    """Create a new task orchestrator instance."""
    return TaskOrchestrator(max_workers=max_workers)


# =====================================================
# QUICK FUNCTIONS
# =====================================================

def run_task(name: str, action: str, **params) -> Dict[str, Any]:
    """Quick function to run a single task."""
    orch = get_task_orchestrator()
    task = orch.create_task(name=name, action=action, params=params)
    orch.submit_task(task)
    orch.wait_for_task(task.id)
    return orch.get_task_status(task.id)

def run_batch_tasks(action: str, items: List[Any], parallel: bool = True) -> Dict[str, Any]:
    """Quick function to run batch tasks."""
    return get_task_orchestrator().run_batch(action, items, parallel=parallel)


# =====================================================
# EXAMPLE USAGE
# =====================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Task Orchestrator Test")
    print("=" * 60)
    
    # Create orchestrator
    orchestrator = TaskOrchestrator(max_workers=4)
    
    # Test 1: Simple task
    print("\n📋 Test 1: Simple Task")
    task1 = orchestrator.create_task(
        name="Log Test",
        action="log",
        params={"message": "Hello from task orchestrator!"}
    )
    orchestrator.submit_task(task1)
    orchestrator.wait_for_task(task1.id)
    status = orchestrator.get_task_status(task1.id)
    print(f"   Status: {status['status']}")
    
    # Test 2: Parallel tasks
    print("\n📋 Test 2: Parallel Tasks")
    for i in range(3):
        task = orchestrator.create_task(
            name=f"Parallel Task {i+1}",
            action="sleep",
            params={"seconds": 0.5}
        )
        orchestrator.submit_task(task)
    
    orchestrator.wait_for_all()
    stats = orchestrator.get_statistics()
    print(f"   Completed: {stats['completed']} tasks")
    print(f"   Success rate: {stats['success_rate']:.1f}%")
    
    # Test 3: Task Group
    print("\n📋 Test 3: Task Group (Sequential)")
    group = orchestrator.create_task_group(
        name="Setup Group",
        tasks=[
            {"name": "Step 1", "action": "log", "params": {"message": "Step 1 executing"}},
            {"name": "Step 2", "action": "log", "params": {"message": "Step 2 executing"}},
            {"name": "Step 3", "action": "log", "params": {"message": "Step 3 executing"}}
        ],
        parallel=False
    )
    orchestrator.submit_group(group)
    orchestrator.wait_for_all()
    print(f"   Group tasks: {len(group.tasks)}")
    
    # Test 4: Pipeline
    print("\n📋 Test 4: Pipeline with Context")
    result = orchestrator.run_pipeline([
        {"name": "Read Config", "action": "log", "params": {"message": "Reading config..."}, "output_key": "config"},
        {"name": "Process", "action": "log", "params": {"message": "Processing..."}, "output_key": "data"},
        {"name": "Save", "action": "log", "params": {"message": "Saving..."}}
    ])
    print(f"   Pipeline success: {result['success']}")
    print(f"   Steps completed: {result['steps']}")
    
    # Final stats
    print("\n" + "=" * 60)
    print("📊 Final Statistics")
    stats = orchestrator.get_statistics()
    print(f"   Total tasks: {stats['total_tasks']}")
    print(f"   Completed: {stats['completed']}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Success rate: {stats['success_rate']:.1f}%")
    print(f"   Avg duration: {stats['avg_duration']:.2f}s")
    
    # Cleanup
    orchestrator.shutdown()
    
    print("\n✅ Task Orchestrator tests complete!")
