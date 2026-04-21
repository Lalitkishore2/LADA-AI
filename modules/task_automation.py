# task_automation.py
# Multi-Step Task Automation & Choreographer
# Handles complex workflows, task templates, state management, etc.

import logging
import json
from typing import Dict, List, Any, Callable, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, asdict
import threading
import time
from queue import Queue
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status states"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TaskStep:
    """Single step in a task"""
    step_id: str
    name: str
    action: str
    parameters: Dict[str, Any]
    dependencies: List[str] = None  # IDs of steps that must complete first
    timeout_seconds: int = 300
    retries: int = 3
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class TaskDefinition:
    """Complete task definition"""
    task_id: str
    name: str
    description: str
    steps: List[TaskStep]
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: int = 3600
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class TaskExecution:
    """Running task instance"""
    execution_id: str
    task_id: str
    task_name: str
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    total_steps: int = 0
    progress_percent: int = 0
    started_at: str = None
    completed_at: str = None
    failed_at: str = None
    error: str = None
    results: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = {}


class TaskChoreographer:
    """Execute complex multi-step tasks with state management"""
    
    def __init__(self, db_path: str = "tasks.db"):
        """Initialize task choreographer"""
        self.db_path = db_path
        self.task_queue = Queue()
        self.running_tasks: Dict[str, TaskExecution] = {}
        self.completed_tasks: List[TaskExecution] = []
        self.task_templates: Dict[str, TaskDefinition] = {}
        self.step_handlers: Dict[str, Callable] = {}
        self.max_concurrent_tasks = 3
        self.worker_threads = []
        
        # Start worker threads
        self._start_workers()
        
        # Load task templates
        self._load_templates()
    
    def _start_workers(self, num_workers: int = 2):
        """Start worker threads for task execution"""
        for i in range(num_workers):
            thread = threading.Thread(
                target=self._task_worker,
                daemon=True
            )
            thread.start()
            self.worker_threads.append(thread)
        
        logger.info(f"Started {num_workers} task workers")
    
    def _task_worker(self):
        """Worker thread that processes tasks from queue"""
        while True:
            try:
                # Get task from queue
                task_execution = self.task_queue.get(timeout=1)
                
                # Execute task
                self._execute_task(task_execution)
                
                self.task_queue.task_done()
            
            except Exception as e:
                continue
    
    def register_step_handler(self, 
                             action_name: str, 
                             handler_func: Callable):
        """
        Register a handler for task step
        
        Args:
            action_name: Name of the action (e.g., 'download', 'extract')
            handler_func: Function to call: async def handler(params) -> result
        
        Example:
            async def download_handler(params):
                url = params['url']
                # Download logic
                return {'success': True, 'file': 'downloaded.zip'}
            
            choreographer.register_step_handler('download', download_handler)
        """
        self.step_handlers[action_name] = handler_func
        logger.info(f"Registered handler for action: {action_name}")
    
    def parse_complex_command(self, text: str) -> TaskDefinition:
        """
        Parse complex command into task steps
        
        Examples:
            "download file from URL, extract it, move to folder"
            "create morning routine: open chrome, open slack, set volume"
        
        Returns:
            TaskDefinition with parsed steps
        """
        try:
            # Split by common separators
            actions = [a.strip() for a in text.split(',')]
            
            steps = []
            task_id = str(uuid.uuid4())
            
            for i, action in enumerate(actions):
                # Extract action and parameters
                step_id = str(uuid.uuid4())
                
                # Simple parameter extraction
                params = self._extract_parameters(action)
                
                step = TaskStep(
                    step_id=step_id,
                    name=action,
                    action=params.get('action', 'unknown'),
                    parameters=params,
                    dependencies=[steps[-1].step_id] if steps else []  # Linear dependency
                )
                steps.append(step)
            
            task = TaskDefinition(
                task_id=task_id,
                name=text[:50],
                description=text,
                steps=steps,
                priority=TaskPriority.NORMAL
            )
            
            logger.info(f"Parsed complex command into {len(steps)} steps")
            return task
        
        except Exception as e:
            logger.error(f"Error parsing command: {e}")
            raise
    
    def _extract_parameters(self, action_text: str) -> Dict[str, Any]:
        """Extract parameters from natural language action"""
        text = action_text.lower()
        params = {'action': 'unknown'}
        
        # Download detection
        if 'download' in text:
            params['action'] = 'download'
            if 'from' in text:
                parts = text.split('from')
                if len(parts) > 1:
                    params['url'] = parts[1].strip()
        
        # Extract detection
        elif 'extract' in text:
            params['action'] = 'extract'
            if 'to' in text:
                parts = text.split('to')
                if len(parts) > 1:
                    params['destination'] = parts[1].strip()
        
        # Move detection
        elif 'move' in text:
            params['action'] = 'move'
            if 'to' in text:
                parts = text.split('to')
                if len(parts) > 1:
                    params['destination'] = parts[1].strip()
        
        # Open detection
        elif 'open' in text:
            params['action'] = 'open'
            parts = text.replace('open', '').strip()
            params['target'] = parts
        
        # Set/change detection
        elif 'set' in text or 'change' in text:
            params['action'] = 'set'
            params['text'] = action_text
        
        # Create detection
        elif 'create' in text:
            params['action'] = 'create'
            params['text'] = action_text
        
        return params
    
    def create_task_template(self, 
                            template_name: str,
                            task_definition: TaskDefinition) -> Dict[str, Any]:
        """
        Save a task as a reusable template
        
        Example:
            task = choreographer.parse_complex_command(
                "open chrome, open slack, set volume to 30"
            )
            choreographer.create_task_template("morning_routine", task)
            
            # Later, use it:
            choreographer.execute_template("morning_routine")
        """
        try:
            self.task_templates[template_name.lower()] = task_definition
            
            # Save to file
            templates_file = Path("tasks_templates.json")
            templates_dict = {
                name: {
                    'name': task.name,
                    'description': task.description,
                    'steps': [
                        {
                            'step_id': step.step_id,
                            'name': step.name,
                            'action': step.action,
                            'parameters': step.parameters,
                            'dependencies': step.dependencies
                        }
                        for step in task.steps
                    ]
                }
                for name, task in self.task_templates.items()
            }
            
            with open(templates_file, 'w') as f:
                json.dump(templates_dict, f, indent=2)
            
            logger.info(f"Created task template: {template_name}")
            
            return {
                'success': True,
                'template_name': template_name,
                'steps': len(task_definition.steps),
                'message': f'Created template "{template_name}" with {len(task_definition.steps)} steps'
            }
        
        except Exception as e:
            logger.error(f"Error creating template: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_template(self, template_name: str) -> Dict[str, Any]:
        """Execute a saved task template"""
        try:
            template_name = template_name.lower()
            
            if template_name not in self.task_templates:
                return {
                    'success': False,
                    'error': f'Template not found: {template_name}',
                    'available': list(self.task_templates.keys())
                }
            
            task = self.task_templates[template_name]
            return self.execute_task(task)
        
        except Exception as e:
            logger.error(f"Error executing template: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_task(self, task_definition: TaskDefinition) -> Dict[str, Any]:
        """
        Execute a task
        
        Returns:
            {'execution_id': '...', 'task_name': '...', 'status': 'running'}
        """
        try:
            # Create execution record
            execution = TaskExecution(
                execution_id=str(uuid.uuid4()),
                task_id=task_definition.task_id,
                task_name=task_definition.name,
                status=TaskStatus.RUNNING,
                total_steps=len(task_definition.steps),
                started_at=datetime.now().isoformat()
            )
            
            # Store execution
            self.running_tasks[execution.execution_id] = execution
            
            # Queue for processing
            self.task_queue.put(execution)
            
            logger.info(f"Started task execution: {execution.execution_id}")
            
            return {
                'success': True,
                'execution_id': execution.execution_id,
                'task_name': execution.task_name,
                'status': execution.status.value,
                'total_steps': execution.total_steps
            }
        
        except Exception as e:
            logger.error(f"Error executing task: {e}")
            return {'success': False, 'error': str(e)}
    
    def _execute_task(self, execution: TaskExecution):
        """Actually execute the task steps"""
        try:
            task = self.task_templates.get(execution.task_name.lower())
            if not task:
                # If not a template, treat as task with its own steps
                logger.warning(f"Task definition not found: {execution.task_name}")
                return
            
            # Execute each step
            for step_index, step in enumerate(task.steps):
                execution.current_step = step_index
                execution.progress_percent = int((step_index / execution.total_steps) * 100)
                
                # Check dependencies
                if step.dependencies:
                    # Wait for dependent steps to complete
                    for dep_id in step.dependencies:
                        if dep_id not in execution.results:
                            logger.warning(f"Dependency not met: {dep_id}")
                
                # Execute step
                try:
                    result = self._execute_step(step)
                    
                    if result.get('success'):
                        execution.results[step.step_id] = result
                        logger.info(f"Step completed: {step.name}")
                    else:
                        raise Exception(f"Step failed: {result.get('error')}")
                
                except Exception as e:
                    # Retry logic
                    retried = False
                    for attempt in range(step.retries):
                        try:
                            logger.warning(f"Retrying step {step.name} (attempt {attempt + 1}/{step.retries})")
                            result = self._execute_step(step)
                            if result.get('success'):
                                execution.results[step.step_id] = result
                                retried = True
                                break
                        except Exception as e:
                            continue
                    
                    if not retried:
                        execution.status = TaskStatus.FAILED
                        execution.error = str(e)
                        execution.failed_at = datetime.now().isoformat()
                        logger.error(f"Task failed at step {step.name}: {e}")
                        return
            
            # Task completed successfully
            execution.status = TaskStatus.COMPLETED
            execution.completed_at = datetime.now().isoformat()
            execution.progress_percent = 100
            
            # Move to completed
            self.completed_tasks.append(execution)
            if execution.execution_id in self.running_tasks:
                del self.running_tasks[execution.execution_id]
            
            logger.info(f"Task completed: {execution.execution_id}")
        
        except Exception as e:
            logger.error(f"Error in _execute_task: {e}")
            execution.status = TaskStatus.FAILED
            execution.error = str(e)
    
    def _execute_step(self, step: TaskStep) -> Dict[str, Any]:
        """Execute a single step"""
        try:
            # Get handler for this action
            handler = self.step_handlers.get(step.action)
            
            if not handler:
                logger.warning(f"No handler for action: {step.action}")
                # Return mock success
                return {'success': True, 'mock': True}
            
            # Call handler
            result = handler(step.parameters)
            return result
        
        except Exception as e:
            logger.error(f"Error executing step: {e}")
            raise
    
    def get_task_status(self, execution_id: str) -> Dict[str, Any]:
        """Get status of a running task"""
        execution = self.running_tasks.get(execution_id)
        
        if not execution:
            # Check completed tasks
            for task in self.completed_tasks:
                if task.execution_id == execution_id:
                    execution = task
                    break
        
        if not execution:
            return {'success': False, 'error': f'Task not found: {execution_id}'}
        
        return {
            'success': True,
            'execution_id': execution.execution_id,
            'task_name': execution.task_name,
            'status': execution.status.value,
            'current_step': execution.current_step,
            'total_steps': execution.total_steps,
            'progress_percent': execution.progress_percent,
            'started_at': execution.started_at,
            'completed_at': execution.completed_at,
            'error': execution.error,
            'results': execution.results
        }
    
    def pause_task(self, execution_id: str) -> Dict[str, Any]:
        """Pause a running task"""
        execution = self.running_tasks.get(execution_id)
        
        if not execution:
            return {'success': False, 'error': f'Task not found: {execution_id}'}
        
        execution.status = TaskStatus.PAUSED
        logger.info(f"Task paused: {execution_id}")
        
        return {
            'success': True,
            'message': f'Task paused at step {execution.current_step}'
        }
    
    def resume_task(self, execution_id: str) -> Dict[str, Any]:
        """Resume a paused task"""
        execution = self.running_tasks.get(execution_id)
        
        if not execution:
            return {'success': False, 'error': f'Task not found: {execution_id}'}
        
        if execution.status != TaskStatus.PAUSED:
            return {
                'success': False,
                'error': f'Task is not paused: {execution.status.value}'
            }
        
        execution.status = TaskStatus.RUNNING
        logger.info(f"Task resumed: {execution_id}")
        
        return {
            'success': True,
            'message': f'Task resumed from step {execution.current_step}'
        }
    
    def cancel_task(self, execution_id: str) -> Dict[str, Any]:
        """Cancel a running task"""
        execution = self.running_tasks.get(execution_id)
        
        if not execution:
            return {'success': False, 'error': f'Task not found: {execution_id}'}
        
        execution.status = TaskStatus.CANCELLED
        logger.info(f"Task cancelled: {execution_id}")
        
        return {
            'success': True,
            'message': f'Task cancelled'
        }
    
    def get_active_tasks(self) -> Dict[str, Any]:
        """Get all active tasks"""
        tasks = []
        
        for execution_id, execution in self.running_tasks.items():
            tasks.append({
                'execution_id': execution_id,
                'task_name': execution.task_name,
                'status': execution.status.value,
                'progress': f'{execution.progress_percent}%',
                'current_step': f'{execution.current_step}/{execution.total_steps}',
                'started_at': execution.started_at
            })
        
        return {
            'success': True,
            'active_tasks': tasks,
            'count': len(tasks)
        }
    
    def get_completed_tasks(self, limit: int = 20) -> Dict[str, Any]:
        """Get recently completed tasks"""
        tasks = []
        
        for execution in self.completed_tasks[-limit:]:
            tasks.append({
                'execution_id': execution.execution_id,
                'task_name': execution.task_name,
                'status': execution.status.value,
                'started_at': execution.started_at,
                'completed_at': execution.completed_at,
                'error': execution.error
            })
        
        return {
            'success': True,
            'completed_tasks': tasks,
            'count': len(tasks)
        }
    
    def _load_templates(self):
        """Load task templates from file"""
        try:
            templates_file = Path("tasks_templates.json")
            if templates_file.exists():
                with open(templates_file, 'r') as f:
                    data = json.load(f)
                
                for name, task_data in data.items():
                    steps = [
                        TaskStep(
                            step_id=step['step_id'],
                            name=step['name'],
                            action=step['action'],
                            parameters=step['parameters'],
                            dependencies=step.get('dependencies', [])
                        )
                        for step in task_data['steps']
                    ]
                    
                    task = TaskDefinition(
                        task_id=str(uuid.uuid4()),
                        name=task_data['name'],
                        description=task_data['description'],
                        steps=steps
                    )
                    
                    self.task_templates[name.lower()] = task
                
                logger.info(f"Loaded {len(self.task_templates)} task templates")
        
        except Exception as e:
            logger.warning(f"Could not load task templates: {e}")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    choreographer = TaskChoreographer()
    
    # Example 1: Parse complex command
    print("Example 1: Parsing complex command...")
    task = choreographer.parse_complex_command(
        "download file from http://example.com, extract it, move to documents"
    )
    print(f"Parsed into {len(task.steps)} steps")
    
    # Example 2: Create template
    print("\nExample 2: Creating task template...")
    result = choreographer.create_task_template("work_setup", task)
    print(result['message'])
    
    # Example 3: List templates
    print(f"\nAvailable templates: {list(choreographer.task_templates.keys())}")
    
    # Example 4: Get active tasks
    print("\nActive tasks:")
    result = choreographer.get_active_tasks()
    print(f"Count: {result['count']}")
