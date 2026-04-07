# system_control.py
# Complete System Control Module
# Handles volume, brightness, WiFi, Bluetooth, power, processes, etc.

import os
import subprocess
import logging
import threading
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import psutil
import json

logger = logging.getLogger(__name__)
_NOISY_OPTIONAL_LOGGERS_CONFIGURED = False
_NOISY_OPTIONAL_LOGGERS_LOCK = threading.Lock()

class PowerAction(Enum):
    """Power management actions"""
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    LOCK = "lock"
    LOGOFF = "logoff"


class SystemController:
    """Complete system control and monitoring"""
    
    def __init__(self):
        """Initialize system controller"""
        self._optional_dep_warnings: set[str] = set()
        self._configure_optional_library_loggers()
        self.current_brightness = self._get_brightness()
        self.current_volume = self._get_volume()
        self.connected_networks = []
        self.bluetooth_devices = []

    def _configure_optional_library_loggers(self):
        """Reduce non-actionable warnings from optional third-party integrations."""
        global _NOISY_OPTIONAL_LOGGERS_CONFIGURED
        if _NOISY_OPTIONAL_LOGGERS_CONFIGURED:
            return

        with _NOISY_OPTIONAL_LOGGERS_LOCK:
            if _NOISY_OPTIONAL_LOGGERS_CONFIGURED:
                return
            logging.getLogger("screen_brightness_control.windows").setLevel(logging.ERROR)
            _NOISY_OPTIONAL_LOGGERS_CONFIGURED = True

    def _log_operation_error(self, operation: str, error: Exception, optional_modules: Tuple[str, ...] = ()):
        """Log operation failures with lower severity for missing optional dependencies."""
        if isinstance(error, ModuleNotFoundError) and optional_modules:
            missing_name = (getattr(error, "name", "") or "").strip()
            for module_name in optional_modules:
                if missing_name == module_name or missing_name.startswith(f"{module_name}."):
                    key = f"{operation}:{module_name}"
                    if key not in self._optional_dep_warnings:
                        self._optional_dep_warnings.add(key)
                        logger.warning(
                            f"{operation.capitalize()} unavailable: optional dependency '{module_name}' is not installed"
                        )
                    else:
                        logger.debug(f"{operation.capitalize()} still unavailable: missing '{module_name}'")
                    return

        logger.error(f"Error {operation}: {error}")
    
    # ============================================================
    # VOLUME & AUDIO CONTROL
    # ============================================================
    
    def set_volume(self, level: int) -> Dict[str, Any]:
        """
        Set system volume (0-100%)
        
        Args:
            level: Volume level (0-100)
        
        Returns:
            {'success': True/False, 'volume': 50, 'message': '...'}
        """
        try:
            # Clamp level between 0-100
            level = max(0, min(100, level))

            # Windows volume control via pycaw
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            # Get default audio device and activate volume interface
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, 'Activate'):
                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
            elif hasattr(speakers, 'EndpointVolume'):
                volume = speakers.EndpointVolume
            else:
                raise RuntimeError("No compatible pycaw speaker interface found")

            # Set volume (convert 0-100 to 0.0-1.0)
            volume_level = level / 100.0
            volume.SetMasterVolumeLevelScalar(volume_level, None)

            self.current_volume = level
            logger.info(f"Volume set to {level}%")
            
            return {
                'success': True,
                'volume': level,
                'message': f'Volume set to {level}%'
            }
        
        except Exception as e:
            self._log_operation_error("setting volume", e, optional_modules=("pycaw",))
            # Fallback: use Windows command
            try:
                os.system(f'nircmd.exe setvolume 0 {level * 655}')
                return {'success': True, 'volume': level}
            except:
                return {
                    'success': False,
                    'error': str(e),
                    'message': 'Could not set volume. Install pycaw: pip install pycaw'
                }
    
    def get_volume(self) -> Dict[str, Any]:
        """Get current system volume"""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, 'Activate'):
                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
            elif hasattr(speakers, 'EndpointVolume'):
                volume = speakers.EndpointVolume
            else:
                raise RuntimeError("No compatible pycaw speaker interface found")

            level = int(volume.GetMasterVolumeLevelScalar() * 100)
            self.current_volume = level

            return {
                'success': True,
                'volume': level,
                'muted': volume.GetMute()
            }
        
        except Exception as e:
            self._log_operation_error("getting volume", e, optional_modules=("pycaw",))
            return {'success': False, 'error': str(e)}
    
    def _get_volume(self) -> int:
        """Get volume silently"""
        try:
            result = self.get_volume()
            return result.get('volume', 50)
        except:
            return 50
    
    def mute(self) -> Dict[str, Any]:
        """Mute system"""
        try:
            from pycaw.pycaw import AudioUtilities
            
            speakers = AudioUtilities.GetSpeakers()
            volume = speakers.EndpointVolume
            volume.SetMute(1, None)
            
            logger.info("System muted")
            return {'success': True, 'message': 'System muted'}
        
        except Exception as e:
            self._log_operation_error("muting", e, optional_modules=("pycaw",))
            return {'success': False, 'error': str(e)}
    
    def unmute(self) -> Dict[str, Any]:
        """Unmute system"""
        try:
            from pycaw.pycaw import AudioUtilities
            
            speakers = AudioUtilities.GetSpeakers()
            volume = speakers.EndpointVolume
            volume.SetMute(0, None)
            
            logger.info("System unmuted")
            return {'success': True, 'message': 'System unmuted'}
        
        except Exception as e:
            self._log_operation_error("unmuting", e, optional_modules=("pycaw",))
            return {'success': False, 'error': str(e)}
    
    # ============================================================
    # BRIGHTNESS CONTROL
    # ============================================================
    
    def set_brightness(self, level: int) -> Dict[str, Any]:
        """
        Set screen brightness (0-100%)
        
        Args:
            level: Brightness level (0-100)
        
        Returns:
            {'success': True/False, 'brightness': 75}
        """
        try:
            import screen_brightness_control as sbc
            
            # Clamp level
            level = max(0, min(100, level))
            
            # Set brightness
            sbc.set_brightness(level)
            
            self.current_brightness = level
            logger.info(f"Brightness set to {level}%")
            
            return {
                'success': True,
                'brightness': level,
                'message': f'Brightness set to {level}%'
            }
        
        except Exception as e:
            self._log_operation_error("setting brightness", e, optional_modules=("screen_brightness_control",))
            return {
                'success': False,
                'error': str(e),
                'message': 'Could not set brightness. Install: pip install screen-brightness-control'
            }
    
    def get_brightness(self) -> Dict[str, Any]:
        """Get current screen brightness"""
        try:
            import screen_brightness_control as sbc
            level = int(sbc.get_brightness()[0])
            self.current_brightness = level
            
            return {
                'success': True,
                'brightness': level
            }
        
        except Exception as e:
            self._log_operation_error("getting brightness", e, optional_modules=("screen_brightness_control",))
            return {'success': False, 'error': str(e)}
    
    def _get_brightness(self) -> int:
        """Get brightness silently"""
        try:
            result = self.get_brightness()
            return result.get('brightness', 75)
        except:
            return 75
    
    # ============================================================
    # WIFI MANAGEMENT
    # ============================================================

    def _list_wifi_networks_netsh(self) -> Dict[str, Any]:
        """Fallback WiFi scan using Windows netsh (no extra deps)."""
        try:
            proc = subprocess.run(
                ['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            out = (proc.stdout or "").splitlines()
            networks: List[Dict[str, Any]] = []
            current_ssid: str | None = None
            for line in out:
                s = line.strip()
                if s.lower().startswith('ssid') and ':' in s:
                    # e.g. SSID 1 : MyWifi
                    current_ssid = s.split(':', 1)[1].strip()
                    if current_ssid:
                        networks.append({'ssid': current_ssid})
            # De-dupe while preserving order
            seen = set()
            unique = []
            for n in networks:
                ssid = n.get('ssid')
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                unique.append(n)
            return {'success': True, 'networks': unique, 'count': len(unique), 'source': 'netsh'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'message': 'WiFi scan failed (netsh).'}
    
    def list_wifi_networks(self) -> Dict[str, Any]:
        """List available WiFi networks"""
        try:
            try:
                import pywifi  # type: ignore
                from pywifi import const  # type: ignore
            except Exception:
                # Fallback to netsh scan (works on Windows without pywifi)
                return self._list_wifi_networks_netsh()
            
            wifi = pywifi.PyWiFi()
            iface = wifi.interfaces()[0]
            
            # Scan for networks
            iface.scan()
            
            import time
            time.sleep(2)  # Wait for scan to complete
            
            results = iface.scan_results()
            networks = []
            
            for network in results:
                networks.append({
                    'ssid': network.ssid,
                    'signal': network.signal,
                    'security': network.security,
                    'frequency': network.freq
                })
            
            logger.info(f"Found {len(networks)} WiFi networks")
            
            return {
                'success': True,
                'networks': networks,
                'count': len(networks)
            }
        
        except Exception as e:
            logger.error(f"Error listing WiFi networks: {e}")
            return {'success': False, 'error': str(e)}
    
    def connect_wifi(self, ssid: str, password: str = None) -> Dict[str, Any]:
        """
        Connect to WiFi network
        
        Args:
            ssid: Network name
            password: Network password (if needed)
        
        Returns:
            {'success': True/False, 'message': '...'}
        """
        try:
            try:
                import pywifi  # type: ignore
                from pywifi import const  # type: ignore
            except Exception:
                # netsh connect requires an existing profile; don't guess.
                return {
                    'success': False,
                    'error': 'pywifi not installed',
                    'message': "WiFi connect requires 'pywifi'. Install with: pip install pywifi",
                }
            
            wifi = pywifi.PyWiFi()
            iface = wifi.interfaces()[0]
            
            # Disconnect first
            iface.disconnect()
            
            import time
            time.sleep(1)
            
            # Create profile
            profile = pywifi.Profile()
            profile.ssid = ssid
            
            if password:
                profile.auth = const.AUTH_ALG_OPEN
                profile.cipher = const.CIPHER_TYPE_CCMP
                profile.key = password
            else:
                profile.auth = const.AUTH_ALG_OPEN
            
            # Connect
            iface.add_network_profile(profile)
            iface.connect(profile)
            
            time.sleep(3)
            
            if iface.status() == const.IFACE_CONNECTED:
                logger.info(f"Connected to {ssid}")
                return {
                    'success': True,
                    'message': f'Connected to {ssid}',
                    'network': ssid
                }
            else:
                return {
                    'success': False,
                    'error': 'Connection failed'
                }
        
        except Exception as e:
            logger.error(f"Error connecting to WiFi: {e}")
            return {'success': False, 'error': str(e)}
    
    def disconnect_wifi(self) -> Dict[str, Any]:
        """Disconnect from WiFi"""
        try:
            try:
                import pywifi  # type: ignore
                wifi = pywifi.PyWiFi()
                iface = wifi.interfaces()[0]
                iface.disconnect()
                logger.info("Disconnected from WiFi")
                return {'success': True, 'message': 'Disconnected from WiFi'}
            except Exception:
                # Fallback to netsh
                subprocess.run(['netsh', 'wlan', 'disconnect'], capture_output=True, text=True, timeout=10)
                logger.info("Disconnected from WiFi (netsh)")
                return {'success': True, 'message': 'Disconnected from WiFi'}
        
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============================================================
    # POWER MANAGEMENT
    # ============================================================
    
    def power_action(self, 
                    action: str, 
                    delay_seconds: int = 0) -> Dict[str, Any]:
        """
        Perform power action (sleep, shutdown, restart, etc.)
        
        Args:
            action: 'sleep', 'hibernate', 'shutdown', 'restart', 'lock', 'logoff'
            delay_seconds: Delay before action (0 for immediate)
        
        Returns:
            {'success': True/False, 'action': 'sleep', 'delay': 0}
        """
        try:
            action = action.lower()
            
            if action == 'sleep':
                if delay_seconds > 0:
                    os.system(f'timeout /t {delay_seconds} && rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
                else:
                    os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
                logger.info(f"Sleep scheduled for {delay_seconds}s")
            
            elif action == 'hibernate':
                if delay_seconds > 0:
                    os.system(f'timeout /t {delay_seconds} && rundll32.exe powrprof.dll,SetSuspendState 1,1,0')
                else:
                    os.system('rundll32.exe powrprof.dll,SetSuspendState 1,1,0')
                logger.info(f"Hibernation scheduled for {delay_seconds}s")
            
            elif action == 'shutdown':
                if delay_seconds > 0:
                    os.system(f'shutdown /s /t {delay_seconds}')
                else:
                    os.system('shutdown /s /t 1')
                logger.info(f"Shutdown scheduled for {delay_seconds}s")
            
            elif action == 'restart':
                if delay_seconds > 0:
                    os.system(f'shutdown /r /t {delay_seconds}')
                else:
                    os.system('shutdown /r /t 1')
                logger.info(f"Restart scheduled for {delay_seconds}s")
            
            elif action == 'lock':
                os.system('rundll32.exe user32.dll,LockWorkStation')
                logger.info("System locked")
            
            elif action == 'logoff':
                os.system('shutdown /l /t 1')
                logger.info("Logging off")
            
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
            
            return {
                'success': True,
                'action': action,
                'delay': delay_seconds,
                'message': f'{action.capitalize()} scheduled' if delay_seconds > 0 else f'{action.capitalize()} initiated'
            }
        
        except Exception as e:
            logger.error(f"Error performing power action: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============================================================
    # SYSTEM INFORMATION & MONITORING
    # ============================================================
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information"""
        try:
            import platform
            
            return {
                'success': True,
                'os': platform.system(),
                'os_version': platform.release(),
                'processor': platform.processor(),
                'architecture': platform.architecture()[0],
                'hostname': os.getenv('COMPUTERNAME'),
                'username': os.getenv('USERNAME')
            }
        
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_disk_space(self, drive: str = 'C:') -> Dict[str, Any]:
        """Get disk space information"""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage(drive)
            
            return {
                'success': True,
                'drive': drive,
                'total_gb': round(total / (1024**3), 2),
                'used_gb': round(used / (1024**3), 2),
                'free_gb': round(free / (1024**3), 2),
                'used_percent': round((used / total) * 100, 2),
                'free_percent': round((free / total) * 100, 2)
            }
        
        except Exception as e:
            logger.error(f"Error getting disk space: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get RAM and memory usage"""
        try:
            memory = psutil.virtual_memory()
            
            return {
                'success': True,
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'used_percent': memory.percent,
                'available_percent': 100 - memory.percent
            }
        
        except Exception as e:
            logger.error(f"Error getting memory: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            return {
                'success': True,
                'cpu_percent': cpu_percent,
                'core_count': cpu_count,
                'status': 'high' if cpu_percent > 80 else 'normal' if cpu_percent > 50 else 'low'
            }
        
        except Exception as e:
            logger.error(f"Error getting CPU: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get complete system status"""
        try:
            return {
                'success': True,
                'cpu': self.get_cpu_usage(),
                'memory': self.get_memory_usage(),
                'disk': self.get_disk_space(),
                'volume': self._get_volume(),
                'brightness': self._get_brightness(),
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============================================================
    # PROCESS MANAGEMENT
    # ============================================================
    
    def list_processes(self, filter_name: str = None, limit: int = 20) -> Dict[str, Any]:
        """
        List running processes
        
        Args:
            filter_name: Filter by process name
            limit: Limit number of results
        
        Returns:
            {'processes': [...], 'total': 5}
        """
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    if filter_name and filter_name.lower() not in proc.info['name'].lower():
                        continue
                    
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'memory_mb': round(proc.info['memory_percent'] or 0, 2)
                    })
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort by memory usage
            processes = sorted(processes, key=lambda x: x['memory_mb'], reverse=True)[:limit]
            
            return {
                'success': True,
                'processes': processes,
                'total': len(processes)
            }
        
        except Exception as e:
            logger.error(f"Error listing processes: {e}")
            return {'success': False, 'error': str(e)}
    
    def kill_process(self, app_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Kill a process by name
        
        Args:
            app_name: Application name (e.g., 'python.exe')
            force: Force kill (SIGKILL)
        
        Returns:
            {'success': True/False, 'killed': 2}
        """
        try:
            killed = 0
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if app_name.lower() in proc.info['name'].lower():
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        killed += 1
                        logger.info(f"Killed process: {proc.info['name']}")
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if killed == 0:
                return {'success': False, 'error': f'Process not found: {app_name}'}
            
            return {
                'success': True,
                'app': app_name,
                'killed': killed,
                'message': f'Killed {killed} {app_name} process(es)'
            }
        
        except Exception as e:
            logger.error(f"Error killing process: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============================================================
    # CLEANUP & MAINTENANCE
    # ============================================================
    
    def clear_temp_files(self) -> Dict[str, Any]:
        """Clear Windows temporary files"""
        try:
            import shutil
            
            temp_paths = [
                os.path.expandvars(r'%TEMP%'),
                os.path.expandvars(r'%TMP%'),
                os.path.expandvars(r'%WINDIR%\Temp'),
                os.path.expandvars(r'%USERPROFILE%\AppData\Local\Temp'),
            ]
            
            deleted_count = 0
            freed_space = 0
            
            for temp_path in temp_paths:
                if not os.path.exists(temp_path):
                    continue
                
                try:
                    for item in os.listdir(temp_path):
                        item_path = os.path.join(temp_path, item)
                        try:
                            if os.path.isfile(item_path):
                                freed_space += os.path.getsize(item_path)
                                os.remove(item_path)
                                deleted_count += 1
                            elif os.path.isdir(item_path):
                                freed_space += sum(os.path.getsize(os.path.join(dirpath, filename))
                                                 for dirpath, dirnames, filenames in os.walk(item_path)
                                                 for filename in filenames)
                                shutil.rmtree(item_path)
                                deleted_count += 1
                        except:
                            pass
                except:
                    pass
            
            freed_mb = round(freed_space / (1024**2), 2)
            logger.info(f"Cleared {deleted_count} temp files, freed {freed_mb} MB")
            
            return {
                'success': True,
                'deleted': deleted_count,
                'freed_mb': freed_mb,
                'message': f'Deleted {deleted_count} temp files, freed {freed_mb} MB'
            }
        
        except Exception as e:
            logger.error(f"Error clearing temp: {e}")
            return {'success': False, 'error': str(e)}
    
    def empty_recycle_bin(self) -> Dict[str, Any]:
        """Empty Windows Recycle Bin"""
        try:
            os.system('cmd /c "echo Y | powershell Clear-RecycleBin -Force"')
            logger.info("Recycle Bin emptied")
            return {
                'success': True,
                'message': 'Recycle Bin emptied'
            }
        
        except Exception as e:
            logger.error(f"Error emptying Recycle Bin: {e}")
            return {'success': False, 'error': str(e)}

    # ============================================================
    # THEME CONTROL (Dark/Light Mode)
    # ============================================================
    
    def get_system_theme(self) -> Dict[str, Any]:
        """
        Get current Windows system theme (dark or light).
        
        Returns:
            {'success': True, 'theme': 'dark'/'light', 'apps_theme': 'dark'/'light'}
        """
        try:
            import winreg
            
            # Check system theme (taskbar, start menu)
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
                
                # SystemUsesLightTheme: 0 = dark, 1 = light
                system_light, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
                system_theme = "light" if system_light == 1 else "dark"
                
                # AppsUseLightTheme: 0 = dark, 1 = light
                apps_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                apps_theme = "light" if apps_light == 1 else "dark"
                
                winreg.CloseKey(key)
                
                return {
                    'success': True,
                    'theme': system_theme,
                    'apps_theme': apps_theme,
                    'message': f'System: {system_theme}, Apps: {apps_theme}'
                }
                
            except WindowsError:
                return {
                    'success': False,
                    'error': 'Could not read theme settings from registry'
                }
                
        except Exception as e:
            logger.error(f"Error getting system theme: {e}")
            return {'success': False, 'error': str(e)}
    
    def set_system_theme(self, theme: str, apply_to_apps: bool = True) -> Dict[str, Any]:
        """
        Set Windows system theme (dark or light).
        
        Args:
            theme: 'dark' or 'light'
            apply_to_apps: Also apply to Windows apps (default True)
        
        Returns:
            {'success': True/False, 'theme': 'dark', 'message': '...'}
        """
        try:
            import winreg
            
            theme = theme.lower().strip()
            if theme not in ('dark', 'light'):
                return {
                    'success': False,
                    'error': f"Invalid theme: {theme}. Use 'dark' or 'light'"
                }
            
            # 0 = dark, 1 = light
            value = 1 if theme == 'light' else 0
            
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, 
                    key_path, 
                    0, 
                    winreg.KEY_SET_VALUE
                )
                
                # Set system theme (taskbar, start menu)
                winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
                
                # Optionally set apps theme
                if apply_to_apps:
                    winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
                
                winreg.CloseKey(key)
                
                logger.info(f"System theme set to {theme}")
                
                return {
                    'success': True,
                    'theme': theme,
                    'apps_updated': apply_to_apps,
                    'message': f'Theme changed to {theme} mode'
                }
                
            except WindowsError as e:
                return {
                    'success': False,
                    'error': f'Could not set theme: {e}. Try running as Administrator.'
                }
                
        except Exception as e:
            logger.error(f"Error setting system theme: {e}")
            return {'success': False, 'error': str(e)}
    
    def toggle_theme(self) -> Dict[str, Any]:
        """
        Toggle between dark and light theme.
        
        Returns:
            {'success': True, 'theme': 'dark'/'light', 'message': '...'}
        """
        current = self.get_system_theme()
        if not current.get('success'):
            return current
        
        current_theme = current.get('theme', 'dark')
        new_theme = 'light' if current_theme == 'dark' else 'dark'
        
        return self.set_system_theme(new_theme)
    
    def set_dark_mode(self) -> Dict[str, Any]:
        """Shortcut to enable dark mode"""
        return self.set_system_theme('dark')
    
    def set_light_mode(self) -> Dict[str, Any]:
        """Shortcut to enable light mode"""
        return self.set_system_theme('light')


    # ============================================================
    # KEYBOARD INPUT
    # ============================================================
    
    def type_text(self, text: str, delay: float = 0.02) -> Dict[str, Any]:
        """
        Type text using keyboard simulation
        
        Args:
            text: Text to type
            delay: Delay between keystrokes (seconds)
        
        Returns:
            {'success': True/False, 'text': '...', 'message': '...'}
        """
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=delay)
            return {
                'success': True,
                'text': text,
                'message': f'Typed: {text[:50]}...' if len(text) > 50 else f'Typed: {text}'
            }
        except ImportError:
            # Fallback using Windows SendKeys if pyautogui not available
            try:
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys(text)
                return {
                    'success': True,
                    'text': text,
                    'message': f'Typed: {text[:50]}...' if len(text) > 50 else f'Typed: {text}'
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'message': 'Could not type text. Install pyautogui: pip install pyautogui'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Error typing text: {e}'
            }
    
    def press_key(self, key: str) -> Dict[str, Any]:
        """
        Press a single key or key combination

        Args:
            key: Key to press (e.g., 'enter', 'ctrl+c', 'alt+tab')

        Returns:
            {'success': True/False, 'key': '...', 'message': '...'}
        """
        try:
            import pyautogui

            # Handle key combinations
            if '+' in key:
                keys = key.lower().split('+')
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key.lower())

            return {
                'success': True,
                'key': key,
                'message': f'Pressed: {key}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Error pressing key: {e}'
            }

    # ============================================================
    # BLUETOOTH MANAGEMENT
    # ============================================================

    def get_bluetooth_status(self) -> Dict[str, Any]:
        """Get Bluetooth on/off status via Windows registry/PowerShell."""
        try:
            proc = subprocess.run(
                ['powershell', '-Command',
                 'Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -eq "OK"} | Select-Object -First 1 Status'],
                capture_output=True, text=True, timeout=10,
            )
            has_bt = 'OK' in (proc.stdout or '')
            return {'success': True, 'enabled': has_bt, 'message': f"Bluetooth is {'on' if has_bt else 'off'}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_bluetooth(self, enable: bool) -> Dict[str, Any]:
        """Enable or disable Bluetooth adapter via PowerShell."""
        try:
            action = 'Enable' if enable else 'Disable'
            proc = subprocess.run(
                ['powershell', '-Command',
                 f'Get-PnpDevice -Class Bluetooth | Where-Object {{$_.FriendlyName -match "Bluetooth"}} | {action}-PnpDevice -Confirm:$false'],
                capture_output=True, text=True, timeout=15,
            )
            state = 'enabled' if enable else 'disabled'
            if proc.returncode == 0:
                logger.info(f"Bluetooth {state}")
                return {'success': True, 'enabled': enable, 'message': f'Bluetooth {state}'}
            return {'success': False, 'error': proc.stderr.strip() or f'Could not {action.lower()} Bluetooth. Try running as admin.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list_bluetooth_devices(self) -> Dict[str, Any]:
        """List paired Bluetooth devices."""
        try:
            proc = subprocess.run(
                ['powershell', '-Command',
                 'Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName, Status | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10,
            )
            devices = []
            if proc.stdout.strip():
                data = json.loads(proc.stdout)
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    name = d.get('FriendlyName', '')
                    if name and 'radio' not in name.lower() and 'adapter' not in name.lower():
                        devices.append({'name': name, 'status': d.get('Status', 'Unknown')})
            return {'success': True, 'devices': devices, 'count': len(devices)}
        except Exception as e:
            return {'success': False, 'error': str(e), 'devices': []}

    # ============================================================
    # AIRPLANE MODE
    # ============================================================

    def set_airplane_mode(self, enable: bool) -> Dict[str, Any]:
        """Enable or disable airplane mode via radio management API."""
        try:
            state = 'on' if enable else 'off'
            # Use PowerShell to toggle radio states
            script = (
                '$radios = [Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType=WindowsRuntime]::GetRadiosAsync().GetAwaiter().GetResult(); '
                f'foreach($r in $radios) {{ $r.SetStateAsync([Windows.Devices.Radios.RadioState]::'
                f'{"Off" if enable else "On"}).GetAwaiter().GetResult() }}'
            )
            proc = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                logger.info(f"Airplane mode {state}")
                return {'success': True, 'airplane_mode': enable, 'message': f'Airplane mode {state}'}
            # Fallback: use keyboard shortcut (Fn key varies by laptop)
            return {'success': False, 'error': 'Could not toggle airplane mode programmatically. Use Fn+radio key or Action Center.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # NIGHT LIGHT / BLUE LIGHT FILTER
    # ============================================================

    def set_night_light(self, enable: bool) -> Dict[str, Any]:
        """Enable or disable Windows Night Light (blue light filter)."""
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                data, reg_type = winreg.QueryValueEx(key, "Data")
                data_list = list(data)
                # Byte at index 18 controls the toggle: 0x15 = off, 0x13 = on
                if len(data_list) > 18:
                    data_list[18] = 0x13 if enable else 0x15
                winreg.SetValueEx(key, "Data", 0, reg_type, bytes(data_list))
                winreg.CloseKey(key)
                state = 'enabled' if enable else 'disabled'
                logger.info(f"Night light {state}")
                return {'success': True, 'enabled': enable, 'message': f'Night light {state}'}
            except (FileNotFoundError, WindowsError):
                # Fallback: open Night Light settings
                os.system('start ms-settings:nightlight')
                return {'success': True, 'message': 'Opened Night Light settings. Please toggle manually.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_night_light_status(self) -> Dict[str, Any]:
        """Check if Night Light is currently active."""
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            data, _ = winreg.QueryValueEx(key, "Data")
            winreg.CloseKey(key)
            is_on = len(data) > 18 and data[18] == 0x13
            return {'success': True, 'enabled': is_on, 'message': f"Night light is {'on' if is_on else 'off'}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # HOTSPOT / MOBILE HOTSPOT
    # ============================================================

    def set_hotspot(self, enable: bool) -> Dict[str, Any]:
        """Enable or disable Windows Mobile Hotspot."""
        try:
            if enable:
                script = (
                    '[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking, ContentType=WindowsRuntime] | Out-Null; '
                    '$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile('
                    '[Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime]::GetInternetConnectionProfile()); '
                    '$mgr.StartTetheringAsync().GetAwaiter().GetResult()'
                )
            else:
                script = (
                    '[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking, ContentType=WindowsRuntime] | Out-Null; '
                    '$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile('
                    '[Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime]::GetInternetConnectionProfile()); '
                    '$mgr.StopTetheringAsync().GetAwaiter().GetResult()'
                )
            proc = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True, text=True, timeout=20,
            )
            state = 'enabled' if enable else 'disabled'
            if proc.returncode == 0:
                return {'success': True, 'enabled': enable, 'message': f'Mobile hotspot {state}'}
            # Fallback: open hotspot settings
            os.system('start ms-settings:network-mobilehotspot')
            return {'success': True, 'message': f'Opened hotspot settings. Please toggle manually.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # AUDIO OUTPUT DEVICE SWITCHING
    # ============================================================

    def list_audio_devices(self) -> Dict[str, Any]:
        """List available audio output devices."""
        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetAllDevices()
            output = []
            for d in devices:
                output.append({
                    'name': d.FriendlyName,
                    'id': d.id,
                    'state': str(d.state) if hasattr(d, 'state') else 'unknown'
                })
            return {'success': True, 'devices': output, 'count': len(output)}
        except Exception:
            # Fallback: use PowerShell
            try:
                proc = subprocess.run(
                    ['powershell', '-Command',
                     'Get-AudioDevice -List | Select-Object Name, Type, Default | ConvertTo-Json'],
                    capture_output=True, text=True, timeout=10,
                )
                if proc.stdout.strip():
                    data = json.loads(proc.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    devices = [{'name': d.get('Name', ''), 'type': d.get('Type', ''), 'default': d.get('Default', False)} for d in data]
                    return {'success': True, 'devices': devices, 'count': len(devices)}
            except Exception:
                pass
            return {'success': False, 'error': 'Install pycaw or AudioDeviceCmdlets PowerShell module', 'devices': []}

    def set_audio_device(self, device_name: str) -> Dict[str, Any]:
        """Switch default audio output device by name substring."""
        try:
            proc = subprocess.run(
                ['powershell', '-Command',
                 f'Get-AudioDevice -List | Where-Object {{$_.Name -match "{device_name}"}} | Set-AudioDevice'],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                return {'success': True, 'device': device_name, 'message': f'Switched audio to {device_name}'}
            # Fallback: open sound settings
            os.system('start ms-settings:sound')
            return {'success': True, 'message': 'Opened sound settings. Please switch device manually.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # VIRTUAL DESKTOP MANAGEMENT
    # ============================================================

    def create_virtual_desktop(self) -> Dict[str, Any]:
        """Create a new virtual desktop."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'ctrl', 'd')
            logger.info("Created new virtual desktop")
            return {'success': True, 'message': 'Created new virtual desktop'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def switch_virtual_desktop(self, direction: str = 'right') -> Dict[str, Any]:
        """Switch to next/previous virtual desktop."""
        try:
            import pyautogui
            if direction.lower() in ('right', 'next'):
                pyautogui.hotkey('win', 'ctrl', 'right')
            else:
                pyautogui.hotkey('win', 'ctrl', 'left')
            return {'success': True, 'direction': direction, 'message': f'Switched desktop {direction}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def close_virtual_desktop(self) -> Dict[str, Any]:
        """Close current virtual desktop."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'ctrl', 'F4')
            logger.info("Closed virtual desktop")
            return {'success': True, 'message': 'Closed current virtual desktop'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def show_task_view(self) -> Dict[str, Any]:
        """Open Task View (all desktops + recent apps)."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'tab')
            return {'success': True, 'message': 'Opened Task View'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # TOUCHPAD CONTROL
    # ============================================================

    def set_touchpad(self, enable: bool) -> Dict[str, Any]:
        """Enable or disable touchpad."""
        try:
            action = 'Enable' if enable else 'Disable'
            proc = subprocess.run(
                ['powershell', '-Command',
                 f'Get-PnpDevice -Class HIDClass | Where-Object {{$_.FriendlyName -match "touchpad|touch pad|precision"}} | {action}-PnpDevice -Confirm:$false'],
                capture_output=True, text=True, timeout=10,
            )
            state = 'enabled' if enable else 'disabled'
            if proc.returncode == 0:
                return {'success': True, 'enabled': enable, 'message': f'Touchpad {state}'}
            return {'success': False, 'error': proc.stderr.strip() or f'Could not {action.lower()} touchpad. Try running as admin.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # DISPLAY / PROJECTION
    # ============================================================

    def set_display_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set display projection mode.

        Args:
            mode: 'pc' (PC screen only), 'duplicate', 'extend', 'second' (Second screen only)
        """
        try:
            mode_map = {
                'pc': '/internal', 'pc only': '/internal', 'laptop': '/internal',
                'duplicate': '/clone', 'mirror': '/clone', 'clone': '/clone',
                'extend': '/extend', 'extended': '/extend',
                'second': '/external', 'projector': '/external', 'second screen': '/external',
            }
            flag = mode_map.get(mode.lower())
            if not flag:
                return {'success': False, 'error': f"Unknown mode: {mode}. Use: pc, duplicate, extend, second"}
            subprocess.run(['DisplaySwitch.exe', flag], timeout=5)
            return {'success': True, 'mode': mode, 'message': f'Display mode set to {mode}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # CLIPBOARD MANAGEMENT
    # ============================================================

    def clear_clipboard(self) -> Dict[str, Any]:
        """Clear the system clipboard."""
        try:
            subprocess.run(['powershell', '-Command', 'Set-Clipboard -Value $null'], capture_output=True, timeout=5)
            return {'success': True, 'message': 'Clipboard cleared'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_clipboard_text(self) -> Dict[str, Any]:
        """Get current clipboard text content."""
        try:
            proc = subprocess.run(
                ['powershell', '-Command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=5,
            )
            text = proc.stdout.strip()
            return {'success': True, 'text': text, 'length': len(text)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        """Set clipboard text content."""
        try:
            proc = subprocess.run(
                ['powershell', '-Command', f'Set-Clipboard -Value "{text}"'],
                capture_output=True, text=True, timeout=5,
            )
            return {'success': True, 'message': f'Copied to clipboard ({len(text)} chars)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def toggle_clipboard_history(self) -> Dict[str, Any]:
        """Open Windows Clipboard History (Win+V)."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'v')
            return {'success': True, 'message': 'Opened clipboard history'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # POWER PLAN MANAGEMENT
    # ============================================================

    def get_power_plan(self) -> Dict[str, Any]:
        """Get current power plan."""
        try:
            proc = subprocess.run(
                ['powercfg', '/getactivescheme'],
                capture_output=True, text=True, timeout=5,
            )
            output = proc.stdout.strip()
            # Extract plan name from output like: "Power Scheme GUID: ... (Balanced)"
            import re
            match = re.search(r'\((.+)\)', output)
            plan_name = match.group(1) if match else output
            return {'success': True, 'plan': plan_name, 'raw': output}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list_power_plans(self) -> Dict[str, Any]:
        """List available power plans."""
        try:
            proc = subprocess.run(
                ['powercfg', '/list'],
                capture_output=True, text=True, timeout=5,
            )
            lines = proc.stdout.strip().splitlines()
            import re
            plans = []
            for line in lines:
                match = re.search(r'([\w-]{36})\s+\((.+?)\)(\s*\*)?', line)
                if match:
                    plans.append({
                        'guid': match.group(1),
                        'name': match.group(2),
                        'active': bool(match.group(3))
                    })
            return {'success': True, 'plans': plans, 'count': len(plans)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_power_plan(self, plan_name: str) -> Dict[str, Any]:
        """Set power plan by name (balanced, power saver, high performance)."""
        try:
            plans = self.list_power_plans()
            if not plans.get('success'):
                return plans
            for p in plans.get('plans', []):
                if plan_name.lower() in p['name'].lower():
                    subprocess.run(['powercfg', '/setactive', p['guid']], timeout=5)
                    logger.info(f"Power plan set to {p['name']}")
                    return {'success': True, 'plan': p['name'], 'message': f"Power plan set to {p['name']}"}
            return {'success': False, 'error': f"Plan '{plan_name}' not found. Available: {[p['name'] for p in plans.get('plans', [])]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_screen_timeout(self, minutes: int, on_battery: bool = True, plugged_in: bool = True) -> Dict[str, Any]:
        """Set screen timeout in minutes (0 = never)."""
        try:
            if on_battery:
                subprocess.run(['powercfg', '/change', 'monitor-timeout-dc', str(minutes)], timeout=5)
            if plugged_in:
                subprocess.run(['powercfg', '/change', 'monitor-timeout-ac', str(minutes)], timeout=5)
            return {'success': True, 'timeout_minutes': minutes, 'message': f'Screen timeout set to {minutes} minutes'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # NETWORK STATUS
    # ============================================================

    def get_network_status(self) -> Dict[str, Any]:
        """Get current network connection status."""
        try:
            proc = subprocess.run(
                ['netsh', 'wlan', 'show', 'interfaces'],
                capture_output=True, text=True, timeout=10,
            )
            output = proc.stdout or ''
            info = {}
            for line in output.splitlines():
                s = line.strip()
                if ':' in s:
                    key, _, val = s.partition(':')
                    key = key.strip().lower()
                    val = val.strip()
                    if key == 'ssid':
                        info['ssid'] = val
                    elif key == 'state':
                        info['state'] = val
                    elif key == 'signal':
                        info['signal'] = val
                    elif 'receive rate' in key:
                        info['receive_rate'] = val
                    elif 'transmit rate' in key:
                        info['transmit_rate'] = val

            # Also get IP address
            try:
                import socket
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                info['ip_address'] = ip
                info['hostname'] = hostname
            except Exception:
                pass

            connected = info.get('state', '').lower() == 'connected'
            return {'success': True, 'connected': connected, **info}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # STARTUP APPS MANAGEMENT
    # ============================================================

    def list_startup_apps(self) -> Dict[str, Any]:
        """List apps in Windows startup."""
        try:
            import winreg
            apps = []
            # Check HKCU Run key
            for root, path_name in [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            ]:
                try:
                    key = winreg.OpenKey(root, path_name, 0, winreg.KEY_READ)
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            apps.append({'name': name, 'path': value, 'scope': 'user' if root == winreg.HKEY_CURRENT_USER else 'system'})
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass

            # Also check Startup folder
            startup_folder = os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup')
            if os.path.exists(startup_folder):
                for f in os.listdir(startup_folder):
                    apps.append({'name': f, 'path': os.path.join(startup_folder, f), 'scope': 'startup_folder'})

            return {'success': True, 'apps': apps, 'count': len(apps)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def disable_startup_app(self, app_name: str) -> Dict[str, Any]:
        """Disable a startup app by name (from registry)."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE | winreg.KEY_READ,
            )
            try:
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
                return {'success': True, 'message': f'Removed {app_name} from startup'}
            except FileNotFoundError:
                winreg.CloseKey(key)
                return {'success': False, 'error': f'{app_name} not found in startup'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # SCREEN RECORDING (basic)
    # ============================================================

    def start_screen_recording(self) -> Dict[str, Any]:
        """Start screen recording using Windows Game Bar (Win+Alt+R)."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'alt', 'r')
            return {'success': True, 'message': 'Screen recording started (Game Bar)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def stop_screen_recording(self) -> Dict[str, Any]:
        """Stop screen recording."""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'alt', 'r')
            return {'success': True, 'message': 'Screen recording stopped'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # QUICK ACCESS SETTINGS
    # ============================================================

    def open_settings(self, page: str = '') -> Dict[str, Any]:
        """Open Windows Settings to a specific page."""
        settings_map = {
            '': 'ms-settings:',
            'display': 'ms-settings:display',
            'sound': 'ms-settings:sound',
            'notifications': 'ms-settings:notifications',
            'battery': 'ms-settings:batterysaver',
            'storage': 'ms-settings:storagesense',
            'wifi': 'ms-settings:network-wifi',
            'bluetooth': 'ms-settings:bluetooth',
            'vpn': 'ms-settings:network-vpn',
            'proxy': 'ms-settings:network-proxy',
            'hotspot': 'ms-settings:network-mobilehotspot',
            'background': 'ms-settings:personalization-background',
            'colors': 'ms-settings:personalization-colors',
            'lockscreen': 'ms-settings:lockscreen',
            'mouse': 'ms-settings:mousetouchpad',
            'keyboard': 'ms-settings:typing',
            'update': 'ms-settings:windowsupdate',
            'about': 'ms-settings:about',
            'apps': 'ms-settings:appsfeatures',
            'default apps': 'ms-settings:defaultapps',
            'privacy': 'ms-settings:privacy',
            'accounts': 'ms-settings:yourinfo',
            'night light': 'ms-settings:nightlight',
            'focus assist': 'ms-settings:quiethours',
            'region': 'ms-settings:regionformatting',
            'language': 'ms-settings:regionlanguage',
            'date': 'ms-settings:dateandtime',
            'power': 'ms-settings:powersleep',
        }
        uri = settings_map.get(page.lower(), f'ms-settings:{page}')
        try:
            os.system(f'start {uri}')
            return {'success': True, 'page': page or 'home', 'message': f'Opened Settings: {page or "home"}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # NOTIFICATION / DO NOT DISTURB
    # ============================================================

    def set_do_not_disturb(self, enable: bool) -> Dict[str, Any]:
        """Toggle Windows Focus Assist / Do Not Disturb."""
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            # NOC_GLOBAL_SETTING_TOASTS_ENABLED: 0=DND on, 1=DND off
            winreg.SetValueEx(key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, winreg.REG_DWORD, 0 if enable else 1)
            winreg.CloseKey(key)
            state = 'enabled' if enable else 'disabled'
            return {'success': True, 'enabled': enable, 'message': f'Do Not Disturb {state}'}
        except Exception as e:
            # Fallback: open focus assist settings
            os.system('start ms-settings:quiethours')
            return {'success': True, 'message': 'Opened Focus Assist settings.'}


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    system = SystemController()
    
    # Test volume
    print("Setting volume to 50%...")
    result = system.set_volume(50)
    print(result)
    
    # Test brightness
    print("\nGetting brightness...")
    result = system.get_brightness()
    print(result)
    
    # Test system info
    print("\nSystem status...")
    result = system.get_system_status()
    print(json.dumps(result, indent=2))
    
    # List WiFi networks
    print("\nWiFi networks...")
    result = system.list_wifi_networks()
    print(f"Found {result['count']} networks")
    
    # Get CPU/Memory
    print("\nCPU Usage:", system.get_cpu_usage()['cpu_percent'], "%")
    print("Memory Usage:", system.get_memory_usage()['used_percent'], "%")
