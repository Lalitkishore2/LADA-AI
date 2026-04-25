"""Extended tests for modules/task_planner.py - covers execute_plan, recovery, edge cases"""
import json
import time
from unittest.mock import MagicMock, patch, call

import pytest


class TestTaskPlannerValidation:
    """Tests for step validation edge cases"""

    def test_validate_step_invalid_action(self):
        """Test validation rejects unknown action types"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        step = {
            "number": 1,
            "action": "invalid_action",
            "target": "https://example.com",
            "description": "Invalid action test",
        }

        assert planner._validate_step(step) is False

    def test_validate_step_all_valid_actions(self):
        """Test all valid action types pass validation"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        valid_actions = ['navigate', 'click', 'fill', 'extract', 'wait', 'screenshot', 'scroll']
        
        for action in valid_actions:
            step = {
                "number": 1,
                "action": action,
                "target": "test_target",
                "description": f"Test {action}",
            }
            assert planner._validate_step(step) is True, f"Action {action} should be valid"

    def test_validate_step_empty_fields(self):
        """Test validation with empty required fields"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        # Empty action should still fail (not in valid_actions)
        step = {
            "number": 1,
            "action": "",
            "target": "test",
            "description": "Empty action",
        }
        assert planner._validate_step(step) is False


class TestFallbackPlanBranches:
    """Tests for all fallback plan intent branches"""

    def test_fallback_plan_product_intent(self):
        """Test fallback for product search requests"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        plan = planner._get_fallback_plan("Find best phone under 20000")
        
        assert len(plan) == 2
        assert "amazon" in plan[0]["target"].lower()

    def test_fallback_plan_laptop_intent(self):
        """Test fallback for laptop search requests"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        plan = planner._get_fallback_plan("Best laptop for gaming")
        
        assert len(plan) == 2
        assert "amazon" in plan[0]["target"].lower()

    def test_fallback_plan_hotel_intent(self):
        """Test fallback for hotel search requests"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        plan = planner._get_fallback_plan("Book a hotel in Mumbai")
        
        assert len(plan) == 2
        assert "booking.com" in plan[0]["target"].lower()

    def test_fallback_plan_default_intent(self):
        """Test fallback for generic search requests"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        plan = planner._get_fallback_plan("What is the weather today")
        
        assert len(plan) == 4
        assert "google.com" in plan[0]["target"].lower()
        assert plan[1]["action"] == "fill"
        assert plan[2]["action"] == "click"
        assert plan[3]["action"] == "screenshot"


class TestPlanTaskEdgeCases:
    """Tests for plan_task JSON parsing edge cases"""

    def test_plan_task_json_with_prefix_text(self):
        """Test parsing JSON with extra text before array"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = """Here is your plan:
        [{"number": 1, "action": "navigate", "target": "https://test.com", "description": "Test"}]
        Hope this helps!"""

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Test request")

        assert len(steps) == 1
        assert steps[0]["action"] == "navigate"

    def test_plan_task_filters_invalid_steps(self):
        """Test that invalid steps are filtered out"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = json.dumps([
            {"number": 1, "action": "navigate", "target": "url", "description": "Valid"},
            {"number": 2, "action": "invalid_action", "target": "url", "description": "Invalid"},
            {"number": 3, "action": "click", "target": "btn", "description": "Also valid"},
        ])

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Test request")

        assert len(steps) == 2
        assert steps[0]["number"] == 1
        assert steps[1]["number"] == 3

    def test_plan_task_empty_json_array(self):
        """Test handling of empty JSON array response"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = "[]"

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Test request")

        assert steps == []

    def test_plan_task_malformed_json_falls_back(self):
        """Test malformed JSON triggers fallback"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = "[{invalid json here}]"

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Find flights")

        # Should get fallback plan
        assert len(steps) > 0
        assert steps[0]["action"] == "navigate"


