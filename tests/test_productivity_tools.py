"""
Tests for Productivity Tools Module
Tests: Alarms, Reminders, Timers, Focus Mode, Backup, Internet Speed
"""

import pytest
import time
import datetime
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.productivity_tools import (
    Alarm, Reminder, Timer,
    AlarmManager, ReminderManager, TimerManager,
    FocusMode, InternetSpeedTest, BackupManager,
    ProductivityManager
)


class TestAlarm:
    """Test Alarm dataclass"""
    
    def test_alarm_creation(self):
        alarm = Alarm(id="test1", time="07:30", label="Wake up")
        assert alarm.id == "test1"
        assert alarm.time == "07:30"
        assert alarm.label == "Wake up"
        assert alarm.enabled == True
        assert alarm.days == []
        
    def test_alarm_with_days(self):
        alarm = Alarm(id="test2", time="09:00", days=["Mon", "Wed", "Fri"])
        assert alarm.days == ["Mon", "Wed", "Fri"]


class TestAlarmManager:
    """Test AlarmManager class"""
    
    @pytest.fixture
    def alarm_manager(self, tmp_path):
        return AlarmManager(str(tmp_path))
        
    def test_create_alarm(self, alarm_manager):
        alarm = alarm_manager.create_alarm("08:00", "Morning alarm")
        assert alarm.time == "08:00"
        assert alarm.label == "Morning alarm"
        assert alarm.id in alarm_manager.alarms
        
    def test_delete_alarm(self, alarm_manager):
        alarm = alarm_manager.create_alarm("08:00")
        assert alarm_manager.delete_alarm(alarm.id) == True
        assert alarm.id not in alarm_manager.alarms
        
    def test_delete_nonexistent_alarm(self, alarm_manager):
        assert alarm_manager.delete_alarm("nonexistent") == False
        
    def test_list_alarms(self, tmp_path):
        import uuid
        alarm_manager = AlarmManager(str(tmp_path / f"alarms_{uuid.uuid4().hex[:8]}"))
        alarm_manager.create_alarm("08:00")
        alarm_manager.create_alarm("09:00")
        alarms = alarm_manager.list_alarms()
        assert len(alarms) == 2
        
    def test_toggle_alarm(self, alarm_manager):
        alarm = alarm_manager.create_alarm("08:00")
        assert alarm.enabled == True
        result = alarm_manager.toggle_alarm(alarm.id)
        assert result == False
        assert alarm_manager.alarms[alarm.id].enabled == False
        
    def test_persistence(self, tmp_path):
        # Create alarms with first manager
        am1 = AlarmManager(str(tmp_path))
        am1.create_alarm("07:00", "Saved alarm")
        
        # Create second manager to load from file
        am2 = AlarmManager(str(tmp_path))
        alarms = am2.list_alarms()
        assert len(alarms) == 1
        assert alarms[0].label == "Saved alarm"
        
    def test_callback_registration(self, alarm_manager):
        callback = Mock()
        alarm_manager.on_alarm(callback)
        assert callback in alarm_manager._callbacks


class TestReminderManager:
    """Test ReminderManager class"""
    
    @pytest.fixture
    def reminder_manager(self, tmp_path):
        return ReminderManager(str(tmp_path))
        
    def test_create_reminder(self, reminder_manager):
        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        reminder = reminder_manager.create_reminder("Test reminder", future)
        assert reminder.message == "Test reminder"
        assert reminder.trigger_time == future
        
    def test_create_reminder_in(self, reminder_manager):
        reminder = reminder_manager.create_reminder_in("In 30 minutes", minutes=30)
        assert reminder.message == "In 30 minutes"
        expected = datetime.datetime.now() + datetime.timedelta(minutes=30)
        # Allow 1 second tolerance
        assert abs((reminder.trigger_time - expected).total_seconds()) < 1
        
    def test_delete_reminder(self, reminder_manager):
        reminder = reminder_manager.create_reminder_in("Test", minutes=5)
        assert reminder_manager.delete_reminder(reminder.id) == True
        
    def test_list_reminders(self, tmp_path):
        import uuid
        reminder_manager = ReminderManager(str(tmp_path / f"reminders_{uuid.uuid4().hex[:8]}"))
        reminder_manager.create_reminder_in("Test 1", minutes=10)
        reminder_manager.create_reminder_in("Test 2", minutes=20)
        reminders = reminder_manager.list_reminders()
        assert len(reminders) == 2
        # Should be sorted by trigger time
        assert reminders[0].trigger_time < reminders[1].trigger_time


