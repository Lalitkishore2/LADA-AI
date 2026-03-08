"""
LADA v7.0 - Continuous Monitoring Module
Background monitoring for files, system, and scheduled tasks

Features:
- File/folder change watching with watchdog
- System resource monitoring
- Scheduled task execution
- Alert notifications
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False
    logger.warning("[Monitor] watchdog not available - file watching disabled")
    Observer = None
    FileSystemEventHandler = object
    FileSystemEvent = None


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert notification"""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    source: str


class FileWatcher(FileSystemEventHandler if WATCHDOG_OK else object):
    """Watch file system for changes"""
    
    def __init__(self, callback: Callable[[str, str, str], None] = None):
        """
        Initialize file watcher.
        
        Args:
            callback: Function called on file change (event_type, path, details)
        """
        if WATCHDOG_OK:
            super().__init__()
        self.callback = callback
        self.events: List[Dict] = []
    
    def on_created(self, event):
        """Handle file creation"""
        if not event.is_directory:
            self._notify("created", event.src_path, f"New file: {Path(event.src_path).name}")
    
    def on_deleted(self, event):
        """Handle file deletion"""
        if not event.is_directory:
            self._notify("deleted", event.src_path, f"Deleted: {Path(event.src_path).name}")
    
    def on_modified(self, event):
        """Handle file modification"""
        if not event.is_directory:
            self._notify("modified", event.src_path, f"Modified: {Path(event.src_path).name}")
    
    def on_moved(self, event):
        """Handle file move/rename"""
        if not event.is_directory:
            src = Path(event.src_path).name
            dst = Path(event.dest_path).name if hasattr(event, 'dest_path') else 'unknown'
            self._notify("moved", event.src_path, f"Moved: {src} → {dst}")
    
    def _notify(self, event_type: str, path: str, details: str):
        """Send notification"""
        event = {
            'type': event_type,
            'path': path,
            'details': details,
            'timestamp': datetime.now()
        }
        self.events.append(event)
        
        # Keep only last 100 events
        if len(self.events) > 100:
            self.events = self.events[-100:]
        
        if self.callback:
            try:
                self.callback(event_type, path, details)
            except Exception as e:
                logger.error(f"[FileWatcher] Callback error: {e}")
        
        logger.info(f"[FileWatcher] {event_type}: {path}")


class ScheduledTask:
    """Scheduled task definition"""
    
    def __init__(
        self,
        name: str,
        action: Callable,
        interval_minutes: int = 0,
        run_at: str = None,  # HH:MM format
        enabled: bool = True
    ):
        self.name = name
        self.action = action
        self.interval_minutes = interval_minutes
        self.run_at = run_at
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self._calculate_next_run()
    
    def _calculate_next_run(self):
        """Calculate next run time"""
        now = datetime.now()
        
        if self.run_at:
            # Run at specific time
            hour, minute = map(int, self.run_at.split(':'))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            self.next_run = next_run
        elif self.interval_minutes > 0:
            # Run at interval
            if self.last_run:
                self.next_run = self.last_run + timedelta(minutes=self.interval_minutes)
            else:
                self.next_run = now + timedelta(minutes=self.interval_minutes)
    
    def should_run(self) -> bool:
        """Check if task should run now"""
        if not self.enabled or not self.next_run:
            return False
        return datetime.now() >= self.next_run
    
    def run(self) -> Dict[str, Any]:
        """Execute the task"""
        try:
            result = self.action()
            self.last_run = datetime.now()
            self._calculate_next_run()
            return {
                'success': True,
                'task': self.name,
                'result': result
            }
        except Exception as e:
            logger.error(f"[ScheduledTask] {self.name} failed: {e}")
            return {
                'success': False,
                'task': self.name,
                'error': str(e)
            }