class TestGetPlanSummary:
    """Tests for get_plan_summary method"""

    def test_get_plan_summary_empty(self):
        """Test summary with no plan"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        summary = planner.get_plan_summary()
        
        assert "No plan" in summary

    def test_get_plan_summary_with_steps(self):
        """Test summary with multiple steps"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "description": "Open website"},
            {"number": 2, "action": "click", "target": "btn", "description": "Click button"},
            {"number": 3, "action": "screenshot", "target": "file.png", "description": "Take screenshot"},
        ]

        summary = planner.get_plan_summary()
        
        assert "3 steps" in summary
        assert "Open website" in summary
        assert "Click button" in summary
        assert "Take screenshot" in summary


class TestExecutePlan:
    """Tests for execute_plan method"""

    def test_execute_plan_no_plan(self):
        """Test execute with no current plan"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        mock_browser = MagicMock()

        result = planner.execute_plan(mock_browser)

        assert result["success"] is False
        assert result["steps_completed"] == 0
        assert "No plan" in result["error"]

    def test_execute_plan_navigate_success(self):
        """Test successful navigation step execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "https://test.com", "value": "", "wait_after": 0, "description": "Navigate to test"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert result["steps_completed"] == 1
        mock_browser.navigate.assert_called_once_with("https://test.com")

    def test_execute_plan_click_action(self):
        """Test click action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "click", "target": "#btn", "value": "", "wait_after": 0, "description": "Click button"}
        ]

        mock_browser = MagicMock()
        mock_browser.click_element.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        mock_browser.click_element.assert_called_once_with("#btn")

    def test_execute_plan_fill_action(self):
        """Test fill action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "fill", "target": "input[name='q']", "value": "test query", "wait_after": 0, "description": "Fill search"}
        ]

        mock_browser = MagicMock()
        mock_browser.fill_form.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        mock_browser.fill_form.assert_called_once_with("input[name='q']", "test query")

    def test_execute_plan_extract_action(self):
        """Test extract action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "extract", "target": "body", "value": "", "wait_after": 0, "description": "Extract text"}
        ]

        mock_browser = MagicMock()
        mock_browser.extract_text.return_value = "Extracted content"

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert result["results"][0]["text"] == "Extracted content"
        mock_browser.extract_text.assert_called_once_with(None)

    def test_execute_plan_extract_specific_selector(self):
        """Test extract action with specific selector"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "extract", "target": "#content", "value": "", "wait_after": 0, "description": "Extract content div"}
        ]

        mock_browser = MagicMock()
        mock_browser.extract_text.return_value = "Specific content"

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        mock_browser.extract_text.assert_called_once_with("#content")

    def test_execute_plan_screenshot_action(self):
        """Test screenshot action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "screenshot", "target": "test.png", "value": "", "wait_after": 0, "description": "Take screenshot"}
        ]

        mock_browser = MagicMock()
        mock_browser.get_page_screenshot.return_value = "/path/to/test.png"

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert result["results"][0]["path"] == "/path/to/test.png"

    def test_execute_plan_screenshot_action_failure(self):
        """Test screenshot action when it fails"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "screenshot", "target": "test.png", "value": "", "wait_after": 0, "description": "Take screenshot"}
        ]

        mock_browser = MagicMock()
        mock_browser.get_page_screenshot.return_value = None

        result = planner.execute_plan(mock_browser)

        # Screenshot failure returns success=False in result
        assert result["results"][0]["success"] is False

    @patch('time.sleep')
    def test_execute_plan_wait_action(self, mock_sleep):
        """Test wait action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "wait", "target": "2000", "value": "", "wait_after": 0, "description": "Wait 2 seconds"}
        ]

        mock_browser = MagicMock()

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        mock_sleep.assert_called_with(2.0)  # 2000ms = 2 seconds

    def test_execute_plan_scroll_action(self):
        """Test scroll action execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "scroll", "target": "500", "value": "", "wait_after": 0, "description": "Scroll down"}
        ]

        mock_browser = MagicMock()
        mock_browser.execute_js.return_value = None

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        mock_browser.execute_js.assert_called_once_with("window.scrollBy(0, 500)")

    def test_execute_plan_unknown_action(self):
        """Test handling of unknown action type"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        # Directly set plan to bypass validation for this test
        planner.current_plan = [
            {"number": 1, "action": "unknown", "target": "test", "value": "", "wait_after": 0, "description": "Unknown action"}
        ]

        mock_browser = MagicMock()

        result = planner.execute_plan(mock_browser)

        assert result["success"] is False
        assert "Unknown action" in result["error"]

    def test_execute_plan_with_progress_callback(self):
        """Test progress callback is called during execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 0, "description": "Step 1"},
            {"number": 2, "action": "click", "target": "btn", "value": "", "wait_after": 0, "description": "Step 2"},
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}
        mock_browser.click_element.return_value = {"success": True}

        progress_calls = []
        def progress_callback(step_num, total, description):
            progress_calls.append((step_num, total, description))

        result = planner.execute_plan(mock_browser, progress_callback=progress_callback)

        assert result["success"] is True
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, "Step 1")
        assert progress_calls[1] == (2, 2, "Step 2")

    def test_execute_plan_with_safety_gate_approve(self):
        """Test safety gate allows action when approved"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "click", "target": "btn", "value": "", "wait_after": 0, "description": "Submit payment form"}
        ]

        mock_browser = MagicMock()
        mock_browser.click_element.return_value = {"success": True}

        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = True

        result = planner.execute_plan(mock_browser, safety_gate=mock_safety)

        assert result["success"] is True
        mock_safety.ask_permission.assert_called_once()

    def test_execute_plan_with_safety_gate_decline(self):
        """Test safety gate blocks action when declined"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "click", "target": "btn", "value": "", "wait_after": 0, "description": "Book flight now"}
        ]

        mock_browser = MagicMock()
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = False

        result = planner.execute_plan(mock_browser, safety_gate=mock_safety)

        assert result["success"] is False
        assert "declined permission" in result["error"]
        mock_browser.click_element.assert_not_called()

    def test_execute_plan_safety_gate_only_risky_actions(self):
        """Test safety gate is only checked for risky actions"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 0, "description": "Payment page"},
            {"number": 2, "action": "screenshot", "target": "file.png", "value": "", "wait_after": 0, "description": "Screenshot payment"},
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}
        mock_browser.get_page_screenshot.return_value = "file.png"

        mock_safety = MagicMock()

        result = planner.execute_plan(mock_browser, safety_gate=mock_safety)

        assert result["success"] is True
        # Safety gate should not be called for navigate/screenshot
        mock_safety.ask_permission.assert_not_called()

    def test_execute_plan_step_exception(self):
        """Test handling of exception during step execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 0, "description": "Navigate"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.side_effect = Exception("Network error")

        result = planner.execute_plan(mock_browser)

        assert result["success"] is False
        assert "Network error" in result["error"]

    @patch('time.sleep')
    def test_execute_plan_wait_after(self, mock_sleep):
        """Test wait_after is applied after actions"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 2000, "description": "Navigate"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        # Should sleep for 2000ms = 2 seconds
        mock_sleep.assert_called_with(2.0)

    def test_execute_plan_updates_execution_log(self):
        """Test that execution log is updated"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 0, "description": "Navigate"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}

        planner.execute_plan(mock_browser)

        assert len(planner.execution_log) == 1
        assert "timestamp" in planner.execution_log[0]
        assert "step" in planner.execution_log[0]
        assert "result" in planner.execution_log[0]

    def test_execute_plan_multiple_steps(self):
        """Test execution of multiple steps in sequence"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "wait_after": 0, "description": "Navigate"},
            {"number": 2, "action": "fill", "target": "input", "value": "test", "wait_after": 0, "description": "Fill"},
            {"number": 3, "action": "click", "target": "btn", "value": "", "wait_after": 0, "description": "Click"},
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}
        mock_browser.fill_form.return_value = {"success": True}
        mock_browser.click_element.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert result["steps_completed"] == 3
        assert len(result["results"]) == 3


class TestTryRecover:
    """Tests for _try_recover method"""

    def test_try_recover_click_with_js(self):
        """Test recovery using JavaScript click"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        failed_step = {
            "number": 1,
            "action": "click",
            "target": "#btn",
            "description": "Click button",
        }

        mock_browser = MagicMock()
        mock_browser.execute_js.return_value = None

        result = planner._try_recover(failed_step, mock_browser)

        assert result is not None
        assert result["success"] is True
        assert result["recovered"] is True
        mock_browser.execute_js.assert_called_with("document.querySelector('#btn').click()")

    def test_try_recover_click_js_fails(self):
        """Test recovery returns None when JS click also fails"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        failed_step = {
            "number": 1,
            "action": "click",
            "target": "#btn",
            "description": "Click button",
        }

        mock_browser = MagicMock()
        mock_browser.execute_js.side_effect = Exception("JS failed")

        result = planner._try_recover(failed_step, mock_browser)

        assert result is None

    def test_try_recover_search_button_fallback(self):
        """Test recovery using search submit button fallback"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        failed_step = {
            "number": 1,
            "action": "click",
            "target": "#search-btn",
            "description": "Click search button",
        }

        mock_browser = MagicMock()
        # First call for the direct JS click fails
        mock_browser.execute_js.side_effect = [Exception("JS failed"), None]

        result = planner._try_recover(failed_step, mock_browser)

        assert result is not None
        assert result["success"] is True
        assert result["recovered"] is True

    def test_try_recover_non_recoverable_action(self):
        """Test that non-click/fill actions return None"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        failed_step = {
            "number": 1,
            "action": "navigate",
            "target": "https://example.com",
            "description": "Navigate",
        }

        mock_browser = MagicMock()

        result = planner._try_recover(failed_step, mock_browser)

        assert result is None

    def test_try_recover_fill_action_with_search(self):
        """Test recovery for fill action with search description"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        failed_step = {
            "number": 1,
            "action": "fill",
            "target": "input[name='q']",
            "description": "Search for products",
        }

        mock_browser = MagicMock()
        mock_browser.execute_js.return_value = None

        result = planner._try_recover(failed_step, mock_browser)

        # Fill action tries the submit button fallback
        assert result is not None


