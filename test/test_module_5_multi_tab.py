import pytest
from unittest.mock import MagicMock, patch
from modules.multi_tab_orchestrator import MultiTabOrchestrator

class TestMultiTabOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        with patch('modules.multi_tab_orchestrator.BrowserTabController') as MockController:
            # Setup mock controller
            mock_controller_instance = MockController.return_value
            mock_controller_instance.open_tab.return_value = {'success': True}
            
            orchestrator = MultiTabOrchestrator()
            orchestrator.tab_controller = mock_controller_instance
            return orchestrator

    def test_create_group(self, orchestrator):
        """Test creating a new tab group"""
        urls = ["https://google.com", "https://github.com"]
        result = orchestrator.create_group("TestGroup", urls, open_now=False)
        
        assert result['success'] is True
        assert result['group_name'] == "TestGroup"
        assert result['tabs_count'] == 2
        assert "TestGroup" in orchestrator.active_groups

    def test_create_group_and_open(self, orchestrator):
        """Test creating and immediately opening a group"""
        urls = ["https://google.com", "https://github.com"]
        result = orchestrator.create_group("OpenGroup", urls, open_now=True)
        
        assert result['success'] is True
        assert result['tabs_opened'] == 2
        assert orchestrator.tab_controller.open_tab.call_count == 2

    def test_open_group(self, orchestrator):
        """Test opening an existing group"""
        # First create a group
        orchestrator.create_group("ExistingGroup", ["https://example.com"], open_now=False)
        
        # Then open it
        result = orchestrator.open_group("ExistingGroup")
        
        assert result['success'] is True
        assert result['tabs_opened'] == 1
        orchestrator.tab_controller.open_tab.assert_called_with("https://example.com")

    def test_open_nonexistent_group(self, orchestrator):
        """Test opening a group that doesn't exist"""
        result = orchestrator.open_group("GhostGroup")
        assert result['success'] is False
        assert "not found" in result['error']

    def test_close_group(self, orchestrator):
        """Test closing (removing) a group"""
        orchestrator.create_group("ToClose", ["https://example.com"], open_now=False)
        
        result = orchestrator.close_group("ToClose")
        
        assert result['success'] is True
        assert "ToClose" not in orchestrator.active_groups

    def test_list_groups(self, orchestrator):
        """Test listing active groups"""
        orchestrator.create_group("Group1", ["url1"], open_now=False)
        orchestrator.create_group("Group2", ["url2"], open_now=False)
        
        result = orchestrator.list_groups()
        
        assert result['success'] is True
        assert result['count'] == 2
        names = [g['name'] for g in result['groups']]
        assert "Group1" in names
        assert "Group2" in names

    def test_open_workspace(self, orchestrator):
        """Test opening a predefined workspace"""
        # Mock open_tab to track calls
        orchestrator.tab_controller.open_tab.reset_mock()
        
        result = orchestrator.open_workspace("research")
        
        assert result['success'] is True
        # Research template has 3 tabs
        assert orchestrator.tab_controller.open_tab.call_count == 3

    def test_open_invalid_workspace(self, orchestrator):
        """Test opening an unknown workspace"""
        result = orchestrator.open_workspace("invalid_workspace")
        assert result['success'] is False
        assert "Unknown workspace" in result['error']
