"""
Productivity Tools Module - LADA Ultimate
Implements: Alarms, Reminders, Timers, Focus Mode, Site Blocking, Internet Speed Test
"""

import time
import threading
import datetime
import json
import os
import subprocess
import platform
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, asdict, field
import socket
import urllib.request
import uuid


def _new_entity_id(prefix: str) -> str:
    """Generate collision-resistant ids for in-memory dictionaries."""
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Alarm:
    """Alarm data structure"""
    id: str
    time: str  # HH:MM format
    label: str = "Alarm"
    enabled: bool = True
    days: List[str] = field(default_factory=list)  # ["Mon", "Tue", ...] or empty for one-time
    sound: str = "default"
    
    
@dataclass
class Reminder:
    """Reminder data structure"""
    id: str
    message: str
    trigger_time: datetime.datetime
    completed: bool = False
    repeat: Optional[str] = None  # "daily", "weekly", "monthly", None
    

@dataclass
class Timer:
    """Timer data structure"""
    id: str
    duration_seconds: int
    label: str = "Timer"
    start_time: Optional[float] = None
    paused: bool = False
    remaining: Optional[int] = None


class AlarmManager:
    """Manage alarms with persistence"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.alarms_file = self.data_dir / "alarms.json"
        self.alarms: Dict[str, Alarm] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._load_alarms()
        
    def _load_alarms(self):
        """Load alarms from file"""
        if self.alarms_file.exists():
            try:
                with open(self.alarms_file, 'r') as f:
                    data = json.load(f)
                    for alarm_id, alarm_data in data.items():
                        self.alarms[alarm_id] = Alarm(**alarm_data)
            except Exception:
                self.alarms = {}
                
    def _save_alarms(self):
        """Save alarms to file"""
        try:
            data = {k: asdict(v) for k, v in self.alarms.items()}
            with open(self.alarms_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
            
    def create_alarm(self, time_str: str, label: str = "Alarm", days: List[str] = None) -> Alarm:
        """Create a new alarm
        
        Args:
            time_str: Time in HH:MM format (e.g., "07:30", "14:00")
            label: Description of the alarm
            days: List of days ["Mon", "Tue", ...] or None for one-time
        """
        alarm_id = _new_entity_id("alarm")
        alarm = Alarm(
            id=alarm_id,
            time=time_str,
            label=label,
            days=days or []
        )
        self.alarms[alarm_id] = alarm
        self._save_alarms()
        return alarm
        
    def delete_alarm(self, alarm_id: str) -> bool:
        """Delete an alarm"""
        if alarm_id in self.alarms:
            del self.alarms[alarm_id]
            self._save_alarms()
            return True
        return False
        
    def list_alarms(self) -> List[Alarm]:
        """List all alarms"""
        return list(self.alarms.values())
        
    def toggle_alarm(self, alarm_id: str) -> Optional[bool]:
        """Toggle alarm enabled state"""
        if alarm_id in self.alarms:
            self.alarms[alarm_id].enabled = not self.alarms[alarm_id].enabled
            self._save_alarms()
            return self.alarms[alarm_id].enabled
        return None
        
    def on_alarm(self, callback: Callable[[Alarm], None]):
        """Register callback for when alarm triggers"""
        self._callbacks.append(callback)
        
    def _trigger_alarm(self, alarm: Alarm):
        """Trigger alarm callbacks"""
        for callback in self._callbacks:
            try:
                callback(alarm)
            except Exception:
                pass
                
    def start_monitoring(self):
        """Start background thread to monitor alarms"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
    def stop_monitoring(self):
        """Stop alarm monitoring"""
        self._running = False
        
    def _monitor_loop(self):
        """Background loop to check alarms"""
        triggered_today = set()
        
        while self._running:
            now = datetime.datetime.now()
            current_time = now.strftime("%H:%M")
            current_day = now.strftime("%a")
            
            for alarm in self.alarms.values():
                if not alarm.enabled:
                    continue
                    
                # Check if time matches
                if alarm.time == current_time:
                    # Check if should trigger today
                    should_trigger = (
                        not alarm.days or  # One-time alarm
                        current_day in alarm.days  # Recurring alarm
                    )
                    
                    if should_trigger and alarm.id not in triggered_today:
                        triggered_today.add(alarm.id)
                        self._trigger_alarm(alarm)
                        
                        # Disable one-time alarms after triggering
                        if not alarm.days:
                            alarm.enabled = False
                            self._save_alarms()
                            
            # Reset triggered set at midnight
            if current_time == "00:00":
                triggered_today.clear()
                
            time.sleep(30)  # Check every 30 seconds


