"""
LADA v8.0 Routine Manager
Smart routine scheduler for automated daily workflows.
Handles scheduled tasks, trigger-based automations, and contextual routines.
"""

import json
import logging
import schedule
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, time
from pathlib import Path
from dataclasses import dataclass, field
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class Routine:
    """Scheduled routine configuration"""
    name: str
    workflow_name: str
    schedule_type: str  # 'daily', 'weekly', 'trigger', 'contextual'
    schedule_time: Optional[str] = None  # HH:MM format
    days_of_week: List[str] = field(default_factory=list)  # ['monday', 'tuesday', ...]
    trigger_event: Optional[str] = None  # 'system_startup', 'user_login', 'idle_30min', etc.
    context_conditions: Dict[str, Any] = field(default_factory=dict)  # {'time_of_day': 'morning', 'calendar_has_events': True}
    enabled: bool = True
    last_run: Optional[str] = None
    run_count: int = 0


class RoutineManager:
    """
    Smart routine scheduler and automation manager.
    Executes workflows based on time, triggers, or contextual conditions.
    """
    
    def __init__(self, workflow_engine=None, jarvis_core=None):
        """
        Initialize routine manager.
        
        Args:
            workflow_engine: Reference to WorkflowEngine
            jarvis_core: Reference to JarvisCommandProcessor
        """
        self.workflow_engine = workflow_engine
        self.jarvis = jarvis_core
        self.routines: Dict[str, Routine] = {}
        self.routine_dir = Path("data/routines")
        self.routine_dir.mkdir(parents=True, exist_ok=True)
        
        self.scheduler_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Event handlers for triggers
        self.trigger_handlers: Dict[str, Callable] = {}
        self._register_trigger_handlers()
        
        # Load saved routines
        self._load_routines()
        
        logger.info("✅ Routine Manager initialized")
    
    def _register_trigger_handlers(self):
        """Register trigger event handlers"""
        self.trigger_handlers['system_startup'] = self._on_system_startup
        self.trigger_handlers['user_login'] = self._on_user_login
        self.trigger_handlers['idle_detected'] = self._on_idle_detected
        self.trigger_handlers['calendar_event_soon'] = self._on_calendar_event_soon
    
    def register_routine(self, routine: Routine) -> bool:
        """
        Register a new routine.
        
        Args:
            routine: Routine configuration
        
        Returns:
            True if registered successfully
        """
        try:
            self.routines[routine.name] = routine
            self._save_routine(routine)
            
            # Schedule if time-based
            if routine.schedule_type == 'daily' and routine.schedule_time:
                self._schedule_daily_routine(routine)
            elif routine.schedule_type == 'weekly' and routine.schedule_time:
                self._schedule_weekly_routine(routine)
            
            logger.info(f"✅ Registered routine: {routine.name} ({routine.schedule_type})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to register routine {routine.name}: {e}")
            return False
    
    def _schedule_daily_routine(self, routine: Routine):
        """Schedule daily routine"""
        if not routine.schedule_time:
            return
        
        schedule.every().day.at(routine.schedule_time).do(
            self._execute_routine_wrapper, routine.name
        )
        logger.info(f"📅 Scheduled daily routine: {routine.name} at {routine.schedule_time}")
    
    def _schedule_weekly_routine(self, routine: Routine):
        """Schedule weekly routine"""
        if not routine.schedule_time or not routine.days_of_week:
            return
        
        day_map = {
            'monday': schedule.every().monday,
            'tuesday': schedule.every().tuesday,
            'wednesday': schedule.every().wednesday,
            'thursday': schedule.every().thursday,
            'friday': schedule.every().friday,
            'saturday': schedule.every().saturday,
            'sunday': schedule.every().sunday,
        }
        
        for day in routine.days_of_week:
            if day.lower() in day_map:
                day_map[day.lower()].at(routine.schedule_time).do(
                    self._execute_routine_wrapper, routine.name
                )
        
        logger.info(f"📅 Scheduled weekly routine: {routine.name} on {routine.days_of_week} at {routine.schedule_time}")
    
    def _execute_routine_wrapper(self, routine_name: str):
        """Wrapper to execute routine (for scheduler)"""
        asyncio.run(self.execute_routine(routine_name))
    
    async def execute_routine(self, routine_name: str, manual: bool = False) -> Dict[str, Any]:
        """
        Execute a registered routine.
        
        Args:
            routine_name: Name of routine to execute
            manual: True if manually triggered by user
        
        Returns:
            Execution result
        """
        if routine_name not in self.routines:
            return {'success': False, 'error': f"Routine '{routine_name}' not found"}
        
        routine = self.routines[routine_name]
        
        if not routine.enabled and not manual:
            return {'success': False, 'error': f"Routine '{routine_name}' is disabled"}
        
        # Check context conditions
        if routine.context_conditions and not manual:
            if not self._check_context_conditions(routine.context_conditions):
                logger.info(f"⏭️ Skipping routine {routine_name}: context conditions not met")
                return {'success': False, 'error': 'Context conditions not met'}
        
        logger.info(f"🚀 Executing routine: {routine_name} (workflow: {routine.workflow_name})")
        
        try:
            # Execute workflow via workflow engine
            if self.workflow_engine:
                result = await self.workflow_engine.execute_workflow(
                    routine.workflow_name,
                    context={'routine': routine_name, 'manual': manual}
                )
                
                # Update routine stats
                routine.last_run = datetime.now().isoformat()
                routine.run_count += 1
                self._save_routine(routine)
                
                return {
                    'success': result.success,
                    'routine': routine_name,
                    'workflow': routine.workflow_name,
                    'steps_completed': result.steps_completed,
                    'duration': result.duration_seconds,
                    'manual': manual
                }
            else:
                return {'success': False, 'error': 'No workflow engine available'}
        
        except Exception as e:
            logger.error(f"❌ Routine execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _check_context_conditions(self, conditions: Dict[str, Any]) -> bool:
        """Check if context conditions are met"""
        try:
            # Time of day check
            if 'time_of_day' in conditions:
                current_hour = datetime.now().hour
                time_of_day = conditions['time_of_day']
                
                if time_of_day == 'morning' and not (6 <= current_hour < 12):
                    return False
                elif time_of_day == 'afternoon' and not (12 <= current_hour < 17):
                    return False
                elif time_of_day == 'evening' and not (17 <= current_hour < 22):
                    return False
                elif time_of_day == 'night' and not (22 <= current_hour or current_hour < 6):
                    return False
            
            # Calendar check
            if conditions.get('calendar_has_events'):
                if hasattr(self.jarvis, 'calendar') and hasattr(self.jarvis.calendar, 'get_today_events'):
                    events = self.jarvis.calendar.get_today_events()
                    if not events:
                        return False
            
            # System idle check
            if 'system_idle_minutes' in conditions:
                # Would need to implement idle detection
                pass
            
            return True
        
        except Exception as e:
            logger.error(f"Context check failed: {e}")
            return False
    
    def start_scheduler(self):
        """Start background scheduler thread"""
        if self.running:
            logger.warning("⚠️ Scheduler already running")
            return
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("▶️ Routine scheduler started")
    
    def stop_scheduler(self):
        """Stop background scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        schedule.clear()
        logger.info("⏸️ Routine scheduler stopped")
    
    def _scheduler_loop(self):
        """Background scheduler loop"""
        while self.running:
            try:
                schedule.run_pending()
                threading.Event().wait(60)  # Check every minute
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
    
    def trigger_event(self, event_name: str, context: Dict[str, Any] = None):
        """
        Trigger event-based routines.
        
        Args:
            event_name: Event identifier
            context: Optional event context
        """
        logger.info(f"🔔 Trigger event: {event_name}")
        
        # Find routines with matching trigger
        matching_routines = [
            routine for routine in self.routines.values()
            if routine.schedule_type == 'trigger' and routine.trigger_event == event_name and routine.enabled
        ]
        
        for routine in matching_routines:
            logger.info(f"  → Executing triggered routine: {routine.name}")
            asyncio.run(self.execute_routine(routine.name))
        
        # Call registered handler if exists
        if event_name in self.trigger_handlers:
            self.trigger_handlers[event_name](context)
    
    def _on_system_startup(self, context: Dict[str, Any] = None):
        """Handle system startup event"""
        logger.info("🚀 System startup detected")
    
    def _on_user_login(self, context: Dict[str, Any] = None):
        """Handle user login event"""
        logger.info("👤 User login detected")
    
    def _on_idle_detected(self, context: Dict[str, Any] = None):
        """Handle system idle event"""
        logger.info("💤 System idle detected")
    
    def _on_calendar_event_soon(self, context: Dict[str, Any] = None):
        """Handle upcoming calendar event"""
        logger.info("📅 Calendar event approaching")
    
    def list_routines(self) -> List[Dict[str, Any]]:
        """List all registered routines"""
        return [
            {
                'name': routine.name,
                'workflow': routine.workflow_name,
                'schedule_type': routine.schedule_type,
                'schedule_time': routine.schedule_time,
                'enabled': routine.enabled,
                'last_run': routine.last_run,
                'run_count': routine.run_count
            }
            for routine in self.routines.values()
        ]
    
    def enable_routine(self, routine_name: str) -> bool:
        """Enable a routine"""
        if routine_name in self.routines:
            self.routines[routine_name].enabled = True
            self._save_routine(self.routines[routine_name])
            logger.info(f"✅ Enabled routine: {routine_name}")
            return True
        return False
    
    def disable_routine(self, routine_name: str) -> bool:
        """Disable a routine"""
        if routine_name in self.routines:
            self.routines[routine_name].enabled = False
            self._save_routine(self.routines[routine_name])
            logger.info(f"⏸️ Disabled routine: {routine_name}")
            return True
        return False
    
    def _save_routine(self, routine: Routine):
        """Save routine to disk"""
        try:
            filepath = self.routine_dir / f"{routine.name}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'name': routine.name,
                    'workflow_name': routine.workflow_name,
                    'schedule_type': routine.schedule_type,
                    'schedule_time': routine.schedule_time,
                    'days_of_week': routine.days_of_week,
                    'trigger_event': routine.trigger_event,
                    'context_conditions': routine.context_conditions,
                    'enabled': routine.enabled,
                    'last_run': routine.last_run,
                    'run_count': routine.run_count
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save routine {routine.name}: {e}")
    
    def _load_routines(self):
        """Load saved routines from disk"""
        try:
            for filepath in self.routine_dir.glob("*.json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    routine = Routine(**data)
                    self.routines[routine.name] = routine
            logger.info(f"📂 Loaded {len(self.routines)} saved routines")
        except Exception as e:
            logger.error(f"Failed to load routines: {e}")


# Pre-built routine templates
def create_morning_routine() -> Routine:
    """Create morning routine"""
    return Routine(
        name='morning_routine',
        workflow_name='morning_routine',
        schedule_type='daily',
        schedule_time='07:00',
        context_conditions={'time_of_day': 'morning'},
        enabled=True
    )


def create_evening_routine() -> Routine:
    """Create evening routine"""
    return Routine(
        name='evening_routine',
        workflow_name='evening_routine',
        schedule_type='daily',
        schedule_time='20:00',
        context_conditions={'time_of_day': 'evening'},
        enabled=True
    )


def create_startup_routine() -> Routine:
    """Create system startup routine"""
    return Routine(
        name='startup_routine',
        workflow_name='morning_routine',
        schedule_type='trigger',
        trigger_event='system_startup',
        enabled=True
    )


def create_routine_manager(workflow_engine=None, jarvis_core=None) -> RoutineManager:
    """Factory function to create routine manager"""
    manager = RoutineManager(workflow_engine, jarvis_core)
    
    # Register pre-built routines
    manager.register_routine(create_morning_routine())
    manager.register_routine(create_evening_routine())
    manager.register_routine(create_startup_routine())
    
    return manager


if __name__ == '__main__':
    # Test routine manager
    logging.basicConfig(level=logging.INFO)
    manager = RoutineManager()
    
    # Test routine registration
    test_routine = Routine(
        name='test_routine',
        workflow_name='test_workflow',
        schedule_type='daily',
        schedule_time='09:00',
        enabled=True
    )
    
    manager.register_routine(test_routine)
    print(f"\n📋 Available routines: {manager.list_routines()}")
