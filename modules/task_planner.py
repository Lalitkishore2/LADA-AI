"""
LADA v7.0 - Task Planner Engine
AI-powered task decomposition for Comet-style automation
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskPlanner:
    """
    AI-powered task decomposition engine.
    Breaks user requests into executable browser automation steps.
    """
    
    def __init__(self, ai_router):
        """
        Initialize task planner.
        
        Args:
            ai_router: HybridAIRouter instance for AI queries
        """
        self.ai_router = ai_router
        self.current_plan: List[Dict] = []
        self.execution_log: List[Dict] = []
        
    def plan_task(self, user_request: str) -> List[Dict]:
        """
        Break down a user request into executable steps.
        
        Args:
            user_request: Natural language request like "Find cheapest flight Delhi to Bangalore"
            
        Returns:
            List of step dictionaries
        """
        planning_prompt = f"""You are a task planner for a browser automation system.
Break down this user request into specific browser automation steps.

User Request: "{user_request}"

Return a JSON array of steps. Each step must have:
- "number": Step number (1, 2, 3...)
- "action": One of: navigate, click, fill, extract, wait, screenshot
- "target": CSS selector or URL
- "value": Value to fill (for fill action) or description
- "wait_after": Milliseconds to wait after action (default 1000)
- "description": Human-readable description

Example for "Find cheapest flight Delhi to Bangalore":
[
  {{"number": 1, "action": "navigate", "target": "https://www.google.com/flights", "value": "", "wait_after": 2000, "description": "Open Google Flights"}},
  {{"number": 2, "action": "fill", "target": "input[aria-label*='Where from']", "value": "Delhi", "wait_after": 1000, "description": "Enter departure city"}},
  {{"number": 3, "action": "fill", "target": "input[aria-label*='Where to']", "value": "Bangalore", "wait_after": 1000, "description": "Enter destination"}},
  {{"number": 4, "action": "click", "target": "button[aria-label*='Search']", "value": "", "wait_after": 3000, "description": "Click search button"}},
  {{"number": 5, "action": "extract", "target": "body", "value": "prices", "wait_after": 0, "description": "Extract flight prices"}},
  {{"number": 6, "action": "screenshot", "target": "results.png", "value": "", "wait_after": 0, "description": "Take screenshot of results"}}
]

