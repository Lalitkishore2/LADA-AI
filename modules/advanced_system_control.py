"""
LADA v9.0 - Advanced System Control Module
Complete file management with voice control capabilities.

Features:
- File CRUD (create, read, update, delete)
- File search by name, type, date, size
- Directory organization (auto-organize downloads)
- File watching for real-time changes
- Clipboard integration
- Disk space monitoring
"""

import os
import shutil
import json
import logging
import fnmatch
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
import threading
import time

logger = logging.getLogger(__name__)

# File type categories for organization
FILE_CATEGORIES = {
    'images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff'],
    'documents': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx'],
    'videos': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
    'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
    'archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
    'code': ['.py', '.js', '.ts', '.html', '.css', '.java', '.cpp', '.c', '.h', '.json', '.xml', '.yaml', '.yml'],
    'executables': ['.exe', '.msi', '.bat', '.cmd', '.ps1', '.sh'],
    'data': ['.csv', '.sql', '.db', '.sqlite', '.json', '.xml'],
}


@dataclass
class FileInfo:
    """Information about a file"""
    name: str
    path: str
    size: int
    size_human: str
    extension: str
    category: str
    created: datetime
    modified: datetime
    is_directory: bool


@dataclass
class SearchResult:
    """Result of a file search"""
    query: str
    total_found: int
    files: List[FileInfo] = field(default_factory=list)
    search_time: float = 0.0


