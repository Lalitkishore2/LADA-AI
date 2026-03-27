"""LADA FileAgent

Specialized agent for file system operations.

Features:
- Find files by pattern/content
- Create/read/update/delete files
- Move/copy/rename operations
- Watch folders for changes
- Search file content
- Directory operations

Usage:
    from modules.agents.file_agent import FileAgent
    
    agent = FileAgent()
    files = await agent.find_files("*.py", content="def main")
    await agent.copy_file("source.txt", "dest.txt")
"""

from __future__ import annotations

import os
import re
import shutil
import fnmatch
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Optional dependency for file watching
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    Observer = None
    FileSystemEventHandler = object
    WATCHDOG_AVAILABLE = False


@dataclass
class FileInfo:
    """Information about a file."""
    path: Path
    name: str
    size: int
    is_dir: bool
    modified: datetime
    created: datetime
    extension: str
    
    @classmethod
    def from_path(cls, path: Path) -> "FileInfo":
        stat = path.stat()
        return cls(
            path=path,
            name=path.name,
            size=stat.st_size,
            is_dir=path.is_dir(),
            modified=datetime.fromtimestamp(stat.st_mtime),
            created=datetime.fromtimestamp(stat.st_ctime),
            extension=path.suffix.lower(),
        )


@dataclass
class SearchResult:
    """File search result with context."""
    path: Path
    line_number: Optional[int] = None
    line_content: Optional[str] = None
    match_start: Optional[int] = None
    match_end: Optional[int] = None


class FileWatchHandler(FileSystemEventHandler):
    """Handler for file system events."""
    
    def __init__(self, callback: Callable):
        self.callback = callback
    
    def on_created(self, event):
        self.callback("created", event.src_path, event.is_directory)
    
    def on_modified(self, event):
        self.callback("modified", event.src_path, event.is_directory)
    
    def on_deleted(self, event):
        self.callback("deleted", event.src_path, event.is_directory)
    
    def on_moved(self, event):
        self.callback("moved", event.src_path, event.is_directory, event.dest_path)


