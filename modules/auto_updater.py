"""
LADA v7.0 - Auto-Updater Module
Checks for updates from GitHub releases and handles updates
"""

import requests
import json
import os
import sys
import zipfile
import shutil
import subprocess
from pathlib import Path
from packaging import version as pkg_version
from datetime import datetime, timedelta


class AutoUpdater:
    """
    Handles automatic updates for LADA from GitHub releases
    """
    
    def __init__(self, repo="yourusername/lada-ai", current_version="7.0.0"):
        self.repo = repo
        self.current_version = current_version
        self.api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        self.cache_file = Path("config/update_cache.json")
        self.update_check_interval = timedelta(hours=6)  # Check every 6 hours
    
    def check_for_updates(self, force=False):
        """
        Check if a new version is available
        
        Args:
            force: If True, ignore cache and always check
        
        Returns:
            dict: Update info or None if no update
        """
        # Check cache first
        if not force and self._is_cache_valid():
            return self._get_cached_update()
        
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            latest_version = release_data['tag_name'].lstrip('v')
            
            # Compare versions
            if self._is_newer_version(latest_version):
                update_info = {
                    'version': latest_version,
                    'name': release_data['name'],
                    'body': release_data['body'],
                    'published_at': release_data['published_at'],
                    'download_url': self._get_download_url(release_data),
                    'available': True
                }
                
                # Cache the result
                self._cache_update(update_info)
                return update_info
            
            # No update available
            self._cache_update({'available': False})
            return None
            
        except Exception as e:
            print(f"Update check error: {e}")
            return None
    
    def download_update(self, update_info, progress_callback=None):
        """
        Download update file
        
        Args:
            update_info: Update information from check_for_updates
            progress_callback: Function called with progress (0-100)
        
        Returns:
            Path to downloaded file or None
        """
        download_url = update_info.get('download_url')
        if not download_url:
            return None
        
        try:
            # Download to temp folder
            download_dir = Path("temp/updates")
            download_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"lada_v{update_info['version']}.zip"
            download_path = download_dir / filename
            
            # Stream download with progress
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size:
                            progress = int((downloaded / total_size) * 100)
                            progress_callback(progress)
            
            return download_path
            
        except Exception as e:
            print(f"Download error: {e}")
            return None
    
    def install_update(self, update_file):
        """
        Install downloaded update
        
        Args:
            update_file: Path to downloaded update zip
        
        Returns:
            bool: Success status
        """
        try:
            # Create backup first
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"lada_backup_{timestamp}.zip"
            
            # Backup current installation
            self._create_backup(backup_path)
            
            # Extract update
            extract_dir = Path("temp/extract")
            with zipfile.ZipFile(update_file, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Copy files (skip venv, data, config)
            skip_dirs = {'jarvis_env', 'data', 'config', 'logs', 'backups', '__pycache__'}
            
            for item in extract_dir.iterdir():
                if item.name not in skip_dirs:
                    dest = Path(item.name)
                    
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            
            # Clean up
            shutil.rmtree(extract_dir)
            update_file.unlink()
            
            return True
            
        except Exception as e:
            print(f"Installation error: {e}")
            # Attempt rollback
            self._rollback_update(backup_path)
            return False
    
    def auto_restart(self):
        """
        Restart LADA after update
        """
        try:
            python = sys.executable
            script = Path("lada_desktop_app.py")
            
            # Windows-specific restart
            if sys.platform == 'win32':
                subprocess.Popen([python, str(script)], 
                               creationflags=subprocess.DETACHED_PROCESS)
            else:
                subprocess.Popen([python, str(script)])
            
            # Exit current instance
            sys.exit(0)
            
        except Exception as e:
            print(f"Restart error: {e}")
    
    def _is_newer_version(self, latest):
        """Compare version strings"""
        try:
            return pkg_version.parse(latest) > pkg_version.parse(self.current_version)
        except Exception as e:
            return False
    
    def _get_download_url(self, release_data):
        """Extract download URL from release assets"""
        for asset in release_data.get('assets', []):
            if asset['name'].endswith('.zip') and 'source' not in asset['name'].lower():
                return asset['browser_download_url']
        
        # Fallback to source code zip
        return release_data.get('zipball_url')
    
    def _is_cache_valid(self):
        """Check if update cache is still valid"""
        if not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file) as f:
                cache = json.load(f)
            
            cached_time = datetime.fromisoformat(cache.get('checked_at', ''))
            return datetime.now() - cached_time < self.update_check_interval
            
        except Exception as e:
            return False
    
    def _get_cached_update(self):
        """Get cached update info"""
        try:
            with open(self.cache_file) as f:
                cache = json.load(f)
            
            if cache.get('available'):
                return cache.get('update_info')
            return None
            
        except Exception as e:
            return None
    
    def _cache_update(self, update_info):
        """Cache update check result"""
        try:
            cache = {
                'checked_at': datetime.now().isoformat(),
                'available': update_info.get('available', False),
                'update_info': update_info if update_info.get('available') else None
            }
            
            self.cache_file.parent.mkdir(exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
                
        except Exception as e:
            print(f"Cache error: {e}")
    
    def _create_backup(self, backup_path):
        """Create backup of current installation"""
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                skip_dirs = {'jarvis_env', 'temp', 'backups', '__pycache__', '.git'}
                
                for root, dirs, files in os.walk('.'):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    
                    for file in files:
                        if not file.endswith('.pyc'):
                            file_path = os.path.join(root, file)
                            zipf.write(file_path)
                            
        except Exception as e:
            print(f"Backup error: {e}")
    
    def _rollback_update(self, backup_path):
        """Rollback to backup after failed update"""
        try:
            if backup_path.exists():
                # Extract backup
                with zipfile.ZipFile(backup_path, 'r') as zip_ref:
                    zip_ref.extractall('.')
                print("Update rolled back successfully")
                
        except Exception as e:
            print(f"Rollback error: {e}")


class UpdateNotifier:
    """
    Simple notification for available updates
    """
    
    def __init__(self, updater):
        self.updater = updater
    
    def notify(self, update_info):
        """
        Show notification about available update
        
        Args:
            update_info: Update information
        
        Returns:
            str: User choice (update/skip/remind_later)
        """
        from PyQt5.QtWidgets import QMessageBox, QPushButton
        
        msg = QMessageBox()
        msg.setWindowTitle("LADA Update Available")
        msg.setIcon(QMessageBox.Information)
        
        text = f"""
A new version of LADA is available!

Current version: {self.updater.current_version}
New version: {update_info['version']}

Release name: {update_info['name']}

Would you like to download and install it now?
        """
        msg.setText(text.strip())
        
        # Custom buttons
        btn_update = msg.addButton("Update Now", QMessageBox.AcceptRole)
        btn_later = msg.addButton("Remind Later", QMessageBox.RejectRole)
        btn_skip = msg.addButton("Skip This Version", QMessageBox.NoRole)
        
        msg.exec_()
        clicked = msg.clickedButton()
        
        if clicked == btn_update:
            return 'update'
        elif clicked == btn_skip:
            return 'skip'
        else:
            return 'remind_later'


def check_and_notify_updates(current_version="7.0.0"):
    """
    Convenience function to check and notify about updates
    
    Args:
        current_version: Current LADA version
    
    Returns:
        bool: True if update was installed
    """
    updater = AutoUpdater(current_version=current_version)
    update_info = updater.check_for_updates()
    
    if update_info:
        notifier = UpdateNotifier(updater)
        choice = notifier.notify(update_info)
        
        if choice == 'update':
            # Download and install
            print("Downloading update...")
            update_file = updater.download_update(update_info)
            
            if update_file:
                print("Installing update...")
                if updater.install_update(update_file):
                    print("Update installed! Restarting...")
                    updater.auto_restart()
                    return True
    
    return False


if __name__ == '__main__':
    # Test update checker
    check_and_notify_updates()