class TestExecutePlanRecovery:
    """Tests for step recovery during plan execution"""

    def test_execute_plan_recovery_success(self):
        """Test successful recovery during execution"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "click", "target": "#btn", "value": "", "wait_after": 0, "description": "Click button"}
        ]

        mock_browser = MagicMock()
        mock_browser.click_element.return_value = {"success": False, "error": "Element not found"}
        # Recovery via JS succeeds
        mock_browser.execute_js.return_value = None

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert result["steps_completed"] == 1

    def test_execute_plan_recovery_failure(self):
        """Test when recovery also fails"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "click", "target": "#btn", "value": "", "wait_after": 0, "description": "Click button"}
        ]

        mock_browser = MagicMock()
        mock_browser.click_element.return_value = {"success": False, "error": "Element not found"}
        mock_browser.execute_js.side_effect = Exception("JS also failed")

        result = planner.execute_plan(mock_browser)

        assert result["success"] is False
        assert "failed" in result["error"]


class TestExecutePlanValueDefault:
    """Tests for default value handling in execute_plan"""

    def test_execute_plan_missing_value_key(self):
        """Test handling of step without 'value' key"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "wait_after": 0, "description": "Navigate"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True

    def test_execute_plan_missing_wait_after(self):
        """Test handling of step without 'wait_after' key"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "navigate", "target": "url", "value": "", "description": "Navigate"}
        ]

        mock_browser = MagicMock()
        mock_browser.navigate.return_value = {"success": True}

        with patch('time.sleep') as mock_sleep:
            result = planner.execute_plan(mock_browser)

            assert result["success"] is True
            # Default wait_after is 1000ms = 1 second
            mock_sleep.assert_called_with(1.0)


class TestExtractTextTruncation:
    """Tests for text extraction length limiting"""

    def test_extract_text_truncated(self):
        """Test that extracted text is truncated to 5000 chars"""
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [
            {"number": 1, "action": "extract", "target": "body", "value": "", "wait_after": 0, "description": "Extract"}
        ]

        mock_browser = MagicMock()
        # Return text longer than 5000 chars
        long_text = "A" * 10000
        mock_browser.extract_text.return_value = long_text

        result = planner.execute_plan(mock_browser)

        assert result["success"] is True
        assert len(result["results"][0]["text"]) == 5000