class FileAgent:
    """Agent for file system operations."""
    
    # File extensions by category
    TEXT_EXTENSIONS = {'.txt', '.md', '.rst', '.json', '.yaml', '.yml', '.xml', '.csv', '.log'}
    CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.cs', '.go', '.rs', '.rb'}
    CONFIG_EXTENSIONS = {'.ini', '.cfg', '.conf', '.toml', '.env'}
    
    def __init__(self, base_path: Path = None):
        """Initialize file agent.
        
        Args:
            base_path: Base path for relative operations (default: cwd)
        """
        self.base_path = base_path or Path.cwd()
        self._watchers: Dict[str, Observer] = {}
        
        logger.info(f"[FileAgent] Init: {self.base_path}")
    
    def _resolve_path(self, path: Union[str, Path]) -> Path:
        """Resolve path relative to base."""
        p = Path(path)
        if not p.is_absolute():
            p = self.base_path / p
        return p.resolve()
    
    # ─────────────────────────────────────────────────────────────────
    # Find Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def find_files(
        self,
        pattern: str = "*",
        directory: Union[str, Path] = None,
        content: str = None,
        recursive: bool = True,
        max_results: int = 100,
    ) -> List[FileInfo]:
        """Find files matching pattern.
        
        Args:
            pattern: Glob pattern (e.g., "*.py")
            directory: Search directory (default: base_path)
            content: Search for files containing this text
            recursive: Search subdirectories
            max_results: Maximum results to return
            
        Returns:
            List of FileInfo
        """
        search_dir = self._resolve_path(directory or self.base_path)
        results = []
        
        # Use glob for pattern matching
        glob_method = search_dir.rglob if recursive else search_dir.glob
        
        for path in glob_method(pattern):
            if len(results) >= max_results:
                break
            
            if not path.is_file():
                continue
            
            # Content filter
            if content:
                try:
                    if not await self._file_contains(path, content):
                        continue
                except Exception:
                    continue
            
            results.append(FileInfo.from_path(path))
        
        logger.debug(f"[FileAgent] Found {len(results)} files matching '{pattern}'")
        return results
    
    async def _file_contains(self, path: Path, text: str) -> bool:
        """Check if file contains text."""
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            return text.lower() in content.lower()
        except Exception:
            return False
    
    async def search_content(
        self,
        query: str,
        directory: Union[str, Path] = None,
        pattern: str = "*",
        regex: bool = False,
        max_results: int = 100,
    ) -> List[SearchResult]:
        """Search file contents.
        
        Args:
            query: Search text or regex
            directory: Search directory
            pattern: File pattern to search
            regex: Use regex matching
            max_results: Max results
            
        Returns:
            List of SearchResult with line context
        """
        search_dir = self._resolve_path(directory or self.base_path)
        results = []
        
        compiled = re.compile(query, re.IGNORECASE) if regex else None
        
        for path in search_dir.rglob(pattern):
            if len(results) >= max_results:
                break
            
            if not path.is_file():
                continue
            
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                for line_num, line in enumerate(content.splitlines(), 1):
                    if regex:
                        match = compiled.search(line)
                        if match:
                            results.append(SearchResult(
                                path=path,
                                line_number=line_num,
                                line_content=line.strip(),
                                match_start=match.start(),
                                match_end=match.end(),
                            ))
                    else:
                        if query.lower() in line.lower():
                            results.append(SearchResult(
                                path=path,
                                line_number=line_num,
                                line_content=line.strip(),
                            ))
            except Exception:
                continue
        
        return results
    
    # ─────────────────────────────────────────────────────────────────
    # CRUD Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def read_file(self, path: Union[str, Path]) -> str:
        """Read file content.
        
        Args:
            path: File path
            
        Returns:
            File content as string
        """
        resolved = self._resolve_path(path)
        return resolved.read_text(encoding='utf-8')
    
    async def write_file(self, path: Union[str, Path], content: str, create_dirs: bool = True) -> bool:
        """Write content to file.
        
        Args:
            path: File path
            content: Content to write
            create_dirs: Create parent directories
            
        Returns:
            True if successful
        """
        resolved = self._resolve_path(path)
        
        if create_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        
        resolved.write_text(content, encoding='utf-8')
        logger.info(f"[FileAgent] Wrote {len(content)} chars to {resolved}")
        return True
    
    async def append_file(self, path: Union[str, Path], content: str) -> bool:
        """Append content to file.
        
        Args:
            path: File path
            content: Content to append
            
        Returns:
            True if successful
        """
        resolved = self._resolve_path(path)
        
        with open(resolved, 'a', encoding='utf-8') as f:
            f.write(content)
        
        return True
    
    async def delete_file(self, path: Union[str, Path]) -> bool:
        """Delete file.
        
        Args:
            path: File path
            
        Returns:
            True if successful
        """
        resolved = self._resolve_path(path)
        
        if resolved.is_file():
            resolved.unlink()
            logger.info(f"[FileAgent] Deleted {resolved}")
            return True
        
        return False
    
    async def delete_directory(self, path: Union[str, Path], recursive: bool = False) -> bool:
        """Delete directory.
        
        Args:
            path: Directory path
            recursive: Delete contents recursively
            
        Returns:
            True if successful
        """
        resolved = self._resolve_path(path)
        
        if resolved.is_dir():
            if recursive:
                shutil.rmtree(resolved)
            else:
                resolved.rmdir()
            logger.info(f"[FileAgent] Deleted directory {resolved}")
            return True
        
        return False
    
    # ─────────────────────────────────────────────────────────────────
    # Move/Copy Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def copy_file(self, source: Union[str, Path], dest: Union[str, Path]) -> bool:
        """Copy file.
        
        Args:
            source: Source path
            dest: Destination path
            
        Returns:
            True if successful
        """
        src = self._resolve_path(source)
        dst = self._resolve_path(dest)
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        
        logger.info(f"[FileAgent] Copied {src} -> {dst}")
        return True
    
    async def move_file(self, source: Union[str, Path], dest: Union[str, Path]) -> bool:
        """Move/rename file.
        
        Args:
            source: Source path
            dest: Destination path
            
        Returns:
            True if successful
        """
        src = self._resolve_path(source)
        dst = self._resolve_path(dest)
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        
        logger.info(f"[FileAgent] Moved {src} -> {dst}")
        return True
    
    async def copy_directory(self, source: Union[str, Path], dest: Union[str, Path]) -> bool:
        """Copy directory recursively.
        
        Args:
            source: Source directory
            dest: Destination directory
            
        Returns:
            True if successful
        """
        src = self._resolve_path(source)
        dst = self._resolve_path(dest)
        
        shutil.copytree(src, dst)
        
        logger.info(f"[FileAgent] Copied directory {src} -> {dst}")
        return True
    
    # ─────────────────────────────────────────────────────────────────
    # Directory Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def list_directory(
        self,
        path: Union[str, Path] = None,
        pattern: str = "*",
        include_hidden: bool = False,
    ) -> List[FileInfo]:
        """List directory contents.
        
        Args:
            path: Directory path (default: base_path)
            pattern: Filter pattern
            include_hidden: Include hidden files
            
        Returns:
            List of FileInfo
        """
        dir_path = self._resolve_path(path or self.base_path)
        results = []
        
        for item in dir_path.iterdir():
            if not include_hidden and item.name.startswith('.'):
                continue
            
            if pattern != "*" and not fnmatch.fnmatch(item.name, pattern):
                continue
            
            results.append(FileInfo.from_path(item))
        
        return sorted(results, key=lambda x: (not x.is_dir, x.name.lower()))
    
    async def create_directory(self, path: Union[str, Path], parents: bool = True) -> bool:
        """Create directory.
        
        Args:
            path: Directory path
            parents: Create parent directories
            
        Returns:
            True if created
        """
        resolved = self._resolve_path(path)
        resolved.mkdir(parents=parents, exist_ok=True)
        return True
    
    async def get_directory_size(self, path: Union[str, Path] = None) -> int:
        """Get total directory size.
        
        Args:
            path: Directory path
            
        Returns:
            Total size in bytes
        """
        dir_path = self._resolve_path(path or self.base_path)
        total = 0
        
        for item in dir_path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
        
        return total
    
    # ─────────────────────────────────────────────────────────────────
    # Watch Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def watch_directory(
        self,
        path: Union[str, Path],
        callback: Callable,
        recursive: bool = True,
    ) -> str:
        """Watch directory for changes.
        
        Args:
            path: Directory to watch
            callback: Callback function(event_type, path, is_dir, dest_path=None)
            recursive: Watch subdirectories
            
        Returns:
            Watcher ID for later removal
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog required for file watching")
        
        resolved = self._resolve_path(path)
        watcher_id = str(resolved)
        
        handler = FileWatchHandler(callback)
        observer = Observer()
        observer.schedule(handler, str(resolved), recursive=recursive)
        observer.start()
        
        self._watchers[watcher_id] = observer
        logger.info(f"[FileAgent] Watching {resolved}")
        
        return watcher_id
    
    async def stop_watching(self, watcher_id: str) -> bool:
        """Stop watching directory.
        
        Args:
            watcher_id: ID from watch_directory
            
        Returns:
            True if stopped
        """
        if watcher_id in self._watchers:
            self._watchers[watcher_id].stop()
            self._watchers[watcher_id].join()
            del self._watchers[watcher_id]
            return True
        return False
    
    async def stop_all_watches(self):
        """Stop all directory watchers."""
        for watcher_id in list(self._watchers.keys()):
            await self.stop_watching(watcher_id)
    
    # ─────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────
    
    async def get_file_info(self, path: Union[str, Path]) -> FileInfo:
        """Get detailed file information.
        
        Args:
            path: File path
            
        Returns:
            FileInfo object
        """
        return FileInfo.from_path(self._resolve_path(path))
    
    async def exists(self, path: Union[str, Path]) -> bool:
        """Check if path exists."""
        return self._resolve_path(path).exists()
    
    async def is_file(self, path: Union[str, Path]) -> bool:
        """Check if path is a file."""
        return self._resolve_path(path).is_file()
    
    async def is_directory(self, path: Union[str, Path]) -> bool:
        """Check if path is a directory."""
        return self._resolve_path(path).is_dir()
    
    def __del__(self):
        """Cleanup watchers."""
        for observer in self._watchers.values():
            try:
                observer.stop()
            except Exception:
                pass


# Singleton
_agent: Optional[FileAgent] = None


def get_file_agent(**kwargs) -> FileAgent:
    """Get or create FileAgent singleton."""
    global _agent
    if _agent is None:
        _agent = FileAgent(**kwargs)
    return _agent