Return ONLY valid JSON array, no other text."""

        try:
            response = self.ai_router.query(planning_prompt)
            
            # Extract JSON from response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON array found in AI response")
                return self._get_fallback_plan(user_request)
            
            json_str = response[json_start:json_end]
            steps = json.loads(json_str)
            
            # Validate steps
            validated_steps = []
            for step in steps:
                if self._validate_step(step):
                    validated_steps.append(step)
            
            self.current_plan = validated_steps
            logger.info(f"✅ Generated {len(validated_steps)} steps for: {user_request}")
            return validated_steps
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return self._get_fallback_plan(user_request)
        except Exception as e:
            logger.error(f"Task planning failed: {e}")
            return self._get_fallback_plan(user_request)
    
    def _validate_step(self, step: Dict) -> bool:
        """Validate a step has required fields."""
        required = ['number', 'action', 'target', 'description']
        valid_actions = ['navigate', 'click', 'fill', 'extract', 'wait', 'screenshot', 'scroll']
        
        if not all(key in step for key in required):
            return False
        
        if step.get('action') not in valid_actions:
            return False
        
        return True
    
    def _get_fallback_plan(self, user_request: str) -> List[Dict]:
        """Generate a basic fallback plan when AI fails."""
        # Detect intent and create simple plan
        request_lower = user_request.lower()
        
        if 'flight' in request_lower:
            return [
                {"number": 1, "action": "navigate", "target": "https://www.google.com/flights", "value": "", "wait_after": 2000, "description": "Open Google Flights"},
                {"number": 2, "action": "screenshot", "target": "flights_page.png", "value": "", "wait_after": 0, "description": "Capture page for manual search"}
            ]
        elif 'product' in request_lower or 'phone' in request_lower or 'laptop' in request_lower:
            return [
                {"number": 1, "action": "navigate", "target": "https://www.amazon.in", "value": "", "wait_after": 2000, "description": "Open Amazon"},
                {"number": 2, "action": "screenshot", "target": "amazon_page.png", "value": "", "wait_after": 0, "description": "Capture page for manual search"}
            ]
        elif 'hotel' in request_lower:
            return [
                {"number": 1, "action": "navigate", "target": "https://www.booking.com", "value": "", "wait_after": 2000, "description": "Open Booking.com"},
                {"number": 2, "action": "screenshot", "target": "hotel_page.png", "value": "", "wait_after": 0, "description": "Capture page for manual search"}
            ]
        else:
            return [
                {"number": 1, "action": "navigate", "target": "https://www.google.com", "value": "", "wait_after": 2000, "description": "Open Google Search"},
                {"number": 2, "action": "fill", "target": "textarea[name='q']", "value": user_request, "wait_after": 1000, "description": "Enter search query"},
                {"number": 3, "action": "click", "target": "input[name='btnK']", "value": "", "wait_after": 2000, "description": "Click search"},
                {"number": 4, "action": "screenshot", "target": "search_results.png", "value": "", "wait_after": 0, "description": "Capture results"}
            ]
    
    def execute_plan(self, browser_agent, safety_gate=None, progress_callback=None) -> Dict[str, Any]:
        """
        Execute the current plan using browser agent.
        
        Args:
            browser_agent: CometBrowserAgent instance
            safety_gate: Optional SafetyGate for permission checks
            progress_callback: Optional callback(step_num, total, description)
            
        Returns:
            {"success": bool, "steps_completed": int, "results": list, "error": str}
        """
        if not self.current_plan:
            return {"success": False, "steps_completed": 0, "results": [], "error": "No plan to execute"}
        
        results = []
        steps_completed = 0
        total_steps = len(self.current_plan)
        
        for step in self.current_plan:
            step_num = step['number']
            action = step['action']
            target = step['target']
            value = step.get('value', '')
            wait_after = step.get('wait_after', 1000)
            description = step['description']
            
            # Progress callback
            if progress_callback:
                progress_callback(step_num, total_steps, description)
            
            logger.info(f"📍 Step {step_num}/{total_steps}: {description}")
            
            # Check safety for risky actions
            if safety_gate and action in ['click', 'fill']:
                if 'payment' in description.lower() or 'submit' in description.lower() or 'book' in description.lower():
                    if not safety_gate.ask_permission(description, "high"):
                        return {
                            "success": False,
                            "steps_completed": steps_completed,
                            "results": results,
                            "error": f"User declined permission at step {step_num}"
                        }
            
            try:
                # Execute action based on type
                if action == 'navigate':
                    result = browser_agent.navigate(target)
                elif action == 'click':
                    result = browser_agent.click_element(target)
                elif action == 'fill':
                    result = browser_agent.fill_form(target, value)
                elif action == 'extract':
                    text = browser_agent.extract_text(target if target != 'body' else None)
                    result = {"success": True, "text": text[:5000]}  # Limit text length
                elif action == 'screenshot':
                    filepath = browser_agent.get_page_screenshot(target)
                    result = {"success": bool(filepath), "path": filepath}
                elif action == 'wait':
                    import time
                    time.sleep(int(target) / 1000)
                    result = {"success": True}
                elif action == 'scroll':
                    browser_agent.execute_js(f"window.scrollBy(0, {target})")
                    result = {"success": True}
                else:
                    result = {"success": False, "error": f"Unknown action: {action}"}
                
                # Wait after action
                if wait_after > 0:
                    import time
                    time.sleep(wait_after / 1000)
                
                result['step'] = step_num
                result['description'] = description
                results.append(result)
                
                if result.get('success', False):
                    steps_completed += 1
                else:
                    # Try to recover from failure
                    recovery = self._try_recover(step, browser_agent)
                    if recovery:
                        steps_completed += 1
                        results[-1] = recovery
                    else:
                        return {
                            "success": False,
                            "steps_completed": steps_completed,
                            "results": results,
                            "error": f"Step {step_num} failed: {result.get('error', 'Unknown error')}"
                        }
                
                # Log execution
                self.execution_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "step": step,
                    "result": result
                })
                
            except Exception as e:
                logger.error(f"❌ Step {step_num} exception: {e}")
                return {
                    "success": False,
                    "steps_completed": steps_completed,
                    "results": results,
                    "error": str(e)
                }
        
        return {
            "success": True,
            "steps_completed": steps_completed,
            "results": results,
            "error": None
        }
    
    def _try_recover(self, failed_step: Dict, browser_agent) -> Optional[Dict]:
        """Try alternative approach for failed step."""
        action = failed_step['action']
        target = failed_step['target']
        
        # Try JavaScript click if CSS click failed
        if action == 'click':
            try:
                browser_agent.execute_js(f"document.querySelector('{target}').click()")
                return {"success": True, "recovered": True, "step": failed_step['number']}
            except Exception:
                pass
        
        # Try alternative selectors
        if action in ['click', 'fill']:
            # Try by text content
            try:
                if 'search' in failed_step['description'].lower():
                    browser_agent.execute_js("document.querySelector('button[type=submit]').click()")
                    return {"success": True, "recovered": True, "step": failed_step['number']}
            except Exception:
                pass
        
        return None
    
    def get_plan_summary(self) -> str:
        """Get human-readable summary of current plan."""
        if not self.current_plan:
            return "No plan generated yet."
        
        summary = f"📋 Plan: {len(self.current_plan)} steps\n"
        for step in self.current_plan:
            summary += f"  {step['number']}. {step['description']}\n"
        return summary
    
    def clear_plan(self):
        """Clear current plan and execution log."""
        self.current_plan = []
        self.execution_log = []


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    from lada_ai_router import HybridAIRouter
    
    print("🚀 Testing TaskPlanner...")
    
    # Initialize
    router = HybridAIRouter()
    planner = TaskPlanner(router)
    
    # Test planning
    request = "Find cheapest flight from Delhi to Bangalore tomorrow"
    print(f"\n📝 Request: {request}")
    
    steps = planner.plan_task(request)
    
    print(f"\n{planner.get_plan_summary()}")
    
    # Show JSON
    print("\n📄 Steps JSON:")
    for step in steps:
        print(f"  {json.dumps(step)}")
    
    print("\n✅ TaskPlanner test complete!")
