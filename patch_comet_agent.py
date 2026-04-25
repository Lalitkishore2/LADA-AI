import re
import sys

with open(r'c:\lada ai\modules\comet_agent.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update ActionType enum
code = re.sub(
    r'    CLOSE_APP = "close_app"',
    '    CLOSE_APP = "close_app"\n    SWITCH_TAB = "switch_tab"\n    NEW_TAB = "new_tab"\n    CLOSE_TAB = "close_tab"',
    code
)

# 2. Add cross_tab_synthesizer import
code = re.sub(
    r'from lada_ai_router import HybridAIRouter',
    'from lada_ai_router import HybridAIRouter\n    try:\n        from modules.cross_tab_synthesizer import get_cross_tab_synthesizer\n        CROSS_TAB_OK = True\n    except ImportError:\n        CROSS_TAB_OK = False',
    code
)

# 3. Change _capture_screen_state to async
code = code.replace('def _capture_screen_state(self)', 'async def _capture_screen_state(self)')
code = code.replace('state.current_url = self.browser.get_current_url()', 'state.current_url = await self.browser.get_current_url()')

# Add cross tab logic right after browser state gathering
cross_tab_logic = """
        # Cross Tab Sync
        if self.browser and CROSS_TAB_OK:
            try:
                cross_tab = get_cross_tab_synthesizer()
                tab_id = getattr(self.browser, "history", [{"tab_id": "-1"}])[-1].get("tab_id", "-1") if self.browser.history else "-1"
                cross_tab.snapshot_tab(
                    tab_id=tab_id,
                    url=state.current_url or "",
                    title=await self.browser.get_current_title() or "",
                    text=state.visible_text or ""
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Cross Tab Snapshot failed: " + str(e))
"""
code = code.replace('state.timestamp = time.time()\n        self.state_history.append(state)', 
                    cross_tab_logic + '\n        state.timestamp = time.time()\n        self.state_history.append(state)')

# 4. Update execute_task to await _capture_screen_state
code = code.replace('current_state = self._capture_screen_state()', 'current_state = await self._capture_screen_state()')
code = code.replace('self._capture_screen_state()', 'await self._capture_screen_state()')

# 5. Make _execute_action async
code = code.replace('def _execute_action(self, action: Action) -> Tuple[bool, str]:', 'async def _execute_action(self, action: Action) -> Tuple[bool, str]:')

# 6. Update _execute_action inner browser calls
code = code.replace('self.browser.navigate(action.value)', 'await self.browser.navigate(action.value)')
code = code.replace('self.browser.click(action.target)', 'await self.browser.click_element(action.target)')
code = code.replace('self.browser.type(action.target or "input", text_to_type)', 'await self.browser.fill_form(action.target or "input", text_to_type)')
code = code.replace('self.browser.execute_js("window.scrollBy(0, 500)")', 'await self.browser.execute_js("window.scrollBy(0, 500)")')
code = code.replace('self.browser.extract_text(action.target or "body")', 'await self.browser.extract_text(action.target or None)')

# Add tab commands to _execute_action
tab_actions = """
            elif action.type == ActionType.NEW_TAB:
                if self.browser:
                    tid = await self.browser.new_tab(action.value or "")
                    return True, f"Opened new tab (ID: {tid})"
                return False, "Browser not available"
            elif action.type == ActionType.SWITCH_TAB:
                if self.browser:
                    try:
                        await self.browser.switch_tab(int(action.target or "0"))
                        return True, f"Switched to tab {action.target}"
                    except ValueError:
                        return False, "Invalid tab index"
                return False, "Browser not available"
            elif action.type == ActionType.CLOSE_TAB:
                if self.browser:
                    try:
                        idx = int(action.target) if action.target else None
                        await self.browser.close_tab(idx)
                        return True, "Closed tab"
                    except ValueError:
                        return False, "Invalid tab index"
                return False, "Browser not available"
"""
code = code.replace('elif action.type == ActionType.OPEN_APP:', tab_actions + '\n            elif action.type == ActionType.OPEN_APP:')

# 7. Update _verify_action
code = code.replace('def _verify_action(self, action: Action,\n                       before_state: ScreenState) -> Tuple[bool, ScreenState]:', 'async def _verify_action(self, action: Action,\n                       before_state: ScreenState) -> Tuple[bool, ScreenState]:')

# 8. Update execute_task awaits
code = code.replace('success, message = self._execute_action(current_action)', 'success, message = await self._execute_action(current_action)')
code = code.replace('verified, new_state = self._verify_action(current_action, current_state)', 'verified, new_state = await self._verify_action(current_action, current_state)')

# Inject CrossTab prompt into THINK context
cross_tab_query = """
        # Build context for AI
        context = self._build_ai_context(task, current_state, history)
        
        cross_tab_prompt = ""
        if CROSS_TAB_OK and self.browser:
            try:
                ct = get_cross_tab_synthesizer()
                cross_tab_prompt = ct.build_synthesis_prompt()
            except Exception:
                pass
"""
# We must replace the basic _think build context
code = code.replace('# Build context for AI\n        context = self._build_ai_context(task, current_state, history)', cross_tab_query)

# Add it to the prompt
code = code.replace(
    'Current screen state:\n- Active window: {current_state.active_window}',
    '{cross_tab_prompt}\n\nCurrent screen state:\n- Active window: {current_state.active_window}'
)

code = code.replace(
    '"action": "click|type|scroll|navigate|wait|extract|keyboard|open_app|complete|error",',
    '"action": "click|type|scroll|navigate|wait|extract|keyboard|open_app|new_tab|switch_tab|close_tab|complete|error",'
)

with open(r'c:\lada ai\modules\comet_agent.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patching complete!")
