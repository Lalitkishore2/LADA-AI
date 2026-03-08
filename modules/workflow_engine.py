"""
LADA v8.0 Workflow Engine
Orchestrates multi-step workflows by chaining existing modules together.
Enables JARVIS-level automation by combining system_control, browser_automation,
file_operations, agents, and other capabilities into complex routines.
"""

import json
import logging
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from pathlib import Path
import asyncio
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    action: str
    module: str
    params: Dict[str, Any] = field(default_factory=dict)
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    retry_count: int = 0
    timeout: int = 30


@dataclass
class WorkflowResult:
    """Result of workflow execution"""
    success: bool
    workflow_name: str
    steps_completed: int
    total_steps: int
    duration_seconds: float
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class WorkflowEngine:
    """
    Core workflow orchestration engine.
    Chains multiple LADA modules into complex multi-step workflows.
    """
    
    def __init__(self, jarvis_core=None):
        """
        Initialize workflow engine.
        
        Args:
            jarvis_core: Reference to JarvisCommandProcessor for module access
        """
        self.jarvis = jarvis_core
        self.workflows: Dict[str, List[WorkflowStep]] = {}
        self.workflow_history: List[WorkflowResult] = []
        self.workflow_dir = Path("data/workflows")
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # Module action registry - maps actions to module methods
        self.action_handlers: Dict[str, Callable] = {}
        self._register_core_actions()
        
        # Load saved workflows
        self._load_workflows()
        
        logger.info("✅ Workflow Engine initialized")
    
    def _register_core_actions(self):
        """Register core module actions"""
        if not self.jarvis:
            logger.warning("⚠️ No JARVIS core - running in standalone mode")
            return
        
        # System Control actions
        if hasattr(self.jarvis, 'system_controller'):
            self.action_handlers['set_volume'] = self.jarvis.system_controller.set_volume
            self.action_handlers['set_brightness'] = self.jarvis.system_controller.set_brightness
            self.action_handlers['wifi_toggle'] = self.jarvis.system_controller.toggle_wifi
            self.action_handlers['bluetooth_toggle'] = self.jarvis.system_controller.toggle_bluetooth
        
        # Browser Control actions
        if hasattr(self.jarvis, 'browser_controller'):
            self.action_handlers['open_url'] = self.jarvis.browser_controller.open_url
            self.action_handlers['google_search'] = self.jarvis.browser_controller.google_search
            self.action_handlers['extract_text'] = self.jarvis.browser_controller.extract_text
        
        # File Operations actions
        if hasattr(self.jarvis, 'file_controller'):
            self.action_handlers['create_file'] = self.jarvis.file_controller.create_file
            self.action_handlers['read_file'] = self.jarvis.file_controller.read_file
            self.action_handlers['organize_downloads'] = self.jarvis.file_controller.organize_downloads
        
        # Agent actions
        if hasattr(self.jarvis, 'agent_actions'):
            self.action_handlers['check_flight'] = self.jarvis.agent_actions.check_flight
            self.action_handlers['find_product'] = self.jarvis.agent_actions.find_product
            self.action_handlers['send_email'] = self.jarvis.agent_actions.send_email
            self.action_handlers['check_calendar'] = self.jarvis.agent_actions.check_calendar
        
        # ============ v9.0 Advanced System Control ============
        if hasattr(self.jarvis, 'advanced_system'):
            asc = self.jarvis.advanced_system
            self.action_handlers['adv_create_file'] = asc.create_file
            self.action_handlers['adv_read_file'] = asc.read_file
            self.action_handlers['adv_delete_file'] = asc.delete_file
            self.action_handlers['adv_move_file'] = asc.move_file
            self.action_handlers['adv_copy_file'] = asc.copy_file
            self.action_handlers['adv_rename_file'] = asc.rename_file
            self.action_handlers['search_files'] = asc.search_files
            self.action_handlers['find_large_files'] = asc.find_large_files
            self.action_handlers['find_recent_files'] = asc.find_recent_files
            self.action_handlers['organize_directory'] = asc.organize_directory
            self.action_handlers['adv_organize_downloads'] = asc.organize_downloads
            self.action_handlers['get_disk_space'] = asc.get_disk_space
            self.action_handlers['undo_file_action'] = asc.undo_last_action
        
        # ============ v9.0 Window Manager ============
        if hasattr(self.jarvis, 'window_manager'):
            wm = self.jarvis.window_manager
            self.action_handlers['list_windows'] = wm.list_windows
            self.action_handlers['get_active_window'] = wm.get_active_window
            self.action_handlers['find_window'] = wm.find_window
            self.action_handlers['switch_to_window'] = wm.switch_to_window
            self.action_handlers['maximize_window'] = wm.maximize_window
            self.action_handlers['minimize_window'] = wm.minimize_window
            self.action_handlers['close_window'] = wm.close_window
            self.action_handlers['arrange_windows'] = wm.arrange_windows
            self.action_handlers['snap_window'] = wm.snap_window
            self.action_handlers['open_application'] = wm.open_application
            self.action_handlers['close_application'] = wm.close_application
        
        # ============ v9.0 GUI Automator ============
        if hasattr(self.jarvis, 'gui_automator'):
            gui = self.jarvis.gui_automator
            self.action_handlers['click'] = gui.click
            self.action_handlers['double_click'] = gui.double_click
            self.action_handlers['right_click'] = gui.right_click
            self.action_handlers['type_text'] = gui.type_text
            self.action_handlers['press_key'] = gui.press_key
            self.action_handlers['hotkey'] = gui.hotkey
            self.action_handlers['scroll'] = gui.scroll
            self.action_handlers['screenshot'] = gui.screenshot
            self.action_handlers['find_image'] = gui.find_image_on_screen
            self.action_handlers['find_text'] = gui.find_text_on_screen
            self.action_handlers['click_on_text'] = gui.click_on_text
            self.action_handlers['click_on_image'] = gui.click_on_image
            self.action_handlers['extract_screen_text'] = gui.extract_text_from_screen
            self.action_handlers['copy'] = gui.copy
            self.action_handlers['paste'] = gui.paste
            self.action_handlers['select_all'] = gui.select_all
            self.action_handlers['save'] = gui.save
        
        # ============ v9.0 Browser Tab Controller ============
        if hasattr(self.jarvis, 'browser_tabs'):
            btc = self.jarvis.browser_tabs
            self.action_handlers['open_tab'] = btc.open_tab
            self.action_handlers['close_tab'] = btc.close_tab
            self.action_handlers['switch_tab'] = btc.switch_tab
            self.action_handlers['navigate_to'] = btc.navigate_to
            self.action_handlers['refresh_tab'] = btc.refresh_tab
            self.action_handlers['go_back'] = btc.go_back
            self.action_handlers['go_forward'] = btc.go_forward
            self.action_handlers['browser_google_search'] = btc.google_search
            self.action_handlers['youtube_search'] = btc.youtube_search
            self.action_handlers['find_on_page'] = btc.find_on_page
            self.action_handlers['scroll_page'] = btc.scroll_page
            self.action_handlers['open_incognito'] = btc.open_incognito
        
        # ============ v9.0 Multi-Tab Orchestrator ============
        if hasattr(self.jarvis, 'multi_tab'):
            mto = self.jarvis.multi_tab
            self.action_handlers['create_tab_group'] = mto.create_group
            self.action_handlers['open_workspace'] = mto.open_workspace
            self.action_handlers['open_multiple_tabs'] = mto.open_multiple_tabs
            self.action_handlers['research_topic'] = mto.research_topic
            self.action_handlers['compare_products'] = mto.compare_products
            self.action_handlers['save_session'] = mto.save_session
            self.action_handlers['load_session'] = mto.load_session
        
        # ============ v9.0 Gmail Controller ============
        if hasattr(self.jarvis, 'gmail'):
            gm = self.jarvis.gmail
            self.action_handlers['send_email'] = gm.send_email
            self.action_handlers['get_inbox'] = gm.get_inbox
            self.action_handlers['get_unread_count'] = gm.get_unread_count
            self.action_handlers['search_emails'] = gm.search_emails
            self.action_handlers['mark_as_read'] = gm.mark_as_read
            self.action_handlers['archive_email'] = gm.archive_email
            self.action_handlers['trash_email'] = gm.trash_email
            self.action_handlers['create_draft'] = gm.create_draft
        
        # ============ v9.0 Calendar Controller ============
        if hasattr(self.jarvis, 'calendar'):
            cal = self.jarvis.calendar
            self.action_handlers['create_event'] = cal.create_event
            self.action_handlers['quick_add_event'] = cal.quick_add
            self.action_handlers['get_upcoming_events'] = cal.get_upcoming_events
            self.action_handlers['get_today_events'] = cal.get_today_events
            self.action_handlers['get_week_events'] = cal.get_week_events
            self.action_handlers['search_events'] = cal.search_events
            self.action_handlers['delete_event'] = cal.delete_event
            self.action_handlers['create_meeting'] = cal.create_meeting
        
        # ============ v9.0 Task Orchestrator (Week 3) ============
        if hasattr(self.jarvis, 'task_orchestrator'):
            to = self.jarvis.task_orchestrator
            self.action_handlers['create_task'] = to.create_task
            self.action_handlers['submit_task'] = to.submit_task
            self.action_handlers['create_task_group'] = to.create_task_group
            self.action_handlers['submit_group'] = to.submit_group
            self.action_handlers['get_task_status'] = to.get_task_status
            self.action_handlers['cancel_task'] = to.cancel_task
            self.action_handlers['list_tasks'] = to.list_tasks
            self.action_handlers['get_running_tasks'] = to.get_running_tasks
            self.action_handlers['get_task_stats'] = to.get_statistics
            self.action_handlers['wait_for_task'] = to.wait_for_task
            self.action_handlers['run_batch'] = to.run_batch
            self.action_handlers['run_pipeline'] = to.run_pipeline
            self.action_handlers['get_task_history'] = to.get_history
        
        # ============ v9.0 Screenshot Analysis (Week 3) ============
        if hasattr(self.jarvis, 'screenshot_analyzer'):
            sa = self.jarvis.screenshot_analyzer
            self.action_handlers['capture_screen'] = sa.capture_screen
            self.action_handlers['capture_window'] = sa.capture_window
            self.action_handlers['extract_screen_text'] = sa.extract_text
            self.action_handlers['find_text_on_screen'] = sa.find_text
            self.action_handlers['click_on_text'] = sa.click_text
            self.action_handlers['detect_ui_elements'] = sa.detect_ui_elements
            self.action_handlers['find_ui_element'] = sa.find_element
            self.action_handlers['get_clickable'] = sa.get_clickable_elements
            self.action_handlers['compare_images'] = sa.compare_images
            self.action_handlers['detect_changes'] = sa.detect_changes
            self.action_handlers['save_baseline'] = sa.save_baseline
            self.action_handlers['analyze_screen'] = sa.analyze_screen
            self.action_handlers['get_dominant_colors'] = sa.get_dominant_colors
            self.action_handlers['start_screen_monitor'] = sa.start_monitoring
            self.action_handlers['stop_screen_monitor'] = sa.stop_monitoring
        
        # ============ v9.0 Pattern Learning (Week 3) ============
        if hasattr(self.jarvis, 'pattern_learner'):
            pl = self.jarvis.pattern_learner
            self.action_handlers['record_command'] = pl.record_command
            self.action_handlers['predict_next'] = pl.predict_next_command
            self.action_handlers['suggest_routines'] = pl.suggest_routines
            self.action_handlers['get_suggestions'] = pl.get_suggestions_for_time
            self.action_handlers['learn_preference'] = pl.learn_preference
            self.action_handlers['get_preference'] = pl.get_preference
            self.action_handlers['get_usage_stats'] = pl.get_usage_stats
            self.action_handlers['get_insights'] = pl.get_insights
            self.action_handlers['get_patterns'] = pl.get_patterns
            self.action_handlers['get_habits'] = pl.get_habits
        
        # ============ v9.0 Proactive Agent (Week 4) ============
        if hasattr(self.jarvis, 'proactive_agent'):
            pa = self.jarvis.proactive_agent
            self.action_handlers['add_suggestion'] = pa.add_suggestion
            self.action_handlers['get_pending_suggestions'] = pa.get_pending_suggestions
            self.action_handlers['get_next_suggestion'] = pa.get_next_suggestion
            self.action_handlers['accept_suggestion'] = pa.accept_suggestion
            self.action_handlers['dismiss_suggestion'] = pa.dismiss_suggestion
            self.action_handlers['morning_briefing'] = pa.generate_morning_briefing
            self.action_handlers['evening_summary'] = pa.generate_evening_summary
            self.action_handlers['suggest_based_on_context'] = pa.suggest_based_on_context
            self.action_handlers['check_system_state'] = pa.check_system_state
            self.action_handlers['check_calendar_reminders'] = pa.check_calendar_reminders
            self.action_handlers['start_proactive'] = pa.start
            self.action_handlers['stop_proactive'] = pa.stop
            self.action_handlers['add_trigger'] = pa.add_trigger
            self.action_handlers['remove_trigger'] = pa.remove_trigger
            self.action_handlers['list_triggers'] = pa.list_triggers
            self.action_handlers['proactive_status'] = pa.get_status
            self.action_handlers['proactive_stats'] = pa.get_stats
        
        # ============ v9.0 Permission System (Week 4) ============
        if hasattr(self.jarvis, 'permission_system'):
            ps = self.jarvis.permission_system
            self.action_handlers['check_permission'] = ps.check_permission
            self.action_handlers['set_permission_level'] = ps.set_permission_level
            self.action_handlers['get_permission_level'] = ps.get_permission_level
            self.action_handlers['add_whitelist'] = ps.add_to_whitelist
            self.action_handlers['remove_whitelist'] = ps.remove_from_whitelist
            self.action_handlers['add_blacklist'] = ps.add_to_blacklist
            self.action_handlers['remove_blacklist'] = ps.remove_from_blacklist
            self.action_handlers['get_permission_lists'] = ps.get_lists
            self.action_handlers['emergency_lock'] = ps.emergency_lock
            self.action_handlers['emergency_unlock'] = ps.emergency_unlock
            self.action_handlers['add_permission_rule'] = ps.add_rule
            self.action_handlers['remove_permission_rule'] = ps.remove_rule
            self.action_handlers['list_permission_rules'] = ps.list_rules
            self.action_handlers['get_audit_log'] = ps.get_audit_log
            self.action_handlers['get_audit_stats'] = ps.get_audit_stats
            self.action_handlers['set_rate_limit'] = ps.set_rate_limit
            self.action_handlers['get_rate_limits'] = ps.get_rate_limits
            self.action_handlers['permission_status'] = ps.get_status
        
        logger.info(f"📋 Registered {len(self.action_handlers)} action handlers")
    
    def register_workflow(self, name: str, steps: List[Dict[str, Any]]) -> bool:
        """
        Register a new workflow.
        
        Args:
            name: Workflow name
            steps: List of workflow steps as dicts
        
        Returns:
            True if registered successfully
        """
        try:
            workflow_steps = [WorkflowStep(**step) for step in steps]
            self.workflows[name] = workflow_steps
            self._save_workflow(name, steps)
            logger.info(f"✅ Registered workflow: {name} ({len(steps)} steps)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to register workflow {name}: {e}")
            return False
    
    async def execute_workflow(self, name: str, context: Dict[str, Any] = None) -> WorkflowResult:
        """
        Execute a registered workflow.
        
        Args:
            name: Workflow name
            context: Optional context variables
        
        Returns:
            WorkflowResult with execution details
        """
        if name not in self.workflows:
            return WorkflowResult(
                success=False,
                workflow_name=name,
                steps_completed=0,
                total_steps=0,
                duration_seconds=0.0,
                error=f"Workflow '{name}' not found"
            )
        
        start_time = datetime.now()
        steps = self.workflows[name]
        results = []
        context = context or {}
        
        logger.info(f"🚀 Executing workflow: {name} ({len(steps)} steps)")
        
        for idx, step in enumerate(steps, 1):
            try:
                logger.info(f"  Step {idx}/{len(steps)}: {step.action}")
                
                # Get action handler
                if step.action not in self.action_handlers:
                    raise ValueError(f"Unknown action: {step.action}")
                
                handler = self.action_handlers[step.action]
                
                # Substitute context variables in params
                params = self._substitute_context(step.params, context)
                
                # Execute action with timeout
                result = await asyncio.wait_for(
                    self._execute_action(handler, params),
                    timeout=step.timeout
                )
                
                results.append({
                    'step': idx,
                    'action': step.action,
                    'success': True,
                    'result': result
                })
                
                # Store result in context for next steps
                context[f'step_{idx}_result'] = result
                
            except asyncio.TimeoutError:
                error_msg = f"Step {idx} ({step.action}) timed out after {step.timeout}s"
                logger.error(f"  ❌ {error_msg}")
                results.append({
                    'step': idx,
                    'action': step.action,
                    'success': False,
                    'error': error_msg
                })
                
                if step.on_failure:
                    logger.info(f"  ↪️ Executing failure handler: {step.on_failure}")
                    # Could execute alternative workflow here
                break
            
            except Exception as e:
                error_msg = f"Step {idx} ({step.action}) failed: {e}"
                logger.error(f"  ❌ {error_msg}")
                results.append({
                    'step': idx,
                    'action': step.action,
                    'success': False,
                    'error': str(e)
                })
                break
        
        duration = (datetime.now() - start_time).total_seconds()
        success = len(results) == len(steps) and all(r['success'] for r in results)
        
        workflow_result = WorkflowResult(
            success=success,
            workflow_name=name,
            steps_completed=len(results),
            total_steps=len(steps),
            duration_seconds=duration,
            results=results,
            error=None if success else "Workflow incomplete"
        )
        
        self.workflow_history.append(workflow_result)
        
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{status} Workflow {name} completed in {duration:.2f}s ({len(results)}/{len(steps)} steps)")
        
        return workflow_result
    
    async def _execute_action(self, handler: Callable, params: Dict[str, Any]) -> Any:
        """Execute action handler with params"""
        if asyncio.iscoroutinefunction(handler):
            return await handler(**params)
        else:
            # Run sync function in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: handler(**params))
    
    def _substitute_context(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Substitute context variables in parameters"""
        result = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith('$'):
                # Context variable reference
                var_name = value[1:]
                result[key] = context.get(var_name, value)
            else:
                result[key] = value
        return result
    
    def _save_workflow(self, name: str, steps: List[Dict[str, Any]]):
        """Save workflow to disk"""
        try:
            filepath = self.workflow_dir / f"{name}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'name': name,
                    'created': datetime.now().isoformat(),
                    'steps': steps
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save workflow {name}: {e}")
    
    def _load_workflows(self):
        """Load saved workflows from disk"""
        try:
            for filepath in self.workflow_dir.glob("*.json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    name = data['name']
                    steps = [WorkflowStep(**step) for step in data['steps']]
                    self.workflows[name] = steps
            logger.info(f"📂 Loaded {len(self.workflows)} saved workflows")
        except Exception as e:
            logger.error(f"Failed to load workflows: {e}")
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all registered workflows"""
        return [
            {
                'name': name,
                'steps': len(steps),
                'actions': [step.action for step in steps]
            }
            for name, steps in self.workflows.items()
        ]
    
    def get_workflow_history(self, limit: int = 10) -> List[WorkflowResult]:
        """Get recent workflow execution history"""
        return self.workflow_history[-limit:]


# Pre-built workflow templates
MORNING_ROUTINE = [
    {'action': 'set_volume', 'module': 'system_control', 'params': {'level': 50}},
    {'action': 'set_brightness', 'module': 'system_control', 'params': {'level': 80}},
    {'action': 'check_calendar', 'module': 'agents', 'params': {'days': 1}},
    {'action': 'open_url', 'module': 'browser_control', 'params': {'url': 'https://gmail.com'}},
]

EVENING_ROUTINE = [
    {'action': 'set_brightness', 'module': 'system_control', 'params': {'level': 30}},
    {'action': 'organize_downloads', 'module': 'file_operations', 'params': {}},
    {'action': 'check_calendar', 'module': 'agents', 'params': {'days': 1}},
]

RESEARCH_WORKFLOW = [
    {'action': 'google_search', 'module': 'browser_control', 'params': {'query': '$search_query'}},
    {'action': 'extract_text', 'module': 'browser_control', 'params': {}},
    {'action': 'create_file', 'module': 'file_operations', 'params': {'path': '$output_file', 'content': '$step_2_result'}},
]


def create_workflow_engine(jarvis_core=None) -> WorkflowEngine:
    """Factory function to create workflow engine"""
    engine = WorkflowEngine(jarvis_core)
    
    # Register pre-built workflows
    engine.register_workflow('morning_routine', MORNING_ROUTINE)
    engine.register_workflow('evening_routine', EVENING_ROUTINE)
    engine.register_workflow('research_workflow', RESEARCH_WORKFLOW)
    
    return engine


if __name__ == '__main__':
    # Test workflow engine
    logging.basicConfig(level=logging.INFO)
    engine = WorkflowEngine()
    
    # Test workflow registration
    test_workflow = [
        {'action': 'set_volume', 'module': 'system_control', 'params': {'level': 75}},
        {'action': 'set_brightness', 'module': 'system_control', 'params': {'level': 90}},
    ]
    
    engine.register_workflow('test_workflow', test_workflow)
    print(f"\n📋 Available workflows: {engine.list_workflows()}")
