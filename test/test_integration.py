import pytest
from unittest.mock import MagicMock, patch
from modules.advanced_system_control import AdvancedSystemController
from modules.window_manager import WindowManager
from modules.task_automation import TaskChoreographer, TaskDefinition, TaskStep

@pytest.mark.integration
class TestIntegration:
    
    @pytest.fixture
    def system(self):
        return AdvancedSystemController()
        
    @pytest.fixture
    def window(self):
        return WindowManager()
        
    @pytest.fixture
    def task_choreographer(self):
        return TaskChoreographer()

    def test_workflow_create_file_and_open(self, system, window, temp_test_dir):
        """Test creating a file and then opening it"""
        # 1. Create file
        filename = "integration_test.txt"
        content = "Integration Content"
        create_result = system.create_file(filename, content, path=temp_test_dir)
        assert create_result['success'] is True
        
        # 2. Open file (mocked)
        with patch('subprocess.Popen') as mock_popen, \
             patch('pathlib.Path.exists', return_value=True):
            window.open_application("notepad", args=[create_result['path']])
            mock_popen.assert_called()

    def test_task_orchestration_workflow(self, task_choreographer):
        """Test a multi-step task workflow"""
        # Define a complex task
        complex_task = {
            'id': 'int_1',
            'name': 'Integration Task',
            'description': 'Test task',
            'steps': [
                {'step_id': 's1', 'name': 'Open Browser', 'action': 'open_browser', 'parameters': {'url': 'google.com'}},
                {'step_id': 's2', 'name': 'Search', 'action': 'search', 'parameters': {'query': 'python'}}
            ]
        }
        
        # Mock execution
        with patch.object(task_choreographer, '_execute_step') as mock_step:
            mock_step.return_value = {'success': True}
            
            steps = [TaskStep(**s) for s in complex_task['steps']]
            task_def = TaskDefinition(
                task_id=complex_task['id'],
                name=complex_task['name'],
                description=complex_task['description'],
                steps=steps
            )
            
            # Register template so _execute_task can find it
            task_choreographer.task_templates[task_def.name.lower()] = task_def

            result = task_choreographer.execute_task(task_def)
            assert result['success'] is True
            
            # Manually trigger execution since we're not running the worker thread
            execution_id = result['execution_id']
            execution = task_choreographer.running_tasks[execution_id]
            task_choreographer._execute_task(execution)
            
            assert mock_step.call_count == 2