class AdvancedSystemController:
    """
    Advanced system control for complete file management.
    Enables JARVIS-level file automation via voice commands.
    """
    
    def __init__(self):
        """Initialize the advanced system controller"""
        self.home_dir = Path.home()
        self.downloads_dir = self.home_dir / 'Downloads'
        self.documents_dir = self.home_dir / 'Documents'
        self.desktop_dir = self.home_dir / 'Desktop'
        
        # File watcher state
        self._watchers: Dict[str, threading.Thread] = {}
        self._watcher_callbacks: Dict[str, Callable] = {}
        self._watching = False
        
        # Action history for undo
        self.action_history: List[Dict[str, Any]] = []
        
        logger.info("[OK] Advanced System Controller initialized")
    
    # ==================== FILE CRUD ====================
    
    def create_file(self, filename: str, content: str = "", path: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new file with optional content.
        
        Args:
            filename: Name of file to create
            content: Optional content to write
            path: Optional directory path (defaults to Desktop)
        
        Returns:
            Dict with success status and file path
        """
        try:
            # Determine target directory
            if path:
                target_dir = Path(path)
            else:
                target_dir = self.desktop_dir
            
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / filename
            
            # Write content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Record for undo
            self._record_action('create_file', {'path': str(file_path)})
            
            logger.info(f"[OK] Created file: {file_path}")
            return {
                'success': True,
                'path': str(file_path),
                'message': f"Created '{filename}' in {target_dir.name}"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to create file: {e}")
            return {'success': False, 'error': str(e)}
    
    def read_file(self, filepath: str) -> Dict[str, Any]:
        """
        Read contents of a file.
        
        Args:
            filepath: Path to file to read
        
        Returns:
            Dict with success status and content
        """
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return {'success': False, 'error': f"File not found: {filepath}"}
            
            # Check file size (limit to 1MB for safety)
            if file_path.stat().st_size > 1024 * 1024:
                return {'success': False, 'error': "File too large (>1MB). Use specific range."}
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return {
                'success': True,
                'content': content,
                'path': str(file_path),
                'size': len(content)
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to read file: {e}")
            return {'success': False, 'error': str(e)}
    
    def delete_file(self, filepath: str, permanent: bool = False) -> Dict[str, Any]:
        """
        Delete a file (move to recycle bin by default).
        
        Args:
            filepath: Path to file to delete
            permanent: If True, permanently delete (no recycle bin)
        
        Returns:
            Dict with success status
        """
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return {'success': False, 'error': f"File not found: {filepath}"}
            
            # Record for undo before deleting
            if file_path.is_file():
                backup_content = file_path.read_bytes()
                self._record_action('delete_file', {
                    'path': str(file_path),
                    'content': backup_content,
                    'permanent': permanent
                })
            
            if permanent:
                if file_path.is_dir():
                    shutil.rmtree(file_path)
                else:
                    file_path.unlink()
                logger.info(f"[OK] Permanently deleted: {file_path}")
            else:
                # Move to recycle bin using send2trash if available
                try:
                    from send2trash import send2trash
                    send2trash(str(file_path))
                    logger.info(f"[OK] Moved to recycle bin: {file_path}")
                except ImportError:
                    # Fallback to permanent delete
                    if file_path.is_dir():
                        shutil.rmtree(file_path)
                    else:
                        file_path.unlink()
                    logger.info(f"[OK] Deleted (no recycle bin): {file_path}")
            
            return {
                'success': True,
                'path': str(file_path),
                'message': f"Deleted '{file_path.name}'"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to delete: {e}")
            return {'success': False, 'error': str(e)}
    
    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """
        Move a file or directory to a new location.
        
        Args:
            source: Path to file/directory to move
            destination: Destination path or directory
        
        Returns:
            Dict with success status
        """
        try:
            src_path = Path(source)
            dst_path = Path(destination)
            
            if not src_path.exists():
                return {'success': False, 'error': f"Source not found: {source}"}
            
            # If destination is a directory, move into it
            if dst_path.is_dir():
                dst_path = dst_path / src_path.name
            
            # Create parent directories if needed
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Record for undo
            self._record_action('move_file', {
                'source': str(src_path),
                'destination': str(dst_path)
            })
            
            shutil.move(str(src_path), str(dst_path))
            
            logger.info(f"[OK] Moved: {src_path} -> {dst_path}")
            return {
                'success': True,
                'source': str(src_path),
                'destination': str(dst_path),
                'message': f"Moved '{src_path.name}' to {dst_path.parent.name}"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to move: {e}")
            return {'success': False, 'error': str(e)}
    
    def copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """
        Copy a file or directory to a new location.
        
        Args:
            source: Path to file/directory to copy
            destination: Destination path or directory
        
        Returns:
            Dict with success status
        """
        try:
            src_path = Path(source)
            dst_path = Path(destination)
            
            if not src_path.exists():
                return {'success': False, 'error': f"Source not found: {source}"}
            
            # If destination is a directory, copy into it
            if dst_path.is_dir():
                dst_path = dst_path / src_path.name
            
            # Create parent directories if needed
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Record for undo
            self._record_action('copy_file', {'destination': str(dst_path)})
            
            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path))
            else:
                shutil.copy2(str(src_path), str(dst_path))
            
            logger.info(f"[OK] Copied: {src_path} -> {dst_path}")
            return {
                'success': True,
                'source': str(src_path),
                'destination': str(dst_path),
                'message': f"Copied '{src_path.name}' to {dst_path.parent.name}"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to copy: {e}")
            return {'success': False, 'error': str(e)}
    
    def rename_file(self, filepath: str, new_name: str) -> Dict[str, Any]:
        """
        Rename a file or directory.
        
        Args:
            filepath: Path to file/directory to rename
            new_name: New name (not full path, just the name)
        
        Returns:
            Dict with success status
        """
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return {'success': False, 'error': f"File not found: {filepath}"}
            
            new_path = file_path.parent / new_name
            
            if new_path.exists():
                return {'success': False, 'error': f"A file named '{new_name}' already exists"}
            
            # Record for undo
            self._record_action('rename_file', {
                'old_path': str(file_path),
                'new_path': str(new_path)
            })
            
            file_path.rename(new_path)
            
            logger.info(f"[OK] Renamed: {file_path.name} -> {new_name}")
            return {
                'success': True,
                'old_name': file_path.name,
                'new_name': new_name,
                'path': str(new_path),
                'message': f"Renamed to '{new_name}'"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to rename: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== FILE SEARCH ====================
    
    def search_files(
        self,
        pattern: str = "*",
        directory: Optional[str] = None,
        file_type: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[datetime] = None,
        modified_before: Optional[datetime] = None,
        recursive: bool = True,
        limit: int = 50
    ) -> SearchResult:
        """
        Search for files with various filters.
        
        Args:
            pattern: Filename pattern (supports wildcards like *.py)
            directory: Directory to search (defaults to home)
            file_type: Category like 'images', 'documents', etc.
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            modified_after: Only files modified after this date
            modified_before: Only files modified before this date
            recursive: Search subdirectories
            limit: Maximum results to return
        
        Returns:
            SearchResult with matching files
        """
        start_time = time.time()
        search_dir = Path(directory) if directory else self.home_dir
        
        if not search_dir.exists():
            return SearchResult(query=pattern, total_found=0)
        
        # Get file extensions for type filter
        type_extensions = set()
        if file_type and file_type.lower() in FILE_CATEGORIES:
            type_extensions = set(FILE_CATEGORIES[file_type.lower()])
        
        results: List[FileInfo] = []
        
        try:
            # Choose iteration method
            if recursive:
                file_iter = search_dir.rglob(pattern)
            else:
                file_iter = search_dir.glob(pattern)
            
            for file_path in file_iter:
                if len(results) >= limit:
                    break
                
                try:
                    stat = file_path.stat()
                    
                    # Apply filters
                    if type_extensions and file_path.suffix.lower() not in type_extensions:
                        continue
                    
                    if min_size and stat.st_size < min_size:
                        continue
                    
                    if max_size and stat.st_size > max_size:
                        continue
                    
                    modified = datetime.fromtimestamp(stat.st_mtime)
                    
                    if modified_after and modified < modified_after:
                        continue
                    
                    if modified_before and modified > modified_before:
                        continue
                    
                    # Get file category
                    category = self._get_file_category(file_path.suffix.lower())
                    
                    results.append(FileInfo(
                        name=file_path.name,
                        path=str(file_path),
                        size=stat.st_size,
                        size_human=self._human_readable_size(stat.st_size),
                        extension=file_path.suffix.lower(),
                        category=category,
                        created=datetime.fromtimestamp(stat.st_ctime),
                        modified=modified,
                        is_directory=file_path.is_dir()
                    ))
                
                except (PermissionError, OSError):
                    continue
        
        except Exception as e:
            logger.error(f"Search error: {e}")
        
        search_time = time.time() - start_time
        
        return SearchResult(
            query=pattern,
            total_found=len(results),
            files=results,
            search_time=search_time
        )
    
    def find_large_files(self, directory: Optional[str] = None, min_size_mb: int = 100, limit: int = 20) -> SearchResult:
        """Find files larger than specified size in MB"""
        return self.search_files(
            directory=directory or str(self.home_dir),
            min_size=min_size_mb * 1024 * 1024,
            limit=limit
        )
    
    def find_recent_files(self, directory: Optional[str] = None, days: int = 7, limit: int = 50) -> SearchResult:
        """Find files modified in the last N days"""
        return self.search_files(
            directory=directory or str(self.home_dir),
            modified_after=datetime.now() - timedelta(days=days),
            limit=limit
        )
    
    def find_old_files(self, directory: Optional[str] = None, days: int = 365, limit: int = 50) -> SearchResult:
        """Find files not modified in the last N days"""
        return self.search_files(
            directory=directory or str(self.home_dir),
            modified_before=datetime.now() - timedelta(days=days),
            limit=limit
        )
    
    # ==================== ORGANIZATION ====================
    
    def organize_downloads(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Organize Downloads folder by file type.
        
        Args:
            dry_run: If True, only show what would be done
        
        Returns:
            Dict with organization results
        """
        return self.organize_directory(str(self.downloads_dir), dry_run=dry_run)
    
    def organize_directory(self, directory: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Organize a directory by file type into subfolders.
        
        Args:
            directory: Path to directory to organize
            dry_run: If True, only show what would be done
        
        Returns:
            Dict with organization results
        """
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                return {'success': False, 'error': f"Directory not found: {directory}"}
            
            organized = {}
            moved_count = 0
            
            for file_path in dir_path.iterdir():
                if file_path.is_dir():
                    continue
                
                # Get category for this file
                category = self._get_file_category(file_path.suffix.lower())
                if category == 'other':
                    continue  # Skip unknown types
                
                # Create category folder
                category_folder = dir_path / category.capitalize()
                
                if not dry_run:
                    category_folder.mkdir(exist_ok=True)
                    dest = category_folder / file_path.name
                    
                    # Handle duplicates
                    counter = 1
                    while dest.exists():
                        stem = file_path.stem
                        suffix = file_path.suffix
                        dest = category_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    shutil.move(str(file_path), str(dest))
                    moved_count += 1
                
                if category not in organized:
                    organized[category] = []
                organized[category].append(file_path.name)
            
            # Record for undo (simplified - just record the action)
            if not dry_run:
                self._record_action('organize_directory', {
                    'directory': str(dir_path),
                    'organized': organized
                })
            
            logger.info(f"[OK] Organized {moved_count} files in {dir_path}")
            
            return {
                'success': True,
                'directory': str(dir_path),
                'organized': organized,
                'moved_count': moved_count,
                'dry_run': dry_run,
                'message': f"Organized {moved_count} files into {len(organized)} folders"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to organize: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_folder_structure(self, base_path: str, structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a folder structure from a dictionary.
        
        Args:
            base_path: Base directory to create structure in
            structure: Dict defining folder structure
                       Example: {'src': {'components': {}, 'utils': {}}, 'docs': {}}
        
        Returns:
            Dict with created folders
        """
        try:
            base = Path(base_path)
            created = []
            
            def create_recursive(current_path: Path, struct: Dict[str, Any]):
                for name, children in struct.items():
                    folder_path = current_path / name
                    folder_path.mkdir(parents=True, exist_ok=True)
                    created.append(str(folder_path))
                    
                    if isinstance(children, dict) and children:
                        create_recursive(folder_path, children)
            
            create_recursive(base, structure)
            
            logger.info(f"[OK] Created {len(created)} folders in {base}")
            return {
                'success': True,
                'base_path': str(base),
                'created_folders': created,
                'message': f"Created {len(created)} folders"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to create structure: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== FILE INFO ====================
    
    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """
        Get detailed information about a file.
        
        Args:
            filepath: Path to file
        
        Returns:
            Dict with file information
        """
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return {'success': False, 'error': f"File not found: {filepath}"}
            
            stat = file_path.stat()
            
            return {
                'success': True,
                'name': file_path.name,
                'path': str(file_path),
                'size': stat.st_size,
                'size_human': self._human_readable_size(stat.st_size),
                'extension': file_path.suffix.lower(),
                'category': self._get_file_category(file_path.suffix.lower()),
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'is_directory': file_path.is_dir(),
                'is_hidden': file_path.name.startswith('.'),
                'parent': str(file_path.parent)
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to get file info: {e}")
            return {'success': False, 'error': str(e)}
    
    def list_directory(self, directory: Optional[str] = None, show_hidden: bool = False) -> Dict[str, Any]:
        """
        List contents of a directory.
        
        Args:
            directory: Path to directory (defaults to current)
            show_hidden: Include hidden files
        
        Returns:
            Dict with directory contents
        """
        try:
            dir_path = Path(directory) if directory else Path.cwd()
            if not dir_path.exists():
                return {'success': False, 'error': f"Directory not found: {directory}"}
            
            items = []
            for item in sorted(dir_path.iterdir()):
                if not show_hidden and item.name.startswith('.'):
                    continue
                
                try:
                    stat = item.stat()
                    items.append({
                        'name': item.name,
                        'type': 'directory' if item.is_dir() else 'file',
                        'size': stat.st_size if item.is_file() else 0,
                        'size_human': self._human_readable_size(stat.st_size) if item.is_file() else '-',
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except (PermissionError, OSError):
                    continue
            
            return {
                'success': True,
                'directory': str(dir_path),
                'count': len(items),
                'items': items
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to list directory: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_disk_space(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get disk space information.
        
        Args:
            path: Path to check (defaults to system drive)
        
        Returns:
            Dict with disk space info
        """
        try:
            import psutil
            
            check_path = path or str(Path.home())
            usage = psutil.disk_usage(check_path)
            
            return {
                'success': True,
                'path': check_path,
                'total': usage.total,
                'total_human': self._human_readable_size(usage.total),
                'used': usage.used,
                'used_human': self._human_readable_size(usage.used),
                'free': usage.free,
                'free_human': self._human_readable_size(usage.free),
                'percent_used': usage.percent
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to get disk space: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== FILE WATCHING ====================
    
    def watch_directory(self, directory: str, callback: Callable[[str, str], None]) -> Dict[str, Any]:
        """
        Watch a directory for changes (simplified polling implementation).
        
        Args:
            directory: Directory to watch
            callback: Function to call on changes (event_type, file_path)
        
        Returns:
            Dict with watcher status
        """
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                return {'success': False, 'error': f"Directory not found: {directory}"}
            
            if str(dir_path) in self._watchers:
                return {'success': False, 'error': "Already watching this directory"}
            
            self._watcher_callbacks[str(dir_path)] = callback
            
            def watch_loop():
                last_state = self._get_directory_state(dir_path)
                
                while str(dir_path) in self._watchers:
                    time.sleep(1)  # Poll every second
                    
                    try:
                        current_state = self._get_directory_state(dir_path)
                        
                        # Check for changes
                        for path, mtime in current_state.items():
                            if path not in last_state:
                                callback('created', path)
                            elif last_state[path] != mtime:
                                callback('modified', path)
                        
                        for path in last_state:
                            if path not in current_state:
                                callback('deleted', path)
                        
                        last_state = current_state
                    
                    except Exception as e:
                        logger.error(f"Watch error: {e}")
            
            thread = threading.Thread(target=watch_loop, daemon=True)
            self._watchers[str(dir_path)] = thread
            thread.start()
            
            logger.info(f"[OK] Started watching: {dir_path}")
            return {
                'success': True,
                'directory': str(dir_path),
                'message': f"Started watching {dir_path.name}"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to start watcher: {e}")
            return {'success': False, 'error': str(e)}
    
    def stop_watching(self, directory: str) -> Dict[str, Any]:
        """Stop watching a directory"""
        try:
            dir_path = Path(directory)
            key = str(dir_path)
            
            if key in self._watchers:
                del self._watchers[key]
                if key in self._watcher_callbacks:
                    del self._watcher_callbacks[key]
                
                logger.info(f"[OK] Stopped watching: {dir_path}")
                return {'success': True, 'message': f"Stopped watching {dir_path.name}"}
            
            return {'success': False, 'error': "Not watching this directory"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_directory_state(self, directory: Path) -> Dict[str, float]:
        """Get current state of directory (path -> mtime)"""
        state = {}
        try:
            for item in directory.iterdir():
                state[str(item)] = item.stat().st_mtime
        except Exception as e:
            pass
        return state
    
    # ==================== UNDO SYSTEM ====================
    
    def _record_action(self, action_type: str, data: Dict[str, Any]):
        """Record an action for potential undo"""
        self.action_history.append({
            'type': action_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 50 actions
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]
    
    def undo_last_action(self) -> Dict[str, Any]:
        """
        Undo the last file operation.
        
        Returns:
            Dict with undo result
        """
        if not self.action_history:
            return {'success': False, 'error': "No actions to undo"}
        
        last_action = self.action_history.pop()
        action_type = last_action['type']
        data = last_action['data']
        
        try:
            if action_type == 'create_file':
                # Delete the created file
                Path(data['path']).unlink(missing_ok=True)
                return {'success': True, 'message': f"Undone: file creation"}
            
            elif action_type == 'delete_file' and 'content' in data:
                # Restore the deleted file
                Path(data['path']).write_bytes(data['content'])
                return {'success': True, 'message': f"Undone: file deletion"}
            
            elif action_type == 'move_file':
                # Move back to original location
                shutil.move(data['destination'], data['source'])
                return {'success': True, 'message': f"Undone: file move"}
            
            elif action_type == 'copy_file':
                # Delete the copy
                Path(data['destination']).unlink(missing_ok=True)
                return {'success': True, 'message': f"Undone: file copy"}
            
            elif action_type == 'rename_file':
                # Rename back
                Path(data['new_path']).rename(data['old_path'])
                return {'success': True, 'message': f"Undone: file rename"}
            
            else:
                return {'success': False, 'error': f"Cannot undo action type: {action_type}"}
        
        except Exception as e:
            logger.error(f"[X] Undo failed: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== UTILITIES ====================
    
    def _get_file_category(self, extension: str) -> str:
        """Get category for a file extension"""
        for category, extensions in FILE_CATEGORIES.items():
            if extension in extensions:
                return category
        return 'other'
    
    def _human_readable_size(self, size: int) -> str:
        """Convert bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


# Factory function for workflow engine integration
def create_advanced_system_controller() -> AdvancedSystemController:
    """Create and return an AdvancedSystemController instance"""
    return AdvancedSystemController()


if __name__ == '__main__':
    # Test the controller
    logging.basicConfig(level=logging.INFO)
    controller = AdvancedSystemController()
    
    # Test file info
    print("\n=== Testing File Operations ===")
    result = controller.get_disk_space()
    print(f"Disk Space: {result.get('free_human', 'N/A')} free")
    
    # Test search
    result = controller.find_recent_files(days=1, limit=5)
    print(f"\nRecent files (last 24h): {result.total_found} found")
    for f in result.files[:3]:
        print(f"  - {f.name} ({f.size_human})")
    
    # Test list directory
    result = controller.list_directory(str(Path.home() / 'Desktop'))
    print(f"\nDesktop items: {result.get('count', 0)}")
    
    print("\n[OK] Advanced System Controller tests complete!")
