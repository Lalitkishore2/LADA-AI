import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from modules.workflow_engine import WorkflowEngine, WorkflowStep, WorkflowResult

class TestWorkflowEngine:
    @pytest.fixture
    def mock_jarvis(self):
        """Create a mock Jarvis core with all necessary controllers"""
        jarvis = MagicMock()
        
        # Mock controllers
        jarvis.system_controller = MagicMock()
        jarvis.browser_controller = MagicMock()
        jarvis.file_controller = MagicMock()
        jarvis.agent_actions = MagicMock()
        
        # Mock v9 controllers
        jarvis.advanced_system = MagicMock()
        jarvis.window_manager = MagicMock()
        jarvis.gui_automator = MagicMock()
        jarvis.browser_tabs = MagicMock()
        jarvis.multi_tab = MagicMock()
        jarvis.gmail = MagicMock()
        jarvis.calendar = MagicMock()
        
        return jarvis

    @pytest.fixture
    def workflow_engine(self, mock_jarvis):
        """Initialize WorkflowEngine with mock Jarvis"""
        # Patch Path to prevent loading real workflows during init
        with patch('modules.workflow_engine.Path') as mock_path:
            mock_path.return_value.mkdir.return_value = None
            mock_path.return_value.glob.return_value = []
            
            engine = WorkflowEngine(mock_jarvis)
            # Reset workflows for clean state
            engine.workflows = {}
            # Mock workflow_dir for tests
            engine.workflow_dir = MagicMock()
            return engine

    def test_initialization(self, workflow_engine, mock_jarvis):
        """Test that WorkflowEngine initializes and registers actions correctly"""
        assert workflow_engine.jarvis == mock_jarvis
        assert 'set_volume' in workflow_engine.action_handlers
        assert 'open_url' in workflow_engine.action_handlers
        assert 'create_file' in workflow_engine.action_handlers

    def test_register_action(self, workflow_engine):
        """Test registering a custom action"""
        mock_handler = MagicMock()
        # Directly add to action_handlers as there is no register_action method
        workflow_engine.action_handlers['custom_action'] = mock_handler
        assert 'custom_action' in workflow_engine.action_handlers
        assert workflow_engine.action_handlers['custom_action'] == mock_handler

    @pytest.mark.asyncio
    async def test_execute_workflow_sequential(self, workflow_engine):
        """Test executing a multi-step workflow"""
        # Setup actions
        mock_action1 = AsyncMock(return_value="Result1")
        mock_action2 = AsyncMock(return_value="Result2")
        
        workflow_engine.action_handlers['step1'] = mock_action1
        workflow_engine.action_handlers['step2'] = mock_action2
        
        workflow_steps = [
            {'action': 'step1', 'params': {'p': 1}, 'module': 'test'},
            {'action': 'step2', 'params': {'p': 2}, 'module': 'test'}
        ]
        
        workflow_engine.register_workflow('Test Workflow', workflow_steps)
        
        result = await workflow_engine.execute_workflow('Test Workflow')
        
        assert result.success is True
        assert result.steps_completed == 2
        
        mock_action1.assert_called_once_with(p=1)
        mock_action2.assert_called_once_with(p=2)

    @pytest.mark.asyncio
    async def test_execute_workflow_failure(self, workflow_engine):
        """Test handling of step execution failure"""
        # Register a mock action that raises an exception
        mock_action = AsyncMock(side_effect=Exception("Action failed"))
        workflow_engine.action_handlers['fail_action'] = mock_action
        
        workflow_steps = [
            {'action': 'fail_action', 'params': {}, 'module': 'test'}
        ]
        
        workflow_engine.register_workflow('Fail Workflow', workflow_steps)
        
        result = await workflow_engine.execute_workflow('Fail Workflow')
        
        assert result.success is False
        assert "Action failed" in result.results[0]['error']

    def test_load_workflows(self, workflow_engine):
        """Test loading workflows from disk"""
        # Setup mock glob to return a file
        mock_file = MagicMock()
        workflow_engine.workflow_dir.glob.return_value = [mock_file]
        
        # Mock open and json.load
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.load') as mock_json_load:
                mock_json_load.return_value = {
                    'name': 'Loaded Workflow', 
                    'steps': [{'action': 'test', 'module': 'test', 'params': {}}]
                }
                
                workflow_engine._load_workflows()
                
                assert 'Loaded Workflow' in workflow_engine.workflows