class TestTimerManager:
    """Test TimerManager class"""
    
    @pytest.fixture
    def timer_manager(self):
        return TimerManager()
        
    def test_create_timer(self, timer_manager):
        timer = timer_manager.create_timer(minutes=5, label="Pomodoro")
        assert timer.label == "Pomodoro"
        assert timer.duration_seconds == 300  # 5 minutes
        
    def test_pause_resume_timer(self, timer_manager):
        timer = timer_manager.create_timer(minutes=1)
        time.sleep(0.1)
        
        assert timer_manager.pause_timer(timer.id) == True
        assert timer_manager.timers[timer.id].paused == True
        
        assert timer_manager.resume_timer(timer.id) == True
        assert timer_manager.timers[timer.id].paused == False
        
    def test_cancel_timer(self, timer_manager):
        timer = timer_manager.create_timer(seconds=30)
        assert timer_manager.cancel_timer(timer.id) == True
        assert timer.id not in timer_manager.timers
        
    def test_get_remaining(self, timer_manager):
        timer = timer_manager.create_timer(seconds=60)
        time.sleep(0.5)
        remaining = timer_manager.get_remaining(timer.id)
        assert remaining is not None
        assert remaining <= 60
        assert remaining >= 58
        
    def test_list_timers(self):
        timer_manager = TimerManager()
        timer_manager.create_timer(minutes=1, label="Timer 1")
        timer_manager.create_timer(minutes=2, label="Timer 2")
        timers = timer_manager.list_timers()
        assert len(timers) >= 1


class TestFocusMode:
    """Test FocusMode class"""
    
    @pytest.fixture
    def focus_mode(self, tmp_path):
        return FocusMode(str(tmp_path))
        
    def test_initial_state(self, focus_mode):
        status = focus_mode.get_status()
        assert status["active"] == False
        assert status["remaining_minutes"] is None
        
    def test_add_blocked_site(self, focus_mode):
        focus_mode.add_blocked_site("example.com")
        assert "example.com" in focus_mode.blocked_sites
        assert "www.example.com" in focus_mode.blocked_sites
        
    def test_remove_blocked_site(self, focus_mode):
        focus_mode.add_blocked_site("test.com")
        focus_mode.remove_blocked_site("test.com")
        assert "test.com" not in focus_mode.blocked_sites
        
    def test_add_blocked_app(self, focus_mode):
        focus_mode.add_blocked_app("discord")
        assert "discord" in focus_mode.blocked_apps
        
    @patch.object(FocusMode, '_block_sites')
    def test_start_focus_mode(self, mock_block, focus_mode):
        mock_block.return_value = 5
        result = focus_mode.start(duration_minutes=30)
        assert "enabled" in result.lower() or "✅" in result
        assert focus_mode.active == True
        focus_mode.stop()
        
    @patch.object(FocusMode, '_unblock_sites')
    def test_stop_focus_mode(self, mock_unblock, focus_mode):
        focus_mode.active = True
        result = focus_mode.stop()
        assert "disabled" in result.lower() or "✅" in result
        assert focus_mode.active == False


class TestInternetSpeedTest:
    """Test InternetSpeedTest class"""
    
    @patch('urllib.request.urlopen')
    def test_download_speed(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.read.return_value = b'x' * 1000000  # 1MB
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response
        
        result = InternetSpeedTest.test_download_speed()
        assert result["status"] == "success"
        assert "download_mbps" in result
        
    @patch('subprocess.run')
    def test_latency_windows(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Average = 15ms",
            returncode=0
        )
        
        with patch('platform.system', return_value='Windows'):
            result = InternetSpeedTest.test_latency()
            assert result["status"] == "success"
            assert result["latency_ms"] == 15


class TestBackupManager:
    """Test BackupManager class"""
    
    @pytest.fixture
    def backup_manager(self, tmp_path):
        backup_dir = tmp_path / "backups"
        return BackupManager(str(backup_dir))
        
    def test_backup_file(self, backup_manager, tmp_path):
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")
        
        result = backup_manager.backup_file(str(test_file))
        assert result["status"] == "success"
        assert Path(result["backup"]).exists()
        
    def test_backup_nonexistent_file(self, backup_manager):
        result = backup_manager.backup_file("/nonexistent/file.txt")
        assert result["status"] == "error"
        
    def test_backup_folder(self, backup_manager, tmp_path):
        # Create test folder with files
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file1.txt").write_text("Content 1")
        (test_folder / "file2.txt").write_text("Content 2")
        
        result = backup_manager.backup_folder(str(test_folder), compress=True)
        assert result["status"] == "success"
        assert result["compressed"] == True
        
    def test_list_backups(self, backup_manager, tmp_path):
        # Create some backups
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")
        backup_manager.backup_file(str(test_file))
        
        backups = backup_manager.list_backups()
        assert len(backups) >= 1


class TestProductivityManager:
    """Test ProductivityManager unified class"""
    
    @pytest.fixture
    def productivity(self, tmp_path):
        return ProductivityManager(str(tmp_path))
        
    def test_all_managers_initialized(self, productivity):
        assert productivity.alarms is not None
        assert productivity.reminders is not None
        assert productivity.timers is not None
        assert productivity.focus is not None
        assert productivity.backup is not None
        
    def test_start_stop_monitoring(self, productivity):
        productivity.start_all_monitoring()
        assert productivity.alarms._running == True
        assert productivity.reminders._running == True
        
        productivity.stop_all_monitoring()
        assert productivity.alarms._running == False
        assert productivity.reminders._running == False
