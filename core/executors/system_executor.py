"""
LADA System Executor — Handles volume, brightness, WiFi, Bluetooth, power,
display, clipboard, processes, and other system-level commands.

Extracted from JarvisCommandProcessor.process() system control blocks.
"""

import os
import re
import subprocess
import logging
from typing import Tuple

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class SystemExecutor(BaseExecutor):
    """Handles system control commands (volume, brightness, WiFi, power, etc.)."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        cmd = cmd.lower().strip()

        # Power commands (shutdown/restart/lock/sleep) — no self.system needed
        handled, resp = self._handle_power(cmd)
        if handled:
            return True, resp

        # Battery/CPU/memory/disk via psutil
        handled, resp = self._handle_psutil_status(cmd)
        if handled:
            return True, resp

        # Everything else requires self.core.system (SystemControl module)
        system = self.core.system
        if not system:
            return False, ""

        # Dispatch to subsection handlers
        for handler in [
            self._handle_volume,
            self._handle_brightness,
            self._handle_wifi,
            self._handle_bluetooth,
            self._handle_airplane,
            self._handle_night_light,
            self._handle_hotspot,
            self._handle_audio_devices,
            self._handle_theme,
            self._handle_virtual_desktops,
            self._handle_touchpad,
            self._handle_display,
            self._handle_clipboard,
            self._handle_power_plan,
            self._handle_screen_timeout,
            self._handle_processes,
            self._handle_cleanup,
            self._handle_hibernate_logoff,
            self._handle_dnd,
            self._handle_screen_recording,
            self._handle_startup_apps,
            self._handle_settings_pages,
            self._handle_system_info_verbose,
        ]:
            handled, resp = handler(cmd, system)
            if handled:
                return True, resp

        return False, ""

    # ── Volume ──────────────────────────────────────────────

    def _handle_volume(self, cmd: str, system) -> Tuple[bool, str]:
        from lada_jarvis_core import LadaPersonality

        if any(x in cmd for x in ['set volume', 'volume to', 'change volume', 'make volume']):
            match = re.search(r'(\d+)', cmd)
            if match:
                level = int(match.group(1))
                result = system.set_volume(level)
                if result.get('success'):
                    return True, f"{LadaPersonality.get_acknowledgment()} Volume set to {level}%."
                return True, f"I couldn't change the volume. {result.get('error', '')}"

        if 'mute' in cmd:
            system.set_volume(0)
            return True, "Volume muted."

        if 'unmute' in cmd or 'full volume' in cmd or 'max volume' in cmd:
            system.set_volume(100)
            return True, "Volume set to maximum."

        if any(x in cmd for x in ['volume up', 'increase volume', 'louder']):
            vol = system.get_volume()
            new_vol = min(100, vol.get('volume', 50) + 10)
            system.set_volume(new_vol)
            return True, f"Volume increased to {new_vol}%."

        if any(x in cmd for x in ['volume down', 'decrease volume', 'quieter', 'lower volume']):
            vol = system.get_volume()
            new_vol = max(0, vol.get('volume', 50) - 10)
            system.set_volume(new_vol)
            return True, f"Volume decreased to {new_vol}%."

        if any(x in cmd for x in ['what is the volume', 'current volume', 'volume level']):
            vol = system.get_volume()
            return True, f"Volume is at {vol.get('volume', 'unknown')}%."

        return False, ""

    # ── Brightness ──────────────────────────────────────────

    def _handle_brightness(self, cmd: str, system) -> Tuple[bool, str]:
        from lada_jarvis_core import LadaPersonality

        if any(x in cmd for x in ['set brightness', 'brightness to', 'change brightness']):
            match = re.search(r'(\d+)', cmd)
            if match:
                level = int(match.group(1))
                result = system.set_brightness(level)
                if result.get('success'):
                    return True, f"{LadaPersonality.get_acknowledgment()} Brightness set to {level}%."
                return True, f"I couldn't change the brightness. {result.get('error', '')}"

        if any(x in cmd for x in ['brightness up', 'increase brightness', 'brighter']):
            current = system.get_brightness()
            new_level = min(100, current.get('brightness', 50) + 20)
            system.set_brightness(new_level)
            return True, f"Brightness increased to {new_level}%."

        if any(x in cmd for x in ['brightness down', 'decrease brightness', 'dimmer', 'dim screen', 'lower brightness']):
            current = system.get_brightness()
            new_level = max(0, current.get('brightness', 50) - 20)
            system.set_brightness(new_level)
            return True, f"Brightness decreased to {new_level}%."

        if any(x in cmd for x in ['what is the brightness', 'current brightness', 'brightness level']):
            result = system.get_brightness()
            return True, f"Brightness is at {result.get('brightness', 'unknown')}%."

        return False, ""

    # ── WiFi ────────────────────────────────────────────────

    def _handle_wifi(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['list wifi', 'available wifi', 'scan wifi', 'show wifi', 'wifi networks', 'what wifi']):
            result = system.list_wifi_networks()
            if result.get('success') and result.get('networks'):
                nets = result['networks'][:10]
                net_list = '\n'.join([f"  - {n.get('ssid', 'Unknown')}" for n in nets])
                return True, f"Found {result['count']} WiFi networks:\n{net_list}"
            return True, "No WiFi networks found."

        if any(x in cmd for x in ['connect wifi', 'connect to wifi', 'join wifi', 'connect to network']):
            match = re.search(r'(?:connect(?:\s+to)?|join)\s+(?:wifi|network)\s+(.+)', cmd)
            if match:
                ssid = match.group(1).strip().strip('"\'')
                result = system.connect_wifi(ssid)
                if result.get('success'):
                    return True, f"Connected to {ssid}."
                return True, f"Could not connect to {ssid}: {result.get('error', 'Unknown error')}"
            return True, "Which WiFi network? Say 'connect to wifi [network name]'."

        if any(x in cmd for x in ['disconnect wifi', 'turn off wifi', 'disable wifi', 'wifi off']):
            result = system.disconnect_wifi()
            return True, "Disconnected from WiFi." if result.get('success') else f"Could not disconnect: {result.get('error', '')}"

        if any(x in cmd for x in ['wifi status', 'am i connected', 'network status', 'connection status', 'what network', 'which wifi']):
            result = system.get_network_status()
            if result.get('success'):
                if result.get('connected'):
                    ssid = result.get('ssid', 'Unknown')
                    signal = result.get('signal', 'N/A')
                    ip = result.get('ip_address', 'N/A')
                    return True, f"Connected to '{ssid}', Signal: {signal}, IP: {ip}"
                return True, "Not connected to any WiFi network."
            return True, "Could not get network status."

        return False, ""

    # ── Bluetooth ───────────────────────────────────────────

    def _handle_bluetooth(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['turn on bluetooth', 'enable bluetooth', 'bluetooth on']):
            result = system.set_bluetooth(True)
            return True, result.get('message', 'Bluetooth enabled') if result.get('success') else f"Could not enable Bluetooth: {result.get('error', '')}"

        if any(x in cmd for x in ['turn off bluetooth', 'disable bluetooth', 'bluetooth off']):
            result = system.set_bluetooth(False)
            return True, result.get('message', 'Bluetooth disabled') if result.get('success') else f"Could not disable Bluetooth: {result.get('error', '')}"

        if any(x in cmd for x in ['bluetooth status', 'is bluetooth on', 'bluetooth state']):
            result = system.get_bluetooth_status()
            return True, result.get('message', 'Unknown') if result.get('success') else "Could not check Bluetooth status."

        if any(x in cmd for x in ['list bluetooth', 'bluetooth devices', 'paired devices', 'show bluetooth']):
            result = system.list_bluetooth_devices()
            if result.get('success') and result.get('devices'):
                dev_list = '\n'.join([f"  - {d['name']} ({d['status']})" for d in result['devices']])
                return True, f"Bluetooth devices ({result['count']}):\n{dev_list}"
            return True, "No Bluetooth devices found."

        return False, ""

    # ── Airplane Mode ───────────────────────────────────────

    def _handle_airplane(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['airplane mode on', 'enable airplane', 'turn on airplane', 'flight mode on']):
            result = system.set_airplane_mode(True)
            return True, result.get('message', 'Airplane mode on') if result.get('success') else f"Could not enable airplane mode: {result.get('error', '')}"

        if any(x in cmd for x in ['airplane mode off', 'disable airplane', 'turn off airplane', 'flight mode off']):
            result = system.set_airplane_mode(False)
            return True, result.get('message', 'Airplane mode off') if result.get('success') else f"Could not disable airplane mode: {result.get('error', '')}"

        return False, ""

    # ── Night Light / Blue Light ────────────────────────────

    def _handle_night_light(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['turn on night light', 'enable night light', 'night light on', 'enable blue light filter', 'blue light on', 'warm screen']):
            result = system.set_night_light(True)
            return True, result.get('message', 'Night light enabled')

        if any(x in cmd for x in ['turn off night light', 'disable night light', 'night light off', 'disable blue light', 'blue light off']):
            result = system.set_night_light(False)
            return True, result.get('message', 'Night light disabled')

        if any(x in cmd for x in ['night light status', 'is night light on']):
            result = system.get_night_light_status()
            return True, result.get('message', 'Unknown') if result.get('success') else "Could not check night light status."

        return False, ""

    # ── Hotspot ─────────────────────────────────────────────

    def _handle_hotspot(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['turn on hotspot', 'enable hotspot', 'hotspot on', 'start hotspot', 'mobile hotspot on']):
            result = system.set_hotspot(True)
            return True, result.get('message', 'Hotspot enabled')

        if any(x in cmd for x in ['turn off hotspot', 'disable hotspot', 'hotspot off', 'stop hotspot', 'mobile hotspot off']):
            result = system.set_hotspot(False)
            return True, result.get('message', 'Hotspot disabled')

        return False, ""

    # ── Audio Devices ───────────────────────────────────────

    def _handle_audio_devices(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['list audio devices', 'show audio devices', 'what speakers', 'audio output', 'sound devices']):
            result = system.list_audio_devices()
            if result.get('success') and result.get('devices'):
                dev_list = '\n'.join([f"  - {d.get('name', 'Unknown')}" for d in result['devices']])
                return True, f"Audio devices ({result['count']}):\n{dev_list}"
            return True, "Could not list audio devices."

        if any(x in cmd for x in ['switch audio', 'switch speaker', 'switch to speaker', 'switch to headphone', 'change audio output', 'use speaker', 'use headphone']):
            if 'speaker' in cmd:
                result = system.set_audio_device('Speaker')
            elif 'headphone' in cmd or 'headset' in cmd:
                result = system.set_audio_device('Headphone')
            else:
                match = re.search(r'(?:switch|change)\s+(?:audio|speaker|output)\s+(?:to\s+)?(.+)', cmd)
                if match:
                    result = system.set_audio_device(match.group(1).strip())
                else:
                    return True, "Which audio device? Say 'switch audio to [device name]'."
            return True, result.get('message', 'Audio switched') if result.get('success') else f"Could not switch: {result.get('error', '')}"

        return False, ""

    # ── Dark/Light Theme ────────────────────────────────────

    def _handle_theme(self, cmd: str, system) -> Tuple[bool, str]:
        from lada_jarvis_core import LadaPersonality

        if any(x in cmd for x in ['dark mode', 'enable dark mode', 'turn on dark mode', 'switch to dark', 'dark theme']):
            result = system.set_dark_mode()
            return True, f"{LadaPersonality.get_acknowledgment()} Dark mode enabled." if result.get('success') else f"Could not change theme: {result.get('error', '')}"

        if any(x in cmd for x in ['light mode', 'enable light mode', 'turn on light mode', 'switch to light', 'light theme']):
            result = system.set_light_mode()
            return True, f"{LadaPersonality.get_acknowledgment()} Light mode enabled." if result.get('success') else f"Could not change theme: {result.get('error', '')}"

        if any(x in cmd for x in ['toggle theme', 'switch theme', 'change theme']):
            result = system.toggle_theme()
            if result.get('success'):
                return True, f"Theme switched to {result.get('theme', 'unknown')} mode."
            return True, f"Could not toggle theme: {result.get('error', '')}"

        if any(x in cmd for x in ['what theme', 'current theme', 'which theme', 'theme status']):
            result = system.get_system_theme()
            if result.get('success'):
                return True, f"System theme: {result.get('theme', 'unknown')}, Apps: {result.get('apps_theme', 'unknown')}."
            return True, "Could not get theme information."

        return False, ""

    # ── Virtual Desktops ────────────────────────────────────

    def _handle_virtual_desktops(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['new desktop', 'create desktop', 'add desktop', 'new virtual desktop']):
            result = system.create_virtual_desktop()
            return True, result.get('message', 'Created new virtual desktop')

        if any(x in cmd for x in ['next desktop', 'switch desktop right', 'desktop right']):
            result = system.switch_virtual_desktop('right')
            return True, result.get('message', 'Switched to next desktop')

        if any(x in cmd for x in ['previous desktop', 'switch desktop left', 'desktop left']):
            result = system.switch_virtual_desktop('left')
            return True, result.get('message', 'Switched to previous desktop')

        if any(x in cmd for x in ['close desktop', 'close virtual desktop', 'remove desktop']):
            result = system.close_virtual_desktop()
            return True, result.get('message', 'Closed virtual desktop')

        if any(x in cmd for x in ['task view', 'show desktops', 'show all desktops', 'all desktops']):
            result = system.show_task_view()
            return True, result.get('message', 'Opened Task View')

        return False, ""

    # ── Touchpad ────────────────────────────────────────────

    def _handle_touchpad(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['enable touchpad', 'turn on touchpad', 'touchpad on']):
            result = system.set_touchpad(True)
            return True, result.get('message', 'Touchpad enabled') if result.get('success') else "Could not enable touchpad."

        if any(x in cmd for x in ['disable touchpad', 'turn off touchpad', 'touchpad off']):
            result = system.set_touchpad(False)
            return True, result.get('message', 'Touchpad disabled') if result.get('success') else "Could not disable touchpad."

        return False, ""

    # ── Display / Projection ────────────────────────────────

    def _handle_display(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['extend display', 'extend screen', 'dual monitor', 'extend monitor']):
            result = system.set_display_mode('extend')
            return True, result.get('message', 'Display extended')

        if any(x in cmd for x in ['duplicate display', 'mirror display', 'mirror screen', 'duplicate screen']):
            result = system.set_display_mode('duplicate')
            return True, result.get('message', 'Display mirrored')

        if any(x in cmd for x in ['pc screen only', 'laptop screen only', 'disconnect display', 'disconnect projector']):
            result = system.set_display_mode('pc')
            return True, result.get('message', 'PC screen only')

        if any(x in cmd for x in ['second screen only', 'projector only', 'external display only']):
            result = system.set_display_mode('second')
            return True, result.get('message', 'Second screen only')

        return False, ""

    # ── Clipboard ───────────────────────────────────────────

    def _handle_clipboard(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['clear clipboard', 'empty clipboard']):
            result = system.clear_clipboard()
            return True, result.get('message', 'Clipboard cleared')

        if any(x in cmd for x in ['clipboard history', 'show clipboard', 'open clipboard']):
            result = system.toggle_clipboard_history()
            return True, result.get('message', 'Opened clipboard history')

        if any(x in cmd for x in ['what is in clipboard', 'read clipboard', 'clipboard content']):
            result = system.get_clipboard_text()
            if result.get('success'):
                text = result.get('text', '')[:200]
                return True, f"Clipboard ({result.get('length', 0)} chars): {text}" if text else "Clipboard is empty."
            return True, "Could not read clipboard."

        return False, ""

    # ── Power Plan ──────────────────────────────────────────

    def _handle_power_plan(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['power plan', 'current power plan', 'what power plan', 'which power plan']):
            result = system.get_power_plan()
            return True, f"Current power plan: {result.get('plan', 'Unknown')}" if result.get('success') else "Could not get power plan."

        if any(x in cmd for x in ['list power plans', 'available power plans', 'show power plans']):
            result = system.list_power_plans()
            if result.get('success') and result.get('plans'):
                plan_list = '\n'.join([f"  {'*' if p['active'] else '-'} {p['name']}" for p in result['plans']])
                return True, f"Power plans:\n{plan_list}"
            return True, "Could not list power plans."

        if any(x in cmd for x in ['high performance', 'performance mode', 'gaming mode', 'max performance']):
            result = system.set_power_plan('high performance')
            return True, result.get('message', 'Switched to high performance') if result.get('success') else f"Could not switch: {result.get('error', '')}"

        if any(x in cmd for x in ['power saver', 'power saving', 'battery saver mode', 'save battery', 'eco mode']):
            result = system.set_power_plan('power saver')
            return True, result.get('message', 'Switched to power saver') if result.get('success') else f"Could not switch: {result.get('error', '')}"

        if any(x in cmd for x in ['balanced mode', 'balanced power', 'normal power']):
            result = system.set_power_plan('balanced')
            return True, result.get('message', 'Switched to balanced') if result.get('success') else f"Could not switch: {result.get('error', '')}"

        return False, ""

    # ── Screen Timeout ──────────────────────────────────────

    def _handle_screen_timeout(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['screen timeout', 'set screen timeout', 'display timeout']):
            match = re.search(r'(\d+)\s*(?:minutes?|mins?)', cmd)
            if match:
                minutes = int(match.group(1))
                result = system.set_screen_timeout(minutes)
                return True, result.get('message', f'Screen timeout set to {minutes} minutes')
            if 'never' in cmd:
                result = system.set_screen_timeout(0)
                return True, "Screen timeout disabled (never turn off)."
            return True, "How many minutes? Say 'screen timeout 10 minutes' or 'screen timeout never'."

        return False, ""

    # ── Process Management ──────────────────────────────────

    def _handle_processes(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['list processes', 'running processes', 'show processes', 'what is running', 'top processes']):
            result = system.list_processes(limit=10)
            if result.get('success') and result.get('processes'):
                proc_list = '\n'.join([f"  - {p['name']} (PID: {p['pid']}, Mem: {p['memory_mb']}%)" for p in result['processes'][:10]])
                return True, f"Top processes ({result['total']}):\n{proc_list}"
            return True, "Could not list processes."

        if any(x in cmd for x in ['kill process', 'end process', 'force close', 'terminate process']):
            match = re.search(r'(?:kill|end|terminate|force close)\s+(?:process\s+)?(.+)', cmd)
            if match:
                proc_name = match.group(1).strip()
                result = system.kill_process(proc_name)
                if result.get('success'):
                    return True, f"Killed {result.get('killed', 0)} instance(s) of {proc_name}."
                return True, f"Process '{proc_name}' not found or could not be killed."
            return True, "Which process? Say 'kill process [name]'."

        return False, ""

    # ── Cleanup / Maintenance ───────────────────────────────

    def _handle_cleanup(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['clear temp', 'clean temp', 'delete temp files', 'clear temporary', 'clean up', 'clear cache']):
            result = system.clear_temp_files()
            if result.get('success'):
                return True, f"Cleaned up! Deleted {result.get('deleted', 0)} files, freed {result.get('freed_mb', 0)} MB."
            return True, "Could not clear temp files."

        if any(x in cmd for x in ['empty recycle', 'clear recycle', 'empty trash', 'clear trash', 'empty bin']):
            result = system.empty_recycle_bin()
            return True, result.get('message', 'Recycle bin emptied') if result.get('success') else "Could not empty recycle bin."

        return False, ""

    # ── Hibernate / Logoff ──────────────────────────────────

    def _handle_hibernate_logoff(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['hibernate', 'hibernation']):
            result = system.power_action('hibernate')
            return True, "Hibernating..." if result.get('success') else f"Could not hibernate: {result.get('error', '')}"

        if any(x in cmd for x in ['log off', 'logoff', 'sign out', 'log out', 'logout']):
            return self.core.request_confirmation('log you off', 'All unsaved work will be lost.')

        return False, ""

    # ── Do Not Disturb ──────────────────────────────────────

    def _handle_dnd(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['do not disturb on', 'enable do not disturb', 'turn on dnd', 'dnd on', 'silence notifications']):
            result = system.set_do_not_disturb(True)
            return True, result.get('message', 'Do Not Disturb enabled')

        if any(x in cmd for x in ['do not disturb off', 'disable do not disturb', 'turn off dnd', 'dnd off', 'enable notifications']):
            result = system.set_do_not_disturb(False)
            return True, result.get('message', 'Do Not Disturb disabled')

        return False, ""

    # ── Screen Recording ────────────────────────────────────

    def _handle_screen_recording(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['start recording', 'record screen', 'screen record', 'start screen recording']):
            result = system.start_screen_recording()
            return True, result.get('message', 'Recording started')

        if any(x in cmd for x in ['stop recording', 'stop screen recording', 'end recording']):
            result = system.stop_screen_recording()
            return True, result.get('message', 'Recording stopped')

        return False, ""

    # ── Startup Apps ────────────────────────────────────────

    def _handle_startup_apps(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['startup apps', 'list startup', 'show startup apps', 'what runs at startup']):
            result = system.list_startup_apps()
            if result.get('success') and result.get('apps'):
                app_list = '\n'.join([f"  - {a['name']} ({a['scope']})" for a in result['apps'][:15]])
                return True, f"Startup apps ({result['count']}):\n{app_list}"
            return True, "No startup apps found or could not list them."

        if any(x in cmd for x in ['remove from startup', 'disable startup', 'remove startup']):
            match = re.search(r'(?:remove|disable)\s+(?:from\s+)?startup\s+(?:app\s+)?(.+)', cmd)
            if match:
                app_name = match.group(1).strip()
                result = system.disable_startup_app(app_name)
                return True, result.get('message', f'Removed {app_name} from startup') if result.get('success') else f"Could not remove: {result.get('error', '')}"
            return True, "Which app? Say 'remove from startup [app name]'."

        return False, ""

    # ── Settings Pages ──────────────────────────────────────

    def _handle_settings_pages(self, cmd: str, system) -> Tuple[bool, str]:
        settings_triggers = [
            'open settings', 'open wifi settings', 'open bluetooth settings', 'open display settings',
            'open sound settings', 'open storage settings', 'open battery settings',
            'open update settings', 'open privacy settings', 'open power settings',
            'open accounts settings', 'open apps settings', 'open mouse settings',
            'open keyboard settings', 'open vpn settings', 'open about',
        ]
        if any(x in cmd for x in settings_triggers):
            page_match = re.search(r'open\s+(\w+)\s+settings', cmd)
            page = page_match.group(1) if page_match else ''
            result = system.open_settings(page)
            return True, result.get('message', f'Opened {page} settings')

        return False, ""

    # ── System Info (verbose) ───────────────────────────────

    def _handle_system_info_verbose(self, cmd: str, system) -> Tuple[bool, str]:
        if any(x in cmd for x in ['system information', 'computer info', 'pc info', 'laptop info', 'about this pc', 'about my computer']):
            result = system.get_system_info()
            if result.get('success'):
                return True, (
                    f"System Information:\n"
                    f"  OS: {result.get('os', 'Unknown')} {result.get('os_version', '')}\n"
                    f"  Processor: {result.get('processor', 'Unknown')}\n"
                    f"  Architecture: {result.get('architecture', 'Unknown')}\n"
                    f"  Hostname: {result.get('hostname', 'Unknown')}\n"
                    f"  User: {result.get('username', 'Unknown')}"
                )
            return True, "Could not get system information."

        return False, ""

    # ── Battery / CPU / Memory / Disk (psutil) ──────────────

    def _handle_psutil_status(self, cmd: str) -> Tuple[bool, str]:
        try:
            import psutil
        except ImportError:
            return False, ""

        if any(x in cmd for x in ['battery', 'power status', 'battery level', 'charge']):
            try:
                battery = psutil.sensors_battery()
                if battery:
                    percent = battery.percent
                    plugged = "plugged in" if battery.power_plugged else "on battery"
                    if battery.secsleft > 0 and not battery.power_plugged:
                        mins = battery.secsleft // 60
                        time_left = f", about {mins} minutes remaining"
                    else:
                        time_left = ""
                    return True, f"Battery is at {percent}%, {plugged}{time_left}."
                return True, "I couldn't get battery information. This might be a desktop PC."
            except Exception:
                return True, "Battery information unavailable."

        if any(x in cmd for x in ['cpu usage', 'processor', 'cpu status']):
            cpu = psutil.cpu_percent(interval=1)
            return True, f"CPU usage is at {cpu}%."

        if any(x in cmd for x in ['memory usage', 'ram', 'memory status']):
            mem = psutil.virtual_memory()
            return True, f"Memory usage is at {mem.percent}%. {mem.available // (1024**3)} GB available."

        if any(x in cmd for x in ['disk space', 'storage', 'disk usage']):
            disk = psutil.disk_usage('/')
            free_gb = disk.free // (1024**3)
            return True, f"Disk usage is at {disk.percent}%. {free_gb} GB free."

        if any(x in cmd for x in ['system status', 'system info', 'pc status', 'computer status']):
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            try:
                battery = psutil.sensors_battery()
                bat_str = f", Battery: {battery.percent}%" if battery else ""
            except Exception:
                bat_str = ""
            return True, f"System status: CPU {cpu}%, Memory {mem.percent}%, Disk {disk.percent}%{bat_str}."

        return False, ""

    # ── Power Commands (shutdown/restart/lock/sleep) ────────

    def _handle_power(self, cmd: str) -> Tuple[bool, str]:
        if 'shutdown' in cmd or 'turn off computer' in cmd:
            return True, "Are you sure you want to shut down? Say 'confirm shutdown' to proceed."

        if 'confirm shutdown' in cmd:
            os.system('shutdown /s /t 60')
            return True, "Shutting down in 60 seconds. Say 'cancel shutdown' to abort."

        if 'cancel shutdown' in cmd:
            os.system('shutdown /a')
            return True, "Shutdown cancelled."

        if 'restart' in cmd or 'reboot' in cmd:
            return True, "Are you sure you want to restart? Say 'confirm restart' to proceed."

        if 'confirm restart' in cmd:
            os.system('shutdown /r /t 60')
            return True, "Restarting in 60 seconds."

        if any(x in cmd for x in ['lock screen', 'lock computer', 'lock pc']):
            subprocess.run('rundll32.exe user32.dll,LockWorkStation', shell=True)
            return True, "Locking the screen."

        if any(x in cmd for x in ['sleep', 'go to sleep', 'sleep mode']):
            subprocess.run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
            return True, "Going to sleep."

        return False, ""
