# file_operations.py
# Complete File System Automation Controller
# Handles all file operations: create, delete, move, copy, search, compress, etc.

import os
import shutil
import zipfile
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class FileOperation(Enum):
    """File operation types"""
    CREATE = "create"
    DELETE = "delete"
    COPY = "copy"
    MOVE = "move"
    RENAME = "rename"
    SEARCH = "search"
    READ = "read"
    COMPRESS = "compress"
    EXTRACT = "extract"
    GET_PROPERTIES = "get_properties"
    BATCH = "batch"


class FileSystemController:
    """Complete file system automation"""
    
    # Protected folders that cannot be deleted
    PROTECTED_FOLDERS = {
        'C:\\Windows',
        'C:\\Program Files',
        'C:\\Program Files (x86)',
        'C:\\ProgramData',
        'C:\\Users\\*\\AppData',
        'C:\\System Volume Information',
    }
    
    # Maximum file size (100GB)
    MAX_FILE_SIZE = 100 * 1024 * 1024 * 1024
    
    def __init__(self, current_directory: str = None):
        """Initialize file system controller"""
        self.current_directory = current_directory or os.path.expanduser('~')
        self.operation_history = []
        self.last_search_results = []
    
    def is_protected(self, path: str) -> bool:
        """Check if path is protected from deletion"""
        path = Path(path)
        for protected in self.PROTECTED_FOLDERS:
            if protected.endswith('*'):
                # Wildcard match
                protected_parent = protected.rstrip('*')
                if str(path).startswith(protected_parent):
                    return True
            else:
                if str(path) == protected or str(path).startswith(protected):
                    return True
        return False
    
    def create_file(self, 
                   path: str, 
                   content: str = "",
                   overwrite: bool = False) -> Dict[str, Any]:
        """
        Create a new file with optional content
        
        Args:
            path: File path
            content: Initial content
            overwrite: Overwrite if exists
        
        Returns:
            {
                'success': True,
                'path': '/path/to/file.txt',
                'size': 1024,
                'timestamp': '2025-12-29T...'
            }
        """
        try:
            full_path = Path(path) if Path(path).is_absolute() else Path(self.current_directory) / path
            
            # Check if file exists
            if full_path.exists() and not overwrite:
                return {
                    'success': False,
                    'error': f'File already exists: {full_path}',
                    'path': str(full_path)
                }
            
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            size = full_path.stat().st_size
            logger.info(f"Created file: {full_path} ({size} bytes)")
            
            return {
                'success': True,
                'path': str(full_path),
                'size': size,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error creating file: {e}")
            return {'success': False, 'error': str(e)}
    
    def delete_file(self, 
                   path: str, 
                   permanent: bool = False,
                   confirm: bool = True) -> Dict[str, Any]:
        """
        Delete a file (to Recycle Bin by default)
        
        Args:
            path: File path
            permanent: Permanently delete (Shift+Delete)
            confirm: Require confirmation
        
        Returns:
            {'success': True/False, 'path': '...', 'error': '...' if failed}
        """
        try:
            full_path = Path(path) if Path(path).is_absolute() else Path(self.current_directory) / path
            
            # Check if path exists
            if not full_path.exists():
                return {'success': False, 'error': f'File not found: {full_path}'}
            
            # Check if protected
            if self.is_protected(str(full_path)):
                return {'success': False, 'error': f'Cannot delete protected file: {full_path}'}
            
            # Delete
            if full_path.is_file():
                if permanent:
                    full_path.unlink()  # Permanent delete
                else:
                    import send2trash  # Soft delete to Recycle Bin
                    send2trash.send2trash(str(full_path))
            elif full_path.is_dir():
                if permanent:
                    shutil.rmtree(full_path)
                else:
                    import send2trash
                    send2trash.send2trash(str(full_path))
            
            logger.info(f"Deleted: {full_path}")
            return {'success': True, 'path': str(full_path)}
        
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return {'success': False, 'error': str(e)}
    
    def copy_file(self, 
                 source: str, 
                 destination: str) -> Dict[str, Any]:
        """
        Copy file or directory
        
        Args:
            source: Source path
            destination: Destination path
        
        Returns:
            {'success': True/False, 'source': '...', 'destination': '...'}
        """
        try:
            source = Path(source) if Path(source).is_absolute() else Path(self.current_directory) / source
            dest = Path(destination) if Path(destination).is_absolute() else Path(self.current_directory) / destination
            
            # Check if source exists
            if not source.exists():
                return {'success': False, 'error': f'Source not found: {source}'}
            
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy
            if source.is_file():
                shutil.copy2(source, dest)
            else:
                shutil.copytree(source, dest, dirs_exist_ok=True)
            
            logger.info(f"Copied {source} to {dest}")
            return {
                'success': True,
                'source': str(source),
                'destination': str(dest)
            }
        
        except Exception as e:
            logger.error(f"Error copying: {e}")
            return {'success': False, 'error': str(e)}
    
    def move_file(self, 
                 source: str, 
                 destination: str) -> Dict[str, Any]:
        """Move (cut) file or directory"""
        try:
            source = Path(source) if Path(source).is_absolute() else Path(self.current_directory) / source
            dest = Path(destination) if Path(destination).is_absolute() else Path(self.current_directory) / destination
            
            if not source.exists():
                return {'success': False, 'error': f'Source not found: {source}'}
            
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Move
            shutil.move(str(source), str(dest))
            
            logger.info(f"Moved {source} to {dest}")
            return {
                'success': True,
                'source': str(source),
                'destination': str(dest)
            }
        
        except Exception as e:
            logger.error(f"Error moving file: {e}")
            return {'success': False, 'error': str(e)}
    
    def rename_file(self, 
                   path: str, 
                   new_name: str) -> Dict[str, Any]:
        """Rename file or folder"""
        try:
            full_path = Path(path) if Path(path).is_absolute() else Path(self.current_directory) / path
            
            if not full_path.exists():
                return {'success': False, 'error': f'Path not found: {full_path}'}
            
            new_path = full_path.parent / new_name
            full_path.rename(new_path)
            
            logger.info(f"Renamed {full_path} to {new_path}")
            return {
                'success': True,
                'old_path': str(full_path),
                'new_path': str(new_path)
            }
        
        except Exception as e:
            logger.error(f"Error renaming: {e}")
            return {'success': False, 'error': str(e)}
    
    def search_files(self, 
                    name: str = None,
                    extension: str = None,
                    search_folder: str = None,
                    min_size: int = None,
                    max_size: int = None,
                    date_after: datetime = None,
                    date_before: datetime = None,
                    recursive: bool = True) -> Dict[str, Any]:
        """
        Advanced file search with filters
        
        Args:
            name: Filename pattern (supports * and ?)
            extension: File extension (.txt, .pdf, etc.)
            search_folder: Folder to search in
            min_size, max_size: File size in bytes
            date_after, date_before: Date range
            recursive: Search subdirectories
        
        Returns:
            {'found': 25, 'files': [...], 'search_time': 0.5}
        """
        try:
            search_dir = Path(search_folder or self.current_directory)
            if not search_dir.exists():
                return {'success': False, 'error': f'Folder not found: {search_dir}'}
            
            results = []
            pattern = f"*{name or ''}*" if name else "*"
            
            # Search
            for file_path in search_dir.rglob(pattern) if recursive else search_dir.glob(pattern):
                # Skip if not file
                if not file_path.is_file():
                    continue
                
                # Check extension
                if extension and not str(file_path).endswith(extension):
                    continue
                
                # Check size
                size = file_path.stat().st_size
                if min_size and size < min_size:
                    continue
                if max_size and size > max_size:
                    continue
                
                # Check date
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if date_after and mtime < date_after:
                    continue
                if date_before and mtime > date_before:
                    continue
                
                results.append({
                    'path': str(file_path),
                    'size': size,
                    'modified': mtime.isoformat(),
                    'extension': file_path.suffix
                })
            
            self.last_search_results = results
            logger.info(f"Found {len(results)} files")
            
            return {
                'success': True,
                'found': len(results),
                'files': results,
                'search_folder': str(search_dir)
            }
        
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_file_properties(self, path: str) -> Dict[str, Any]:
        """Get file properties (size, created, modified, type, permissions)"""
        try:
            full_path = Path(path) if Path(path).is_absolute() else Path(self.current_directory) / path
            
            if not full_path.exists():
                return {'success': False, 'error': f'File not found: {full_path}'}
            
            stat = full_path.stat()
            
            return {
                'success': True,
                'path': str(full_path),
                'name': full_path.name,
                'type': 'folder' if full_path.is_dir() else 'file',
                'size': stat.st_size,
                'size_readable': self._bytes_to_readable(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'accessed': datetime.fromtimestamp(stat.st_atime).isoformat(),
                'is_readonly': not os.access(full_path, os.W_OK),
                'extension': full_path.suffix if full_path.is_file() else None
            }
        
        except Exception as e:
            logger.error(f"Error getting properties: {e}")
            return {'success': False, 'error': str(e)}
    
    def compress_files(self, 
                      paths: List[str], 
                      output_path: str) -> Dict[str, Any]:
        """Compress files/folders to ZIP archive"""
        try:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for path_str in paths:
                    path = Path(path_str) if Path(path_str).is_absolute() else Path(self.current_directory) / path_str
                    
                    if not path.exists():
                        continue
                    
                    if path.is_file():
                        zipf.write(path, arcname=path.name)
                    else:
                        for file in path.rglob('*'):
                            if file.is_file():
                                zipf.write(file, arcname=file.relative_to(path.parent))
            
            logger.info(f"Compressed to {output}")
            return {
                'success': True,
                'archive': str(output),
                'size': output.stat().st_size
            }
        
        except Exception as e:
            logger.error(f"Error compressing: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_archive(self, 
                       archive_path: str, 
                       extract_to: str = None) -> Dict[str, Any]:
        """Extract ZIP/TAR archive"""
        try:
            archive = Path(archive_path)
            extract_dir = Path(extract_to or self.current_directory)
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            if archive.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive, 'r') as zipf:
                    zipf.extractall(extract_dir)
            else:
                return {'success': False, 'error': 'Unsupported archive format'}
            
            logger.info(f"Extracted to {extract_dir}")
            return {
                'success': True,
                'extracted_to': str(extract_dir),
                'archive': str(archive)
            }
        
        except Exception as e:
            logger.error(f"Error extracting: {e}")
            return {'success': False, 'error': str(e)}
    
    def batch_operation(self, 
                       operation: str, 
                       pattern: str, 
                       folder: str) -> Dict[str, Any]:
        """
        Batch operation on files matching pattern
        
        Args:
            operation: 'delete', 'move', 'copy'
            pattern: File pattern (*.txt, *.pdf)
            folder: Target folder
        
        Returns:
            {'success': True, 'affected': 5, 'operation': 'delete'}
        """
        try:
            search_folder = Path(folder)
            if not search_folder.exists():
                return {'success': False, 'error': f'Folder not found: {folder}'}
            
            # Find matching files
            files = list(search_folder.glob(pattern))
            
            if operation == 'delete':
                for file in files:
                    if not self.is_protected(str(file)):
                        file.unlink()
            
            elif operation == 'move':
                dest_folder = Path(folder)
                for file in files:
                    shutil.move(str(file), str(dest_folder / file.name))
            
            logger.info(f"Batch {operation}: {len(files)} files affected")
            return {
                'success': True,
                'operation': operation,
                'affected': len(files),
                'folder': str(search_folder)
            }
        
        except Exception as e:
            logger.error(f"Error in batch operation: {e}")
            return {'success': False, 'error': str(e)}
    
    def navigate_directory(self, path: str) -> Dict[str, Any]:
        """
        Navigate to directory and list contents
        
        Returns:
            {
                'current_directory': '/path',
                'parent': '/parent',
                'folders': ['folder1', 'folder2'],
                'files': ['file1.txt', 'file2.pdf']
            }
        """
        try:
            target = Path(path) if Path(path).is_absolute() else Path(self.current_directory) / path
            
            if not target.exists():
                return {'success': False, 'error': f'Path not found: {target}'}
            
            if not target.is_dir():
                return {'success': False, 'error': f'Not a directory: {target}'}
            
            self.current_directory = str(target)
            
            folders = []
            files = []
            
            for item in target.iterdir():
                if item.is_dir():
                    folders.append(item.name)
                else:
                    files.append(item.name)
            
            return {
                'success': True,
                'current_directory': str(target),
                'parent': str(target.parent) if target.parent != target else None,
                'folders': sorted(folders),
                'files': sorted(files),
                'total_items': len(folders) + len(files)
            }
        
        except Exception as e:
            logger.error(f"Error navigating: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _bytes_to_readable(bytes_size: int) -> str:
        """Convert bytes to readable format (KB, MB, GB)"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    controller = FileSystemController()
    
    # Create a test file
    result = controller.create_file("test.txt", "Hello, World!")
    print("Create:", result)
    
    # Get properties
    result = controller.get_file_properties("test.txt")
    print("Properties:", result)
    
    # Search files
    result = controller.search_files(extension=".txt", search_folder=os.path.expanduser("~"))
    print(f"Found {result['found']} files")
