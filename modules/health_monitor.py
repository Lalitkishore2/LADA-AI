"""
Health Monitor for LADA v5.0
Monitors all backends and system resources
Provides real-time status and diagnostics
"""

import requests
import logging
from typing import Dict, List, Tuple
from datetime import datetime
import psutil

logger = logging.getLogger('HealthMonitor')

class HealthMonitor:
    """Monitor backend health and system resources"""
    
    def __init__(self, local_url: str, cloud_url: str = '', colab_url: str = '', gemini_key: str = ''):
        self.local_url = local_url
        self.cloud_url = cloud_url
        self.colab_url = colab_url
        self.gemini_key = gemini_key
        
        self.status_history = []
        self.logger = logging.getLogger('HealthMonitor')
    
    def check_local(self) -> Tuple[bool, float, str]:
        """Check local Ollama"""
        try:
            start = datetime.now()
            response = requests.get(
                f'{self.local_url}/api/status',
                timeout=5
            )
            latency = (datetime.now() - start).total_seconds()
            
            if response.status_code == 200:
                return True, latency, "Online"
            else:
                return False, latency, f"Error {response.status_code}"
        except requests.Timeout:
            return False, 5.0, "Timeout"
        except Exception as e:
            return False, 0, str(e)
    
    def check_cloud(self) -> Tuple[bool, float, str]:
        """Check cloud Ollama"""
        if not self.cloud_url:
            return False, 0, "Not configured"
        
        try:
            start = datetime.now()
            response = requests.get(
                f'{self.cloud_url}/api/status',
                timeout=10
            )
            latency = (datetime.now() - start).total_seconds()
            
            if response.status_code == 200:
                return True, latency, "Online"
            else:
                return False, latency, f"Error {response.status_code}"
        except requests.Timeout:
            return False, 10.0, "Timeout"
        except Exception as e:
            return False, 0, str(e)
    
    def check_colab(self) -> Tuple[bool, float, str]:
        """Check Colab T4"""
        if not self.colab_url:
            return False, 0, "Not configured"
        
        try:
            start = datetime.now()
            response = requests.get(
                f'{self.colab_url}/api/status',
                timeout=15,
                verify=False
            )
            latency = (datetime.now() - start).total_seconds()
            
            if response.status_code == 200:
                return True, latency, "Online"
            else:
                return False, latency, f"Error {response.status_code}"
        except requests.Timeout:
            return False, 15.0, "Timeout"
        except Exception as e:
            return False, 0, str(e)
    
    def check_gemini(self) -> Tuple[bool, float, str]:
        """Check Gemini API"""
        if not self.gemini_key:
            return False, 0, "Not configured"
        
        try:
            start = datetime.now()
            response = requests.get(
                f'https://generativelanguage.googleapis.com/v1/models?key={self.gemini_key}',
                timeout=10
            )
            latency = (datetime.now() - start).total_seconds()
            
            if response.status_code == 200:
                return True, latency, "Online"
            else:
                return False, latency, f"Error {response.status_code}"
        except requests.Timeout:
            return False, 10.0, "Timeout"
        except Exception as e:
            return False, 0, str(e)
    
    def check_system(self) -> Dict[str, float]:
        """Check system resources"""
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'battery_percent': psutil.sensors_battery().percent if psutil.sensors_battery() else 0
        }
    
    def check_all(self) -> Dict:
        """Check all backends and system"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'backends': {
                'local': {
                    'online': False,
                    'latency': 0,
                    'status': 'Unknown'
                },
                'cloud': {
                    'online': False,
                    'latency': 0,
                    'status': 'Unknown'
                },
                'colab': {
                    'online': False,
                    'latency': 0,
                    'status': 'Unknown'
                },
                'gemini': {
                    'online': False,
                    'latency': 0,
                    'status': 'Unknown'
                }
            },
            'system': self.check_system(),
            'summary': {
                'backends_online': 0,
                'all_healthy': False
            }
        }
        
        # Check each backend
        online, latency, msg = self.check_local()
        status['backends']['local']['online'] = online
        status['backends']['local']['latency'] = latency
        status['backends']['local']['status'] = msg
        
        online, latency, msg = self.check_cloud()
        status['backends']['cloud']['online'] = online
        status['backends']['cloud']['latency'] = latency
        status['backends']['cloud']['status'] = msg
        
        online, latency, msg = self.check_colab()
        status['backends']['colab']['online'] = online
        status['backends']['colab']['latency'] = latency
        status['backends']['colab']['status'] = msg
        
        online, latency, msg = self.check_gemini()
        status['backends']['gemini']['online'] = online
        status['backends']['gemini']['latency'] = latency
        status['backends']['gemini']['status'] = msg
        
        # Count online backends
        backends_online = sum(1 for b in status['backends'].values() if b['online'])
        status['summary']['backends_online'] = backends_online
        status['summary']['all_healthy'] = backends_online >= 1
        status['summary']['human_readable'] = self.get_status_message()
        
        self.status_history.append(status)
        
        # Keep only last 100 checks
        if len(self.status_history) > 100:
            self.status_history = self.status_history[-100:]
        
        return status
    
    def get_status_message(self) -> str:
        """Get human-readable status"""
        status = self.check_all()
        backends_online = status['summary']['backends_online']
        
        if backends_online == 4:
            return "[OK] All systems online and healthy!"
        elif backends_online >= 2:
            return f"[WARNING] {backends_online}/4 backends online - Degraded but operational"
        elif backends_online == 1:
            return f"[OFFLINE] Only {backends_online}/4 backend online - Critical, limited functionality"
        else:
            return "[FAIL] No backends available - System offline"
    
    def get_detailed_report(self) -> str:
        """Get detailed status report"""
        status = self.check_all()
        
        report = "\n" + "="*70 + "\n"
        report += "🏥 HYBRID JARVIS HEALTH REPORT\n"
        report += "="*70 + "\n\n"
        
        report += "📡 BACKEND STATUS:\n"
        report += "-"*70 + "\n"
        
        for backend_name, backend_status in status['backends'].items():
            icon = "[ONLINE]" if backend_status['online'] else "[OFFLINE]"
            report += f"{icon} {backend_name.upper()}:\n"
            report += f"   Status: {backend_status['status']}\n"
            if backend_status['online']:
                report += f"   Latency: {backend_status['latency']:.2f}s\n"
            report += "\n"
        
        report += "\n💻 SYSTEM RESOURCES:\n"
        report += "-"*70 + "\n"
        
        cpu = status['system']['cpu_percent']
        memory = status['system']['memory_percent']
        disk = status['system']['disk_percent']
        battery = status['system']['battery_percent']
        
        # Color-code based on usage
        def health_icon(percent):
            if percent < 50:
                return "[OK]"
            elif percent < 75:
                return "[WARNING]"
            else:
                return "[FAIL]"
        
        report += f"{health_icon(cpu)} CPU: {cpu:.1f}%\n"
        report += f"{health_icon(memory)} Memory: {memory:.1f}%\n"
        report += f"{health_icon(disk)} Disk: {disk:.1f}%\n"
        
        if battery > 0:
            report += f"{health_icon(battery)} Battery: {battery:.1f}%\n"
        
        report += "\n" + "="*70 + "\n"
        report += f"Summary: {status['summary']['human_readable']}\n"
        report += "="*70 + "\n\n"
        
        return report
    
    def get_slowest_backend(self) -> Tuple[str, float]:
        """Get slowest responding backend"""
        status = self.check_all()
        
        latencies = {}
        for name, backend in status['backends'].items():
            if backend['online']:
                latencies[name] = backend['latency']
        
        if latencies:
            slowest = max(latencies, key=latencies.get)
            return slowest, latencies[slowest]
        
        return 'None', 0
    
    def get_fastest_backend(self) -> Tuple[str, float]:
        """Get fastest responding backend"""
        status = self.check_all()
        
        latencies = {}
        for name, backend in status['backends'].items():
            if backend['online']:
                latencies[name] = backend['latency']
        
        if latencies:
            fastest = min(latencies, key=latencies.get)
            return fastest, latencies[fastest]
        
        return 'None', 0
    
    def diagnose(self) -> str:
        """Run full diagnostic"""
        report = self.get_detailed_report()
        
        slowest, slowest_latency = self.get_slowest_backend()
        fastest, fastest_latency = self.get_fastest_backend()
        
        report += "\n[STATS] PERFORMANCE ANALYSIS:\n"
        report += "-"*70 + "\n"
        report += f"Fastest: {fastest} ({fastest_latency:.2f}s)\n"
        report += f"Slowest: {slowest} ({slowest_latency:.2f}s)\n"
        
        return report

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    monitor = HealthMonitor(
        local_url='http://localhost:11434',
        colab_url='https://abc123.ngrok.io'
    )
    
    print(monitor.get_detailed_report())
    print(monitor.diagnose())
