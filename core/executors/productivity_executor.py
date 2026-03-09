"""
LADA Productivity Executor — Handles alarms, reminders, timers, focus mode,
speed test, backup, Gmail, Calendar, Spotify, and smart home commands.

Extracted from JarvisCommandProcessor.process() productivity/integration blocks.
"""

import re
import logging
from typing import Tuple

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class ProductivityExecutor(BaseExecutor):
    """Handles productivity and integration commands (alarms, reminders, timers,
    focus, backup, Gmail, Calendar, Spotify, smart home)."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        # --- Productivity subsystem (alarms, reminders, timers, focus, speed test, backup) ---
        if self.core.productivity:
            for handler in [
                self._handle_alarms,
                self._handle_reminders,
                self._handle_timers,
                self._handle_focus,
                self._handle_speed_test,
                self._handle_backup,
            ]:
                handled, resp = handler(cmd)
                if handled:
                    return True, resp

        # --- Gmail ---
        handled, resp = self._handle_gmail(cmd)
        if handled:
            return True, resp

        # --- Calendar ---
        handled, resp = self._handle_calendar(cmd)
        if handled:
            return True, resp

        # --- Spotify ---
        handled, resp = self._handle_spotify(cmd)
        if handled:
            return True, resp

        # --- Smart Home ---
        handled, resp = self._handle_smart_home(cmd)
        if handled:
            return True, resp

        # --- Focus Modes (advanced) ---
        handled, resp = self._handle_focus_modes(cmd)
        if handled:
            return True, resp

        return False, ""

    # ── Alarms ───────────────────────────────────────────────

    def _handle_alarms(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['set alarm', 'create alarm', 'wake me', 'alarm for']):
            match = re.search(r'(?:at\s+|for\s+)?(\d{1,2})[:\s]?(\d{2})?\s*(am|pm)?', cmd)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                ampm = match.group(3)
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                time_str = f"{hour:02d}:{minute:02d}"
                label = "Alarm"
                if 'wake' in cmd:
                    label = "Wake up"
                alarm = self.core.productivity.alarms.create_alarm(time_str, label)
                return True, f"⏰ Alarm set for {time_str}. ID: {alarm.id}"
            return True, "What time should I set the alarm for? (e.g., 'set alarm for 7:30 am')"

        if any(x in cmd for x in ['list alarms', 'show alarms', 'my alarms']):
            alarms = self.core.productivity.alarms.list_alarms()
            if alarms:
                alarm_list = '\n'.join([f"  • {a.time} - {a.label} ({'✅' if a.enabled else '❌'})" for a in alarms])
                return True, f"⏰ Your alarms:\n{alarm_list}"
            return True, "You don't have any alarms set."

        if any(x in cmd for x in ['delete alarm', 'remove alarm', 'cancel alarm']):
            match = re.search(r'(\d{1,2}:\d{2})', cmd)
            if match:
                time_str = match.group(1)
                for alarm in self.core.productivity.alarms.list_alarms():
                    if alarm.time == time_str:
                        self.core.productivity.alarms.delete_alarm(alarm.id)
                        return True, f"⏰ Deleted alarm for {time_str}."
            return True, "Which alarm should I delete? (e.g., 'delete alarm 7:30')"

        return False, ""

    # ── Reminders ────────────────────────────────────────────

    def _handle_reminders(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['remind me', 'set reminder', 'create reminder']):
            match_in = re.search(r'in\s+(\d+)\s*(minutes?|hours?|mins?|hrs?)', cmd)
            if match_in:
                amount = int(match_in.group(1))
                unit = match_in.group(2).lower()
                mins = amount if 'min' in unit else amount * 60
                msg_match = re.search(r'(?:remind me|reminder)\s+(?:to\s+)?(.+?)\s+in\s+', cmd)
                message = msg_match.group(1) if msg_match else "Reminder"
                self.core.productivity.reminders.create_reminder_in(message, minutes=mins)
                return True, f"📝 I'll remind you in {amount} {unit}: '{message}'"

            msg_match = re.search(r'(?:remind me|reminder)\s+(?:to\s+)?(.+)', cmd)
            if msg_match:
                message = msg_match.group(1)
                self.core.productivity.reminders.create_reminder_in(message, minutes=30)
                return True, f"📝 Reminder set for 30 minutes: '{message}'"
            return True, "What should I remind you about? (e.g., 'remind me to call mom in 30 minutes')"

        if any(x in cmd for x in ['list reminders', 'show reminders', 'my reminders']):
            reminders = self.core.productivity.reminders.list_reminders()
            if reminders:
                rem_list = '\n'.join([f"  • {r.message} - {r.trigger_time.strftime('%H:%M')}" for r in reminders[:10]])
                return True, f"📝 Your reminders:\n{rem_list}"
            return True, "You don't have any active reminders."

        return False, ""

    # ── Timers ───────────────────────────────────────────────

    def _handle_timers(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['set timer', 'start timer', 'timer for']):
            match = re.search(r'(\d+)\s*(minutes?|seconds?|hours?|mins?|secs?|hrs?)', cmd)
            if match:
                amount = int(match.group(1))
                unit = match.group(2).lower()
                label_match = re.search(r'(?:called|named|for)\s+(\w+)', cmd)
                label = label_match.group(1) if label_match else "Timer"

                if 'sec' in unit:
                    timer = self.core.productivity.timers.create_timer(seconds=amount, label=label)
                elif 'hour' in unit or 'hr' in unit:
                    timer = self.core.productivity.timers.create_timer(hours=amount, label=label)
                else:
                    timer = self.core.productivity.timers.create_timer(minutes=amount, label=label)
                return True, f"⏱️ Timer set for {amount} {unit}. ID: {timer.id}"
            return True, "How long should the timer be? (e.g., 'set timer for 5 minutes')"

        if any(x in cmd for x in ['pause timer', 'stop timer']):
            timers = self.core.productivity.timers.list_timers()
            if timers:
                self.core.productivity.timers.pause_timer(timers[0]['id'])
                return True, f"⏸️ Timer paused. {timers[0]['remaining']} seconds remaining."
            return True, "No active timers to pause."

        if any(x in cmd for x in ['resume timer', 'continue timer']):
            timers = self.core.productivity.timers.list_timers()
            for t in timers:
                if t['paused']:
                    self.core.productivity.timers.resume_timer(t['id'])
                    return True, f"▶️ Timer resumed."
            return True, "No paused timers to resume."

        if any(x in cmd for x in ['cancel timer', 'delete timer']):
            timers = self.core.productivity.timers.list_timers()
            if timers:
                self.core.productivity.timers.cancel_timer(timers[0]['id'])
                return True, "⏱️ Timer cancelled."
            return True, "No active timers to cancel."

        return False, ""

    # ── Focus Mode ───────────────────────────────────────────

    def _handle_focus(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['enable focus', 'start focus', 'focus mode on', 'do not disturb']):
            match = re.search(r'(\d+)\s*(?:minutes?|mins?|hours?|hrs?)', cmd)
            duration = 60
            if match:
                amount = int(match.group(1))
                if 'hour' in cmd or 'hr' in cmd:
                    duration = amount * 60
                else:
                    duration = amount
            result = self.core.productivity.focus.start(duration)
            return True, result

        if any(x in cmd for x in ['disable focus', 'stop focus', 'focus mode off', 'end focus']):
            result = self.core.productivity.focus.stop()
            return True, result

        if any(x in cmd for x in ['focus status', 'am i focused', 'focus mode status']):
            status = self.core.productivity.focus.get_status()
            if status['active']:
                return True, f"🎯 Focus mode active. {status['remaining_minutes']} minutes remaining."
            return True, "🎯 Focus mode is not active."

        return False, ""

    # ── Speed Test ───────────────────────────────────────────

    def _handle_speed_test(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['speed test', 'test internet', 'internet speed', 'check connection speed']):
            return True, "⏳ Running internet speed test... (this may take a moment)"

        return False, ""

    # ── Backup ───────────────────────────────────────────────

    def _handle_backup(self, cmd: str) -> Tuple[bool, str]:
        if any(x in cmd for x in ['backup files', 'backup folder', 'create backup', 'backup my']):
            match = re.search(r'backup\s+(?:my\s+)?(.+)', cmd)
            if match:
                target = match.group(1).strip()
                if target in ['documents', 'docs']:
                    from pathlib import Path
                    result = self.core.productivity.backup.backup_folder(str(Path.home() / "Documents"))
                elif target in ['desktop']:
                    from pathlib import Path
                    result = self.core.productivity.backup.backup_folder(str(Path.home() / "Desktop"))
                else:
                    result = self.core.productivity.backup.backup_folder(target)
                if result.get('status') == 'success':
                    return True, f"✅ Backup created: {result.get('backup')}"
                return True, f"❌ Backup failed: {result.get('message', 'Unknown error')}"
            return True, "What would you like to backup? (e.g., 'backup my documents')"

        if any(x in cmd for x in ['list backups', 'show backups', 'my backups']):
            backups = self.core.productivity.backup.list_backups()
            if backups:
                backup_list = '\n'.join([f"  • {b['name']} ({b['created'][:10]})" for b in backups[:10]])
                return True, f"📦 Your backups:\n{backup_list}"
            return True, "You don't have any backups yet."

        return False, ""

    # ── Gmail ────────────────────────────────────────────────

    def _handle_gmail(self, cmd: str) -> Tuple[bool, str]:
        gmail = getattr(self.core, 'gmail', None)
        if not gmail or not gmail.is_authenticated():
            return False, ""

        if any(x in cmd for x in ['check email', 'check inbox', 'check mail', 'new emails', 'unread emails']):
            if 'unread' in cmd:
                result = gmail.get_unread_count()
                if result.get('success'):
                    return True, f"📧 You have {result['unread_count']} unread emails"
            else:
                result = gmail.get_inbox(5, unread_only=True)
                if result.get('success'):
                    if result['messages']:
                        email_list = '\n'.join([f"  • {m['sender'][:30]}: {m['subject'][:40]}" for m in result['messages'][:5]])
                        return True, f"📧 Recent emails:\n{email_list}"
                    return True, "No unread emails"
            return True, "Couldn't check emails"

        if any(x in cmd for x in ['send email', 'compose email', 'email to']):
            match = re.search(r'(?:send email|email)\s+to\s+(\S+)\s+(?:subject|about)\s+(.+)', cmd)
            if match:
                to = match.group(1)
                subject = match.group(2)
                result = gmail.create_draft(to, subject, "")
                return True, f"✅ Draft created for {to}" if result.get('success') else "Couldn't create draft"
            return True, "Say 'send email to [address] subject [topic]'"

        if 'search email' in cmd or 'find email' in cmd:
            match = re.search(r'(?:search|find)\s+emails?\s+(?:for|from|about)?\s*(.+)', cmd)
            if match:
                query = match.group(1).strip()
                result = gmail.search_emails(query, 5)
                if result.get('success') and result['messages']:
                    email_list = '\n'.join([f"  • {m['subject'][:50]}" for m in result['messages']])
                    return True, f"📧 Found {result['count']} emails:\n{email_list}"
                return True, f"No emails found for '{query}'"

        return False, ""

    # ── Calendar ─────────────────────────────────────────────

    def _handle_calendar(self, cmd: str) -> Tuple[bool, str]:
        calendar = getattr(self.core, 'calendar', None)
        if not calendar or not calendar.is_authenticated():
            return False, ""

        if any(x in cmd for x in ["today's events", "today's schedule", "what's on today", "events today"]):
            result = calendar.get_today_events()
            if result.get('success'):
                if result['events']:
                    event_list = '\n'.join([f"  • {e['summary']} at {e['start'][:16]}" for e in result['events']])
                    return True, f"📅 Today's events:\n{event_list}"
                return True, "No events scheduled for today"
            return True, "Couldn't get today's events"

        if any(x in cmd for x in ["tomorrow's events", "tomorrow's schedule", "what's on tomorrow"]):
            result = calendar.get_tomorrow_events()
            if result.get('success'):
                if result['events']:
                    event_list = '\n'.join([f"  • {e['summary']}" for e in result['events']])
                    return True, f"📅 Tomorrow's events:\n{event_list}"
                return True, "No events scheduled for tomorrow"

        if any(x in cmd for x in ["this week's events", "week's schedule", "events this week"]):
            result = calendar.get_week_events()
            if result.get('success'):
                if result['events']:
                    event_list = '\n'.join([f"  • {e['summary']}: {e['start'][:10]}" for e in result['events'][:10]])
                    return True, f"📅 This week ({result['count']} events):\n{event_list}"
                return True, "No events this week"

        if any(x in cmd for x in ['upcoming events', 'next events', 'schedule', 'calendar']):
            result = calendar.get_upcoming_events(5)
            if result.get('success'):
                if result['events']:
                    event_list = '\n'.join([f"  • {e['summary']}: {e['start'][:16]}" for e in result['events']])
                    return True, f"📅 Upcoming events:\n{event_list}"
                return True, "No upcoming events"

        if any(x in cmd for x in ['add event', 'create event', 'schedule event', 'new event']):
            match = re.search(r'(?:add|create|schedule|new)\s+event\s+(.+)', cmd)
            if match:
                event_text = match.group(1).strip()
                result = calendar.quick_add(event_text)
                if result.get('success'):
                    return True, f"✅ Event created: {result.get('summary', event_text)}"
                return True, f"Couldn't create event: {result.get('error', '')}"
            return True, "Say 'add event [description]' (e.g., 'add event meeting tomorrow at 3pm')"

        if any(x in cmd for x in ['schedule meeting', 'create meeting', 'set up meeting']):
            match = re.search(r'(?:schedule|create|set up)\s+meeting\s+(?:with\s+)?(.+)', cmd)
            if match:
                meeting_text = match.group(1).strip()
                result = calendar.quick_add(f"Meeting {meeting_text}")
                return True, f"✅ Meeting scheduled" if result.get('success') else "Couldn't schedule meeting"

        return False, ""

    # ── Spotify ──────────────────────────────────────────────

    def _handle_spotify(self, cmd: str) -> Tuple[bool, str]:
        spotify = getattr(self.core, 'spotify', None)
        if not spotify:
            return False, ""

        if not any(x in cmd for x in ['spotify', 'play music', 'pause music',
            'next song', 'previous song', 'now playing', 'what is playing',
            'what song', 'skip song', 'music volume', 'shuffle', 'add to queue',
            'my playlists', 'play playlist', 'play album', 'play artist']):
            return False, ""

        if any(x in cmd for x in ['pause music', 'pause spotify', 'stop music']):
            result = spotify.pause()
            return True, result.get('message', 'Paused') if isinstance(result, dict) else str(result)

        if any(x in cmd for x in ['next song', 'skip song', 'next track']):
            result = spotify.next_track()
            return True, result.get('message', 'Skipped') if isinstance(result, dict) else str(result)

        if any(x in cmd for x in ['previous song', 'last song', 'previous track']):
            result = spotify.previous_track()
            return True, result.get('message', 'Previous') if isinstance(result, dict) else str(result)

        if any(x in cmd for x in ['now playing', 'what is playing', 'what song', 'current song']):
            return True, spotify.what_is_playing()

        if 'shuffle' in cmd:
            on = 'off' not in cmd
            result = spotify.shuffle(on)
            return True, f"Shuffle {'on' if on else 'off'}"

        if 'my playlists' in cmd or 'list playlists' in cmd:
            return True, spotify.list_playlists_spoken()

        if 'music volume' in cmd or 'spotify volume' in cmd:
            nums = [int(x) for x in cmd.split() if x.isdigit()]
            if nums:
                spotify.set_volume(nums[0])
                return True, f"Spotify volume set to {nums[0]}%"

        # Generic play command
        play_query = cmd
        for prefix in ['play music', 'play spotify', 'spotify play', 'play']:
            if play_query.startswith(prefix):
                play_query = play_query[len(prefix):].strip()
                break
        if play_query:
            return True, spotify.play_by_name(play_query)
        else:
            result = spotify.play()
            return True, result.get('message', 'Resumed playback') if isinstance(result, dict) else str(result)

    # ── Smart Home ───────────────────────────────────────────

    def _handle_smart_home(self, cmd: str) -> Tuple[bool, str]:
        smart_home = getattr(self.core, 'smart_home', None)
        if not smart_home:
            return False, ""

        if not any(x in cmd for x in ['turn on light', 'turn off light',
            'lights on', 'lights off', 'dim lights', 'set brightness to',
            'turn on the', 'turn off the', 'set temperature to', 'thermostat',
            'smart home', 'home devices', 'device status', 'smart light',
            'living room light', 'bedroom light', 'kitchen light',
            'activate scene', 'set scene']):
            return False, ""

        if any(x in cmd for x in ['home devices', 'device status', 'smart home status', 'list devices']):
            return True, smart_home.summary()

        if 'activate scene' in cmd or 'set scene' in cmd:
            scene_name = cmd.split('scene', 1)[-1].strip()
            if scene_name:
                result = smart_home.activate_scene(scene_name)
                return True, result if isinstance(result, str) else f"Scene '{scene_name}' activated"

        if 'discover' in cmd:
            devices = smart_home.discover_devices()
            return True, f"Discovered {len(devices)} smart home devices"

        result = smart_home.process_command(cmd)
        if result:
            return True, result if isinstance(result, str) else str(result)

        return False, ""

    # ── Focus Modes (advanced) ────────────────────────────────

    def _handle_focus_modes(self, cmd: str) -> Tuple[bool, str]:
        if not any(x in cmd for x in ['focus mode', 'enter focus', 'start focus',
                                        'coding mode', 'deep work', 'writing mode',
                                        'study mode', 'exit focus', 'stop focus',
                                        'end focus', 'focus status']):
            return False, ""

        try:
            from modules.focus_modes import FocusModeManager
            fm = FocusModeManager()
        except (ImportError, Exception):
            return False, ""

        if any(x in cmd for x in ['exit focus', 'stop focus', 'end focus', 'leave focus']):
            try:
                result = fm.deactivate() if hasattr(fm, 'deactivate') else fm.stop()
                return True, result if isinstance(result, str) else "Focus mode ended."
            except Exception as e:
                return True, f"Error ending focus mode: {e}"

        if 'focus status' in cmd:
            try:
                status = fm.status() if hasattr(fm, 'status') else fm.get_status()
                return True, status if isinstance(status, str) else str(status)
            except Exception as e:
                return True, f"Focus status error: {e}"

        # Detect mode name
        mode = "default"
        for m in ['coding', 'writing', 'study', 'deep work', 'reading']:
            if m in cmd:
                mode = m
                break

        try:
            result = fm.activate(mode) if hasattr(fm, 'activate') else fm.start(mode)
            return True, result if isinstance(result, str) else f"Focus mode '{mode}' activated."
        except Exception as e:
            return True, f"Focus mode error: {e}"
