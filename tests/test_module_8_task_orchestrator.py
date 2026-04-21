import pytest
from unittest.mock import MagicMock, patch
from modules.task_orchestrator import TaskOrchestrator, TaskStatus, TaskPriority
import time

class TestTaskOrchestrator:
    
    @pytest.fixture
    def orchestrator(self):
        orchestrator = TaskOrchestrator(max_workers=2, history_file="tests/test_history.json")
        return orchestrator

    def test_create_task(self, orchestrator):
        """Test creating a task"""
        task = orchestrator.create_task(
            name="Test Task",
            action="log",
            params={"message": "Hello"},
            priority=TaskPriority.HIGH
        )
        
        assert task.name == "Test Task"
        assert task.action == "log"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
        assert task.id in orchestrator.tasks

    def test_submit_task(self, orchestrator):
        """Test submitting a task"""
        task = orchestrator.create_task(
            name="Run Task",
            action="log",
            params={"message": "Running"}
        )
        
        task_id = orchestrator.submit_task(task)
        
        assert task_id == task.id
        # Wait for completion
        time.sleep(0.1)
        assert task.status == TaskStatus.COMPLETED
        assert task.result['success'] is True

    def test_create_task_group(self, orchestrator):
        """Test creating a task group"""
        tasks = [
            {'name': 'Task 1', 'action': 'log', 'params': {'message': '1'}},
            {'name': 'Task 2', 'action': 'log', 'params': {'message': '2'}}
        ]
        
        group = orchestrator.create_task_group("Test Group", tasks, parallel=False)
        
        assert len(group.tasks) == 2
        assert group.name == "Test Group"
        assert group.id in orchestrator.task_groups

    def test_submit_group(self, orchestrator):
        """Test submitting a group"""
        tasks = [
            {'name': 'Task 1', 'action': 'log', 'params': {'message': '1'}},
            {'name': 'Task 2', 'action': 'log', 'params': {'message': '2'}}
        ]
        group = orchestrator.create_task_group("Run Group", tasks)
        
        task_ids = orchestrator.submit_group(group)
        
        assert len(task_ids) == 2
        time.sleep(0.2)
        for task in group.tasks:
            assert task.status == TaskStatus.COMPLETED

    def test_get_task_status(self, orchestrator):
        """Test getting task status"""
        task = orchestrator.create_task("Status Task", "log")
        orchestrator.submit_task(task)
        time.sleep(0.1)
        
        status = orchestrator.get_task_status(task.id)
        
        assert status['success'] is True
        assert status['id'] == task.id
        assert status['status'] == 'completed'

    def test_cancel_task(self, orchestrator):
        """Test cancelling a task"""
        # Create a long running task
        task = orchestrator.create_task(
            name="Long Task",
            action="sleep",
            params={"seconds": 5}
        )
        orchestrator.submit_task(task)
        
        result = orchestrator.cancel_task(task.id)
        
        assert result['success'] is True
        assert task.status == TaskStatus.CANCELLED

    def test_task_dependencies(self, orchestrator):
        """Test task dependencies"""
        task1 = orchestrator.create_task("Task 1", "log")
        task2 = orchestrator.create_task("Task 2", "log", dependencies=[task1.id])
        
        orchestrator.submit_task(task2)
        assert task2.status == TaskStatus.WAITING
        
        orchestrator.submit_task(task1)
        time.sleep(0.2)
        
        assert task1.status == TaskStatus.COMPLETED
        assert task2.status == TaskStatus.COMPLETED

    def test_register_action(self, orchestrator):
        """Test registering custom action"""
        def custom_action(value):
            return {'success': True, 'value': value * 2}
            
        orchestrator.register_action('double', custom_action)
        
        task = orchestrator.create_task("Custom", "double", params={'value': 5})
        orchestrator.submit_task(task)
        time.sleep(0.1)
        
        assert task.result['value'] == 10

    def test_shell_action_defaults_to_shellless_execution(self, orchestrator):
        """Shell action should avoid shell=True unless explicitly requested."""
        captured = {}

        class _Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def _fake_run(command, **kwargs):
            captured['command'] = command
            captured['shell'] = kwargs.get('shell')
            return _Proc()

        with patch('subprocess.run', side_effect=_fake_run):
            result = orchestrator._action_shell('echo hello world')

        assert result['success'] is True
        assert result['shell'] is False
        assert captured['shell'] is False
        assert isinstance(captured['command'], list)

    def test_shell_action_supports_explicit_shell_opt_in(self, orchestrator):
        """Advanced shell features remain available with explicit opt-in."""
        captured = {}

        class _Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def _fake_run(command, **kwargs):
            captured['command'] = command
            captured['shell'] = kwargs.get('shell')
            return _Proc()

        with patch('subprocess.run', side_effect=_fake_run):
            result = orchestrator._action_shell('echo hi && echo there', shell=True)

        assert result['success'] is True
        assert result['shell'] is True
        assert captured['shell'] is True
        assert captured['command'] == 'echo hi && echo there'