class ReminderManager:
    """Manage reminders with persistence"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.reminders_file = self.data_dir / "reminders.json"
        self.reminders: Dict[str, Reminder] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._load_reminders()
        
    def _load_reminders(self):
        """Load reminders from file"""
        if self.reminders_file.exists():
            try:
                with open(self.reminders_file, 'r') as f:
                    data = json.load(f)
                    for rem_id, rem_data in data.items():
                        rem_data['trigger_time'] = datetime.datetime.fromisoformat(rem_data['trigger_time'])
                        self.reminders[rem_id] = Reminder(**rem_data)
            except Exception:
                self.reminders = {}
                
    def _save_reminders(self):
        """Save reminders to file"""
        try:
            data = {}
            for k, v in self.reminders.items():
                d = asdict(v)
                d['trigger_time'] = v.trigger_time.isoformat()
                data[k] = d
            with open(self.reminders_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
            
    def create_reminder(self, message: str, trigger_time: datetime.datetime, 
                       repeat: Optional[str] = None) -> Reminder:
        """Create a new reminder
        
        Args:
            message: Reminder message
            trigger_time: When to trigger
            repeat: "daily", "weekly", "monthly", or None
        """
        reminder_id = _new_entity_id("rem")
        reminder = Reminder(
            id=reminder_id,
            message=message,
            trigger_time=trigger_time,
            repeat=repeat
        )
        self.reminders[reminder_id] = reminder
        self._save_reminders()
        return reminder
        
    def create_reminder_in(self, message: str, minutes: int = 0, hours: int = 0, 
                          days: int = 0) -> Reminder:
        """Create reminder that triggers in X time from now"""
        trigger_time = datetime.datetime.now() + datetime.timedelta(
            days=days, hours=hours, minutes=minutes
        )
        return self.create_reminder(message, trigger_time)
        
    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder"""
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]
            self._save_reminders()
            return True
        return False
        
    def list_reminders(self, include_completed: bool = False) -> List[Reminder]:
        """List reminders"""
        reminders = list(self.reminders.values())
        if not include_completed:
            reminders = [r for r in reminders if not r.completed]
        return sorted(reminders, key=lambda r: r.trigger_time)
        
    def on_reminder(self, callback: Callable[[Reminder], None]):
        """Register callback for when reminder triggers"""
        self._callbacks.append(callback)
        
    def start_monitoring(self):
        """Start background monitoring"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self._running = False
        
    def _monitor_loop(self):
        """Check reminders in background"""
        while self._running:
            now = datetime.datetime.now()
            
            for reminder in list(self.reminders.values()):
                if reminder.completed:
                    continue
                    
                if now >= reminder.trigger_time:
                    # Trigger reminder
                    for callback in self._callbacks:
                        try:
                            callback(reminder)
                        except Exception:
                            pass
                            
                    if reminder.repeat:
                        # Schedule next occurrence
                        if reminder.repeat == "daily":
                            reminder.trigger_time += datetime.timedelta(days=1)
                        elif reminder.repeat == "weekly":
                            reminder.trigger_time += datetime.timedelta(weeks=1)
                        elif reminder.repeat == "monthly":
                            reminder.trigger_time += datetime.timedelta(days=30)
                    else:
                        reminder.completed = True
                        
                    self._save_reminders()
                    
            time.sleep(30)


class TimerManager:
    """Manage countdown timers"""
    
    def __init__(self):
        self.timers: Dict[str, Timer] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
    def create_timer(self, minutes: int = 0, seconds: int = 0, 
                    hours: int = 0, label: str = "Timer") -> Timer:
        """Create a new timer"""
        total_seconds = hours * 3600 + minutes * 60 + seconds
        timer_id = _new_entity_id("timer")
        timer = Timer(
            id=timer_id,
            duration_seconds=total_seconds,
            label=label,
            start_time=time.time(),
            remaining=total_seconds
        )
        self.timers[timer_id] = timer
        self._start_if_needed()
        return timer
        
    def pause_timer(self, timer_id: str) -> bool:
        """Pause a timer"""
        if timer_id in self.timers:
            timer = self.timers[timer_id]
            if not timer.paused and timer.start_time:
                elapsed = time.time() - timer.start_time
                timer.remaining = max(0, timer.duration_seconds - int(elapsed))
                timer.paused = True
                timer.start_time = None
                return True
        return False
        
    def resume_timer(self, timer_id: str) -> bool:
        """Resume a paused timer"""
        if timer_id in self.timers:
            timer = self.timers[timer_id]
            if timer.paused and timer.remaining:
                timer.start_time = time.time()
                timer.duration_seconds = timer.remaining
                timer.paused = False
                return True
        return False
        
    def cancel_timer(self, timer_id: str) -> bool:
        """Cancel a timer"""
        if timer_id in self.timers:
            del self.timers[timer_id]
            return True
        return False
        
    def get_remaining(self, timer_id: str) -> Optional[int]:
        """Get remaining seconds for a timer"""
        if timer_id not in self.timers:
            return None
        timer = self.timers[timer_id]
        if timer.paused:
            return timer.remaining
        if timer.start_time:
            elapsed = time.time() - timer.start_time
            return max(0, timer.duration_seconds - int(elapsed))
        return None
        
    def list_timers(self) -> List[Dict]:
        """List all active timers with remaining time"""
        result = []
        for timer in self.timers.values():
            remaining = self.get_remaining(timer.id)
            result.append({
                "id": timer.id,
                "label": timer.label,
                "remaining": remaining,
                "paused": timer.paused
            })
        return result
        
    def on_timer_complete(self, callback: Callable[[Timer], None]):
        """Register callback for timer completion"""
        self._callbacks.append(callback)
        
    def _start_if_needed(self):
        """Start monitor thread if not running"""
        if not self._running and self.timers:
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            
    def _monitor_loop(self):
        """Monitor timers"""
        while self._running and self.timers:
            completed = []
            
            for timer in self.timers.values():
                if timer.paused:
                    continue
                remaining = self.get_remaining(timer.id)
                if remaining is not None and remaining <= 0:
                    completed.append(timer)
                    
            for timer in completed:
                for callback in self._callbacks:
                    try:
                        callback(timer)
                    except Exception:
                        pass
                del self.timers[timer.id]
                
            time.sleep(1)
            
        self._running = False


class FocusMode:
    """Focus mode - blocks distracting sites and apps"""
    
    HOSTS_FILE = r"C:\Windows\System32\drivers\etc\hosts" if platform.system() == "Windows" else "/etc/hosts"
    REDIRECT_IP = "127.0.0.1"
    
    DEFAULT_BLOCKED_SITES = [
        "facebook.com", "www.facebook.com",
        "twitter.com", "www.twitter.com", "x.com", "www.x.com",
        "instagram.com", "www.instagram.com",
        "tiktok.com", "www.tiktok.com",
        "reddit.com", "www.reddit.com",
        "youtube.com", "www.youtube.com",
        "netflix.com", "www.netflix.com",
        "twitch.tv", "www.twitch.tv",
    ]
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.config_file = self.data_dir / "focus_config.json"
        self.active = False
        self.end_time: Optional[datetime.datetime] = None
        self.blocked_sites: List[str] = []
        self.blocked_apps: List[str] = []
        self._thread: Optional[threading.Thread] = None
        self._load_config()
        
    def _load_config(self):
        """Load focus mode config"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.blocked_sites = data.get('blocked_sites', self.DEFAULT_BLOCKED_SITES)
                    self.blocked_apps = data.get('blocked_apps', [])
            except Exception:
                self.blocked_sites = self.DEFAULT_BLOCKED_SITES.copy()
                
    def _save_config(self):
        """Save focus mode config"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump({
                    'blocked_sites': self.blocked_sites,
                    'blocked_apps': self.blocked_apps
                }, f, indent=2)
        except Exception:
            pass
            
    def add_blocked_site(self, site: str):
        """Add a site to block list"""
        if site not in self.blocked_sites:
            self.blocked_sites.append(site)
            if not site.startswith("www."):
                self.blocked_sites.append(f"www.{site}")
            self._save_config()
            
    def remove_blocked_site(self, site: str):
        """Remove a site from block list"""
        self.blocked_sites = [s for s in self.blocked_sites if site not in s]
        self._save_config()
        
    def add_blocked_app(self, app: str):
        """Add an app to block list"""
        if app not in self.blocked_apps:
            self.blocked_apps.append(app)
            self._save_config()
            
    def start(self, duration_minutes: int = 60) -> str:
        """Start focus mode
        
        Args:
            duration_minutes: How long to enable focus mode
            
        Returns:
            Status message
        """
        if self.active:
            return "Focus mode is already active"
            
        self.active = True
        self.end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)
        
        # Block sites (requires admin on Windows)
        blocked_count = self._block_sites()
        
        # Start monitoring thread
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
        return f"✅ Focus mode enabled for {duration_minutes} minutes. {blocked_count} sites blocked."
        
    def stop(self) -> str:
        """Stop focus mode"""
        if not self.active:
            return "Focus mode is not active"
            
        self.active = False
        self.end_time = None
        
        # Unblock sites
        self._unblock_sites()
        
        return "✅ Focus mode disabled. Sites unblocked."
        
    def get_status(self) -> Dict:
        """Get focus mode status"""
        remaining = None
        if self.active and self.end_time:
            remaining = (self.end_time - datetime.datetime.now()).total_seconds()
            remaining = max(0, int(remaining / 60))
            
        return {
            "active": self.active,
            "remaining_minutes": remaining,
            "blocked_sites": len(self.blocked_sites),
            "blocked_apps": len(self.blocked_apps)
        }
        
    def _block_sites(self) -> int:
        """Block sites by modifying hosts file (requires admin)"""
        try:
            # Read current hosts
            with open(self.HOSTS_FILE, 'r') as f:
                content = f.read()
                
            # Add blocking entries
            lines_added = 0
            new_entries = []
            for site in self.blocked_sites:
                entry = f"{self.REDIRECT_IP} {site}"
                if entry not in content:
                    new_entries.append(entry)
                    lines_added += 1
                    
            if new_entries:
                with open(self.HOSTS_FILE, 'a') as f:
                    f.write("\n# LADA Focus Mode - Start\n")
                    f.write("\n".join(new_entries))
                    f.write("\n# LADA Focus Mode - End\n")
                    
            # Flush DNS
            if platform.system() == "Windows":
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
            else:
                subprocess.run(["systemd-resolve", "--flush-caches"], capture_output=True)
                
            return lines_added
        except PermissionError:
            return 0  # Need admin rights
        except Exception:
            return 0
            
    def _unblock_sites(self):
        """Remove blocked sites from hosts file"""
        try:
            with open(self.HOSTS_FILE, 'r') as f:
                lines = f.readlines()
                
            # Remove LADA focus mode entries
            in_lada_block = False
            new_lines = []
            for line in lines:
                if "LADA Focus Mode - Start" in line:
                    in_lada_block = True
                    continue
                elif "LADA Focus Mode - End" in line:
                    in_lada_block = False
                    continue
                elif not in_lada_block:
                    new_lines.append(line)
                    
            with open(self.HOSTS_FILE, 'w') as f:
                f.writelines(new_lines)
                
            # Flush DNS
            if platform.system() == "Windows":
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        except Exception:
            pass
            
    def _kill_blocked_apps(self):
        """Kill blocked applications"""
        for app in self.blocked_apps:
            try:
                if platform.system() == "Windows":
                    subprocess.run(["taskkill", "/IM", f"{app}.exe", "/F"], 
                                 capture_output=True)
                else:
                    subprocess.run(["pkill", "-f", app], capture_output=True)
            except Exception:
                pass
                
    def _monitor_loop(self):
        """Monitor focus mode"""
        while self.active:
            now = datetime.datetime.now()
            
            # Check if time expired
            if self.end_time and now >= self.end_time:
                self.stop()
                break
                
            # Kill blocked apps
            self._kill_blocked_apps()
            
            time.sleep(30)


class InternetSpeedTest:
    """Test internet connection speed"""
    
    # Test servers and file URLs
    TEST_URLS = [
        ("https://speed.cloudflare.com/__down?bytes=10000000", 10_000_000),  # 10MB
        ("https://proof.ovh.net/files/10Mb.dat", 10_000_000),
        ("http://speedtest.tele2.net/10MB.zip", 10_000_000),
    ]
    
    @staticmethod
    def test_download_speed() -> Dict:
        """Test download speed
        
        Returns:
            Dict with speed in Mbps, time taken, and status
        """
        for url, expected_size in InternetSpeedTest.TEST_URLS:
            try:
                start_time = time.time()
                
                # Download file
                req = urllib.request.Request(url, headers={'User-Agent': 'LADA/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = response.read()
                    
                end_time = time.time()
                elapsed = end_time - start_time
                
                # Calculate speed
                bytes_downloaded = len(data)
                bits = bytes_downloaded * 8
                mbps = (bits / elapsed) / 1_000_000
                
                return {
                    "status": "success",
                    "download_mbps": round(mbps, 2),
                    "bytes": bytes_downloaded,
                    "time_seconds": round(elapsed, 2),
                    "server": url.split("/")[2]
                }
                
            except Exception:
                continue
                
        return {
            "status": "error",
            "message": "Could not connect to any speed test server"
        }
        
    @staticmethod
    def test_latency(host: str = "8.8.8.8") -> Dict:
        """Test network latency (ping)"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["ping", "-n", "4", host],
                    capture_output=True, text=True, timeout=10
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "4", host],
                    capture_output=True, text=True, timeout=10
                )
                
            output = result.stdout
            
            # Parse average latency
            if platform.system() == "Windows":
                # Average = 15ms
                import re
                match = re.search(r"Average = (\d+)ms", output)
                if match:
                    return {
                        "status": "success",
                        "latency_ms": int(match.group(1)),
                        "host": host
                    }
            else:
                # rtt min/avg/max/mdev = 10.123/15.456/20.789/5.000 ms
                import re
                match = re.search(r"rtt .* = [\d.]+/([\d.]+)/", output)
                if match:
                    return {
                        "status": "success",
                        "latency_ms": round(float(match.group(1)), 1),
                        "host": host
                    }
                    
            return {"status": "error", "message": "Could not parse ping output"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
            
    @staticmethod
    def full_test() -> Dict:
        """Run full speed test (download + latency)"""
        download = InternetSpeedTest.test_download_speed()
        latency = InternetSpeedTest.test_latency()
        
        return {
            "download": download,
            "latency": latency,
            "timestamp": datetime.datetime.now().isoformat()
        }


class BackupManager:
    """File backup and restore"""
    
    def __init__(self, backup_dir: str = None):
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            self.backup_dir = Path.home() / ".lada" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def backup_file(self, file_path: str) -> Dict:
        """Backup a single file"""
        try:
            src = Path(file_path)
            if not src.exists():
                return {"status": "error", "message": "File not found"}
                
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{src.name}.{timestamp}.bak"
            dest = self.backup_dir / backup_name
            
            import shutil
            shutil.copy2(src, dest)
            
            return {
                "status": "success",
                "source": str(src),
                "backup": str(dest),
                "size": dest.stat().st_size
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
            
    def backup_folder(self, folder_path: str, compress: bool = True) -> Dict:
        """Backup an entire folder"""
        try:
            src = Path(folder_path)
            if not src.exists():
                return {"status": "error", "message": "Folder not found"}
                
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{src.name}_{timestamp}"
            
            if compress:
                import shutil
                dest = self.backup_dir / backup_name
                archive = shutil.make_archive(str(dest), 'zip', str(src))
                return {
                    "status": "success",
                    "source": str(src),
                    "backup": archive,
                    "compressed": True
                }
            else:
                dest = self.backup_dir / backup_name
                import shutil
                shutil.copytree(src, dest)
                return {
                    "status": "success",
                    "source": str(src),
                    "backup": str(dest),
                    "compressed": False
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
            
    def list_backups(self) -> List[Dict]:
        """List all backups"""
        backups = []
        for item in self.backup_dir.iterdir():
            backups.append({
                "name": item.name,
                "path": str(item),
                "size": item.stat().st_size if item.is_file() else None,
                "created": datetime.datetime.fromtimestamp(item.stat().st_ctime).isoformat()
            })
        return sorted(backups, key=lambda x: x['created'], reverse=True)
        
    def restore_backup(self, backup_path: str, restore_to: str = None) -> Dict:
        """Restore from backup"""
        try:
            src = Path(backup_path)
            if not src.exists():
                return {"status": "error", "message": "Backup not found"}
                
            if restore_to:
                dest = Path(restore_to)
            else:
                # Restore to original location (remove timestamp from name)
                name_parts = src.stem.split('.')
                if len(name_parts) > 1:
                    original_name = '.'.join(name_parts[:-1])
                else:
                    original_name = src.stem
                dest = Path.home() / "Restored" / original_name
                
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            if src.suffix == '.zip':
                import shutil
                shutil.unpack_archive(src, dest)
            else:
                import shutil
                shutil.copy2(src, dest)
                
            return {
                "status": "success",
                "source": str(src),
                "restored_to": str(dest)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
            
    def delete_old_backups(self, keep_days: int = 30) -> Dict:
        """Delete backups older than X days"""
        try:
            cutoff = datetime.datetime.now() - datetime.timedelta(days=keep_days)
            deleted = 0
            
            for item in self.backup_dir.iterdir():
                created = datetime.datetime.fromtimestamp(item.stat().st_ctime)
                if created < cutoff:
                    if item.is_file():
                        item.unlink()
                    else:
                        import shutil
                        shutil.rmtree(item)
                    deleted += 1
                    
            return {
                "status": "success",
                "deleted_count": deleted,
                "kept_days": keep_days
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ============================================================
# POMODORO TIMER
# ============================================================

@dataclass
class PomodoroSession:
    """Track a Pomodoro session"""
    session_id: str
    work_minutes: int
    short_break_minutes: int
    long_break_minutes: int
    sessions_until_long_break: int
    current_session: int = 1
    total_work_completed: int = 0  # In minutes
    is_break: bool = False
    started_at: Optional[str] = None
    state: str = "idle"  # idle, working, short_break, long_break, paused


class PomodoroTimer:
    """
    Pomodoro Technique Timer
    
    The Pomodoro Technique:
    1. Work for 25 minutes
    2. Take a 5 minute break
    3. After 4 pomodoros, take a 15-30 minute long break
    4. Repeat
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.history_file = self.data_dir / "pomodoro_history.json"
        
        # Default Pomodoro settings
        self.work_minutes = 25
        self.short_break_minutes = 5
        self.long_break_minutes = 15
        self.sessions_until_long_break = 4
        
        # Current session state
        self.session: Optional[PomodoroSession] = None
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._remaining_seconds = 0
        self._start_time: Optional[float] = None
        
        # Callbacks
        self._on_work_start: List[Callable] = []
        self._on_break_start: List[Callable] = []
        self._on_session_complete: List[Callable] = []
        self._on_tick: List[Callable] = []  # Called every second with remaining time
        
        # Statistics
        self.history: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """Load Pomodoro history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except Exception as e:
                self.history = []
    
    def _save_history(self):
        """Save Pomodoro history to file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            pass
    
    def configure(
        self,
        work_minutes: int = 25,
        short_break_minutes: int = 5,
        long_break_minutes: int = 15,
        sessions_until_long_break: int = 4
    ):
        """
        Configure Pomodoro timer settings.
        
        Args:
            work_minutes: Duration of work session (default: 25)
            short_break_minutes: Duration of short break (default: 5)
            long_break_minutes: Duration of long break (default: 15)
            sessions_until_long_break: Sessions before long break (default: 4)
        """
        self.work_minutes = work_minutes
        self.short_break_minutes = short_break_minutes
        self.long_break_minutes = long_break_minutes
        self.sessions_until_long_break = sessions_until_long_break
    
    def start(self, task_name: str = "Focus Session") -> Dict:
        """
        Start a new Pomodoro session.
        
        Args:
            task_name: Name of the task to work on
            
        Returns:
            Dict with session details
        """
        if self._running:
            return {
                "status": "already_running",
                "message": "A Pomodoro session is already in progress",
                "remaining": self.get_remaining()
            }
        
        session_id = f"pomo_{int(time.time())}"
        self.session = PomodoroSession(
            session_id=session_id,
            work_minutes=self.work_minutes,
            short_break_minutes=self.short_break_minutes,
            long_break_minutes=self.long_break_minutes,
            sessions_until_long_break=self.sessions_until_long_break,
            started_at=datetime.datetime.now().isoformat()
        )
        
        self._remaining_seconds = self.work_minutes * 60
        self._running = True
        self._paused = False
        self.session.state = "working"
        self._start_time = time.time()
        
        # Start the timer thread
        self._thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._thread.start()
        
        # Notify work start callbacks
        for callback in self._on_work_start:
            try:
                callback(task_name, self.work_minutes)
            except Exception as e:
                pass
        
        return {
            "status": "started",
            "session_id": session_id,
            "task": task_name,
            "work_minutes": self.work_minutes,
            "message": f"🍅 Pomodoro started! Focus for {self.work_minutes} minutes."
        }
    
    def pause(self) -> Dict:
        """Pause the current Pomodoro session"""
        if not self._running:
            return {"status": "not_running", "message": "No active Pomodoro session"}
        
        if self._paused:
            return {"status": "already_paused", "message": "Already paused"}
        
        self._paused = True
        if self.session:
            self.session.state = "paused"
        
        return {
            "status": "paused",
            "remaining": self.get_remaining(),
            "message": "⏸️ Pomodoro paused"
        }
    
    def resume(self) -> Dict:
        """Resume a paused Pomodoro session"""
        if not self._running:
            return {"status": "not_running", "message": "No active Pomodoro session"}
        
        if not self._paused:
            return {"status": "not_paused", "message": "Not paused"}
        
        self._paused = False
        self._start_time = time.time()
        if self.session:
            self.session.state = "working" if not self.session.is_break else "break"
        
        return {
            "status": "resumed",
            "remaining": self.get_remaining(),
            "message": "▶️ Pomodoro resumed"
        }
    
    def stop(self) -> Dict:
        """Stop the current Pomodoro session"""
        if not self._running:
            return {"status": "not_running", "message": "No active Pomodoro session"}
        
        self._running = False
        self._paused = False
        
        # Record the session (even if incomplete)
        if self.session:
            self.history.append({
                "session_id": self.session.session_id,
                "started_at": self.session.started_at,
                "ended_at": datetime.datetime.now().isoformat(),
                "completed": False,
                "work_minutes_completed": self.session.total_work_completed,
                "sessions_completed": self.session.current_session - 1
            })
            self._save_history()
            self.session.state = "idle"
        
        remaining = self.get_remaining()
        self.session = None
        
        return {
            "status": "stopped",
            "remaining_when_stopped": remaining,
            "message": "🛑 Pomodoro stopped"
        }
    
    def skip_break(self) -> Dict:
        """Skip the current break and start next work session"""
        if not self._running or not self.session or not self.session.is_break:
            return {"status": "not_on_break", "message": "Not currently on a break"}
        
        self._start_work_session()
        
        return {
            "status": "break_skipped",
            "message": "⏭️ Break skipped! Starting work session."
        }
    
    def get_status(self) -> Dict:
        """Get current Pomodoro status"""
        if not self._running or not self.session:
            return {
                "active": False,
                "state": "idle",
                "message": "No active Pomodoro session"
            }
        
        remaining = self.get_remaining()
        
        return {
            "active": True,
            "state": self.session.state,
            "is_break": self.session.is_break,
            "current_session": self.session.current_session,
            "total_sessions": self.sessions_until_long_break,
            "remaining_seconds": remaining['seconds'],
            "remaining_formatted": remaining['formatted'],
            "work_minutes_completed": self.session.total_work_completed,
            "paused": self._paused
        }
    
    def get_remaining(self) -> Dict:
        """Get remaining time in current period"""
        if not self._running:
            return {"seconds": 0, "formatted": "00:00"}
        
        if self._paused:
            seconds = self._remaining_seconds
        else:
            elapsed = time.time() - self._start_time if self._start_time else 0
            seconds = max(0, self._remaining_seconds - int(elapsed))
        
        minutes = seconds // 60
        secs = seconds % 60
        
        return {
            "seconds": seconds,
            "formatted": f"{minutes:02d}:{secs:02d}"
        }
    
    def get_statistics(self, days: int = 7) -> Dict:
        """Get Pomodoro statistics for the last N days"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        
        recent = []
        for session in self.history:
            try:
                started = datetime.datetime.fromisoformat(session['started_at'])
                if started >= cutoff:
                    recent.append(session)
            except Exception as e:
                pass
        
        total_work_minutes = sum(s.get('work_minutes_completed', 0) for s in recent)
        completed_sessions = sum(1 for s in recent if s.get('completed', False))
        
        return {
            "period_days": days,
            "total_sessions": len(recent),
            "completed_sessions": completed_sessions,
            "total_work_minutes": total_work_minutes,
            "total_work_hours": round(total_work_minutes / 60, 1),
            "average_daily_minutes": round(total_work_minutes / days, 1) if days > 0 else 0
        }
    
    def on_work_start(self, callback: Callable[[str, int], None]):
        """Register callback for work session start"""
        self._on_work_start.append(callback)
    
    def on_break_start(self, callback: Callable[[bool, int], None]):
        """Register callback for break start (is_long_break, minutes)"""
        self._on_break_start.append(callback)
    
    def on_session_complete(self, callback: Callable[[Dict], None]):
        """Register callback for full Pomodoro cycle complete"""
        self._on_session_complete.append(callback)
    
    def on_tick(self, callback: Callable[[int], None]):
        """Register callback for each second (remaining_seconds)"""
        self._on_tick.append(callback)
    
    def _timer_loop(self):
        """Background timer loop"""
        while self._running:
            if self._paused:
                time.sleep(0.5)
                continue
            
            elapsed = time.time() - self._start_time if self._start_time else 0
            remaining = self._remaining_seconds - int(elapsed)
            
            # Notify tick callbacks
            for callback in self._on_tick:
                try:
                    callback(remaining)
                except Exception as e:
                    pass
            
            if remaining <= 0:
                # Period complete
                if self.session.is_break:
                    self._start_work_session()
                else:
                    self._start_break()
            else:
                time.sleep(1)
    
    def _start_work_session(self):
        """Start a work session"""
        if self.session:
            self.session.is_break = False
            self.session.state = "working"
            self._remaining_seconds = self.work_minutes * 60
            self._start_time = time.time()
            
            # Notify callbacks
            for callback in self._on_work_start:
                try:
                    callback("Work Session", self.work_minutes)
                except Exception as e:
                    pass
    
    def _start_break(self):
        """Start a break session"""
        if not self.session:
            return
        
        # Record completed work
        self.session.total_work_completed += self.work_minutes
        
        # Check if long break
        is_long_break = (self.session.current_session % self.sessions_until_long_break) == 0
        
        if is_long_break:
            break_minutes = self.long_break_minutes
            self.session.state = "long_break"
        else:
            break_minutes = self.short_break_minutes
            self.session.state = "short_break"
        
        self.session.is_break = True
        self.session.current_session += 1
        self._remaining_seconds = break_minutes * 60
        self._start_time = time.time()
        
        # Play notification sound
        self._play_notification()
        
        # Notify callbacks
        for callback in self._on_break_start:
            try:
                callback(is_long_break, break_minutes)
            except Exception as e:
                pass
    
    def _play_notification(self):
        """Play notification sound"""
        try:
            if platform.system() == "Windows":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            elif platform.system() == "Darwin":
                subprocess.run(['afplay', '/System/Library/Sounds/Glass.aiff'], check=False)
            else:
                proc = subprocess.run(
                    ['paplay', '/usr/share/sounds/freedesktop/stereo/complete.oga'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if proc.returncode != 0:
                    print('\a', end='')
        except Exception as e:
            pass


# Convenience class that combines all productivity tools
class ProductivityManager:
    """Unified manager for all productivity tools"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.alarms = AlarmManager(data_dir)
        self.reminders = ReminderManager(data_dir)
        self.timers = TimerManager()
        self.focus = FocusMode(data_dir)
        self.backup = BackupManager()
        self.speed_test = InternetSpeedTest
        self.pomodoro = PomodoroTimer(data_dir)  # NEW: Pomodoro Timer
        
    def start_all_monitoring(self):
        """Start all background monitors"""
        self.alarms.start_monitoring()
        self.reminders.start_monitoring()
        
    def stop_all_monitoring(self):
        """Stop all monitors"""
        self.alarms.stop_monitoring()
        self.reminders.stop_monitoring()
        self.focus.stop()
        if self.pomodoro._running:
            self.pomodoro.stop()