class ContinuousMonitor:
    """
    Background monitoring system.
    Watches files, monitors resources, runs scheduled tasks.
    """
    
    def __init__(self, alert_callback: Callable[[Alert], None] = None):
        """
        Initialize continuous monitor.
        
        Args:
            alert_callback: Function called when alerts occur
        """
        self.alert_callback = alert_callback
        self.alerts: List[Alert] = []
        
        # File watching
        self.observer = Observer() if WATCHDOG_OK else None
        self.watchers: Dict[str, FileWatcher] = {}
        
        # Scheduled tasks
        self.tasks: Dict[str, ScheduledTask] = {}
        
        # Monitoring state
        self.running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # System thresholds
        self.cpu_threshold = 90  # Alert if CPU > 90%
        self.memory_threshold = 90  # Alert if memory > 90%
        self.disk_threshold = 90  # Alert if disk > 90%
        
        # Default tasks
        self._setup_default_tasks()
    
    def _setup_default_tasks(self):
        """Set up default monitoring tasks"""
        # System resource check every 5 minutes
        self.add_task(ScheduledTask(
            name="system_check",
            action=self._check_system_resources,
            interval_minutes=5
        ))
    
    def watch_folder(
        self,
        path: str,
        callback: Callable[[str, str, str], None] = None
    ) -> Dict[str, Any]:
        """
        Start watching a folder for changes.
        
        Args:
            path: Folder path to watch
            callback: Optional callback for events
            
        Returns:
            {'success': True, 'path': '...'}
        """
        if not WATCHDOG_OK:
            return {
                'success': False,
                'error': 'watchdog not installed. Run: pip install watchdog'
            }
        
        if not os.path.exists(path):
            return {'success': False, 'error': f'Path not found: {path}'}
        
        try:
            # Create watcher
            watcher = FileWatcher(callback or self._on_file_event)
            
            # Schedule watching
            self.observer.schedule(watcher, path, recursive=True)
            self.watchers[path] = watcher
            
            # Start observer if not running
            if not self.observer.is_alive():
                self.observer.start()
            
            logger.info(f"[Monitor] Watching: {path}")
            return {'success': True, 'path': path}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stop_watching(self, path: str = None) -> Dict[str, Any]:
        """Stop watching a folder or all folders"""
        try:
            if path and path in self.watchers:
                # Stop specific watcher
                del self.watchers[path]
                return {'success': True, 'stopped': path}
            elif path is None:
                # Stop all
                if self.observer:
                    self.observer.stop()
                self.watchers.clear()
                return {'success': True, 'stopped': 'all'}
            return {'success': False, 'error': f'Not watching: {path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _on_file_event(self, event_type: str, path: str, details: str):
        """Handle file system events"""
        # Create alert for important changes
        if event_type in ['created', 'deleted']:
            self._create_alert(
                AlertLevel.INFO,
                f"File {event_type}",
                details,
                "file_watcher"
            )
    
    def add_task(self, task: ScheduledTask):
        """Add a scheduled task"""
        self.tasks[task.name] = task
        logger.info(f"[Monitor] Added task: {task.name}")
    
    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task"""
        if name in self.tasks:
            del self.tasks[name]
            return True
        return False
    
    def start(self):
        """Start background monitoring"""
        if self.running:
            return
        
        self.running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("[Monitor] Background monitoring started")
    
    def stop(self):
        """Stop background monitoring"""
        self.running = False
        if self.observer:
            self.observer.stop()
        logger.info("[Monitor] Background monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Check scheduled tasks
                for task in self.tasks.values():
                    if task.should_run():
                        result = task.run()
                        logger.debug(f"[Monitor] Task {task.name}: {result}")
                
                # Sleep for a bit
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"[Monitor] Loop error: {e}")
                time.sleep(60)
    
    def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resources and create alerts if needed"""
        try:
            import psutil
            
            # Check CPU
            cpu = psutil.cpu_percent(interval=1)
            if cpu > self.cpu_threshold:
                self._create_alert(
                    AlertLevel.WARNING,
                    "High CPU Usage",
                    f"CPU is at {cpu}%",
                    "system_monitor"
                )
            
            # Check memory
            mem = psutil.virtual_memory()
            if mem.percent > self.memory_threshold:
                self._create_alert(
                    AlertLevel.WARNING,
                    "High Memory Usage",
                    f"Memory is at {mem.percent}%",
                    "system_monitor"
                )
            
            # Check disk
            disk = psutil.disk_usage('/')
            if disk.percent > self.disk_threshold:
                self._create_alert(
                    AlertLevel.WARNING,
                    "Low Disk Space",
                    f"Disk is at {disk.percent}%",
                    "system_monitor"
                )
            
            # Check battery
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged and battery.percent < 20:
                self._create_alert(
                    AlertLevel.CRITICAL,
                    "Low Battery",
                    f"Battery at {battery.percent}% - plug in soon!",
                    "system_monitor"
                )
            
            return {
                'cpu': cpu,
                'memory': mem.percent,
                'disk': disk.percent,
                'battery': battery.percent if battery else None
            }
            
        except ImportError:
            return {'error': 'psutil not available'}
        except Exception as e:
            return {'error': str(e)}
    
    def _create_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        source: str
    ):
        """Create and store an alert"""
        alert = Alert(
            level=level,
            title=title,
            message=message,
            timestamp=datetime.now(),
            source=source
        )
        
        self.alerts.append(alert)
        
        # Keep only last 50 alerts
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]
        
        # Notify callback
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                logger.error(f"[Monitor] Alert callback error: {e}")
        
        logger.info(f"[Monitor] Alert [{level.value}]: {title} - {message}")
    
    def get_alerts(
        self,
        level: AlertLevel = None,
        limit: int = 10
    ) -> List[Alert]:
        """Get recent alerts, optionally filtered by level"""
        alerts = self.alerts
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts[-limit:]
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitoring status"""
        return {
            'running': self.running,
            'watchers': list(self.watchers.keys()),
            'tasks': list(self.tasks.keys()),
            'alert_count': len(self.alerts),
            'watchdog_available': WATCHDOG_OK
        }


# Singleton instance
_monitor: Optional[ContinuousMonitor] = None


def get_monitor(alert_callback: Callable[[Alert], None] = None) -> ContinuousMonitor:
    """Get or create monitor instance"""
    global _monitor
    if _monitor is None:
        _monitor = ContinuousMonitor(alert_callback)
    elif alert_callback and not _monitor.alert_callback:
        _monitor.alert_callback = alert_callback
    return _monitor


def start_monitoring():
    """Start background monitoring"""
    get_monitor().start()


def stop_monitoring():
    """Stop background monitoring"""
    if _monitor:
        _monitor.stop()


def watch_folder(path: str, callback: Callable = None) -> Dict[str, Any]:
    """Watch a folder for changes"""
    return get_monitor().watch_folder(path, callback)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 50)
    print("LADA Continuous Monitor Test")
    print("=" * 50)
    
    def on_alert(alert: Alert):
        print(f"\n🔔 ALERT [{alert.level.value}]: {alert.title}")
        print(f"   {alert.message}")
    
    monitor = ContinuousMonitor(alert_callback=on_alert)
    
    # Test file watching
    if WATCHDOG_OK:
        print("\n📁 Setting up file watcher...")
        result = monitor.watch_folder(str(Path.home() / "Downloads"))
        print(f"  Result: {result}")
    else:
        print("\n⚠️ watchdog not installed - skipping file watching")
    
    # Test system check
    print("\n💻 Checking system resources...")
    resources = monitor._check_system_resources()
    print(f"  CPU: {resources.get('cpu')}%")
    print(f"  Memory: {resources.get('memory')}%")
    print(f"  Disk: {resources.get('disk')}%")
    
    print("\n📊 Monitor status:")
    status = monitor.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
