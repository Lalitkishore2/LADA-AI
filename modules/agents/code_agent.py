"""LADA CodeAgent

Specialized agent for code operations.

Features:
- Write/edit code files
- Run code in sandbox
- Debug assistance
- Git operations
- Language detection
- Code analysis
- Refactoring suggestions

Usage:
    from modules.agents.code_agent import CodeAgent
    
    agent = CodeAgent()
    await agent.create_file("hello.py", "print('Hello')")
    result = await agent.run_code("print(1+1)", language="python")
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import tempfile
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CodeRunResult:
    """Result of code execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    duration_ms: float
    language: str


@dataclass
class GitStatus:
    """Git repository status."""
    branch: str
    staged: List[str]
    unstaged: List[str]
    untracked: List[str]
    ahead: int
    behind: int


@dataclass
class CodeAnalysis:
    """Code analysis result."""
    language: str
    lines_of_code: int
    functions: List[str]
    classes: List[str]
    imports: List[str]
    issues: List[str]


class CodeAgent:
    """Agent for code operations."""
    
    # Language detection by extension
    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.sh': 'bash',
        '.ps1': 'powershell',
    }
    
    # Runners by language
    RUNNERS = {
        'python': ['python', '-c'],
        'javascript': ['node', '-e'],
        'typescript': ['npx', 'ts-node', '-e'],
        'bash': ['bash', '-c'],
        'powershell': ['powershell', '-Command'],
    }
    
    def __init__(self, workspace: Path = None):
        """Initialize code agent.
        
        Args:
            workspace: Workspace directory (default: cwd)
        """
        self.workspace = workspace or Path.cwd()
        
        logger.info(f"[CodeAgent] Init: {self.workspace}")
    
    def _resolve_path(self, path: Union[str, Path]) -> Path:
        """Resolve path relative to workspace."""
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()
    
    # ─────────────────────────────────────────────────────────────────
    # File Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def create_file(
        self,
        path: Union[str, Path],
        content: str,
        language: str = None,
    ) -> bool:
        """Create code file.
        
        Args:
            path: File path
            content: Code content
            language: Language (auto-detect if not specified)
            
        Returns:
            True if created
        """
        resolved = self._resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding='utf-8')
        
        logger.info(f"[CodeAgent] Created {resolved}")
        return True
    
    async def read_file(self, path: Union[str, Path]) -> str:
        """Read code file.
        
        Args:
            path: File path
            
        Returns:
            File content
        """
        return self._resolve_path(path).read_text(encoding='utf-8')
    
    async def edit_file(
        self,
        path: Union[str, Path],
        old_content: str,
        new_content: str,
    ) -> bool:
        """Edit code file by replacing content.
        
        Args:
            path: File path
            old_content: Content to find
            new_content: Replacement content
            
        Returns:
            True if edited
        """
        resolved = self._resolve_path(path)
        content = resolved.read_text(encoding='utf-8')
        
        if old_content not in content:
            logger.warning(f"[CodeAgent] Content not found in {resolved}")
            return False
        
        new_file_content = content.replace(old_content, new_content, 1)
        resolved.write_text(new_file_content, encoding='utf-8')
        
        logger.info(f"[CodeAgent] Edited {resolved}")
        return True
    
    async def insert_at_line(
        self,
        path: Union[str, Path],
        line_number: int,
        content: str,
    ) -> bool:
        """Insert content at specific line.
        
        Args:
            path: File path
            line_number: Line number (1-indexed)
            content: Content to insert
            
        Returns:
            True if inserted
        """
        resolved = self._resolve_path(path)
        lines = resolved.read_text(encoding='utf-8').splitlines(keepends=True)
        
        # Insert at position
        idx = max(0, min(line_number - 1, len(lines)))
        if not content.endswith('\n'):
            content += '\n'
        lines.insert(idx, content)
        
        resolved.write_text(''.join(lines), encoding='utf-8')
        return True
    
    # ─────────────────────────────────────────────────────────────────
    # Code Execution
    # ─────────────────────────────────────────────────────────────────
    
    async def run_code(
        self,
        code: str,
        language: str = "python",
        timeout: float = 30.0,
    ) -> CodeRunResult:
        """Run code snippet.
        
        Args:
            code: Code to run
            language: Programming language
            timeout: Execution timeout
            
        Returns:
            CodeRunResult
        """
        language = language.lower()
        
        if language not in self.RUNNERS:
            return CodeRunResult(
                success=False,
                stdout="",
                stderr=f"Unsupported language: {language}",
                return_code=-1,
                duration_ms=0,
                language=language,
            )
        
        runner = self.RUNNERS[language]
        start = asyncio.get_event_loop().time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *runner, code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            duration = (asyncio.get_event_loop().time() - start) * 1000
            
            return CodeRunResult(
                success=process.returncode == 0,
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                return_code=process.returncode,
                duration_ms=duration,
                language=language,
            )
            
        except asyncio.TimeoutError:
            return CodeRunResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {timeout}s",
                return_code=-1,
                duration_ms=timeout * 1000,
                language=language,
            )
        except Exception as e:
            return CodeRunResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                duration_ms=0,
                language=language,
            )
    
    async def run_file(
        self,
        path: Union[str, Path],
        args: List[str] = None,
        timeout: float = 60.0,
    ) -> CodeRunResult:
        """Run code file.
        
        Args:
            path: File path
            args: Command line arguments
            timeout: Execution timeout
            
        Returns:
            CodeRunResult
        """
        resolved = self._resolve_path(path)
        language = self.detect_language(resolved)
        
        # Build command
        if language == 'python':
            cmd = [sys.executable, str(resolved)] + (args or [])
        elif language == 'javascript':
            cmd = ['node', str(resolved)] + (args or [])
        elif language == 'bash':
            cmd = ['bash', str(resolved)] + (args or [])
        else:
            return CodeRunResult(
                success=False,
                stdout="",
                stderr=f"Cannot run {language} files directly",
                return_code=-1,
                duration_ms=0,
                language=language,
            )
        
        start = asyncio.get_event_loop().time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            duration = (asyncio.get_event_loop().time() - start) * 1000
            
            return CodeRunResult(
                success=process.returncode == 0,
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                return_code=process.returncode,
                duration_ms=duration,
                language=language,
            )
            
        except Exception as e:
            return CodeRunResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                duration_ms=0,
                language=language,
            )
    
    # ─────────────────────────────────────────────────────────────────
    # Git Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def git_status(self) -> Optional[GitStatus]:
        """Get git repository status.
        
        Returns:
            GitStatus or None if not a git repo
        """
        try:
            # Get branch
            branch_result = await self._run_git(['branch', '--show-current'])
            branch = branch_result.strip() if branch_result else 'main'
            
            # Get status
            status_result = await self._run_git(['status', '--porcelain'])
            
            staged = []
            unstaged = []
            untracked = []
            
            for line in status_result.splitlines():
                if not line:
                    continue
                status = line[:2]
                file = line[3:]
                
                if status[0] in 'MADRC':
                    staged.append(file)
                if status[1] in 'MDRC':
                    unstaged.append(file)
                if status == '??':
                    untracked.append(file)
            
            # Get ahead/behind
            ahead_behind = await self._run_git([
                'rev-list', '--left-right', '--count',
                f'{branch}...origin/{branch}'
            ])
            
            ahead, behind = 0, 0
            if ahead_behind:
                parts = ahead_behind.strip().split()
                if len(parts) == 2:
                    ahead, behind = int(parts[0]), int(parts[1])
            
            return GitStatus(
                branch=branch,
                staged=staged,
                unstaged=unstaged,
                untracked=untracked,
                ahead=ahead,
                behind=behind,
            )
            
        except Exception as e:
            logger.warning(f"[CodeAgent] Git status failed: {e}")
            return None
    
    async def git_commit(self, message: str, files: List[str] = None) -> bool:
        """Create git commit.
        
        Args:
            message: Commit message
            files: Files to commit (None = all staged)
            
        Returns:
            True if committed
        """
        try:
            if files:
                await self._run_git(['add'] + files)
            
            await self._run_git(['commit', '-m', message])
            return True
        except Exception as e:
            logger.error(f"[CodeAgent] Git commit failed: {e}")
            return False
    
    async def git_diff(self, file: str = None) -> str:
        """Get git diff.
        
        Args:
            file: Specific file (None = all)
            
        Returns:
            Diff output
        """
        cmd = ['diff']
        if file:
            cmd.append(file)
        return await self._run_git(cmd)
    
    async def _run_git(self, args: List[str]) -> str:
        """Run git command."""
        process = await asyncio.create_subprocess_exec(
            'git', *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace),
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(stderr.decode('utf-8', errors='replace'))
        
        return stdout.decode('utf-8', errors='replace')
    
    # ─────────────────────────────────────────────────────────────────
    # Code Analysis
    # ─────────────────────────────────────────────────────────────────
    
    def detect_language(self, path: Union[str, Path]) -> str:
        """Detect programming language from file.
        
        Args:
            path: File path
            
        Returns:
            Language name
        """
        ext = Path(path).suffix.lower()
        return self.LANGUAGE_MAP.get(ext, 'unknown')
    
    async def analyze_code(self, path: Union[str, Path]) -> CodeAnalysis:
        """Analyze code file.
        
        Args:
            path: File path
            
        Returns:
            CodeAnalysis
        """
        resolved = self._resolve_path(path)
        content = resolved.read_text(encoding='utf-8')
        language = self.detect_language(resolved)
        
        lines = content.splitlines()
        loc = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
        
        # Extract functions
        functions = []
        if language == 'python':
            functions = re.findall(r'^def\s+(\w+)\s*\(', content, re.MULTILINE)
        elif language in ('javascript', 'typescript'):
            functions = re.findall(r'(?:function\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?function|\bconst\s+(\w+)\s*=\s*(?:async\s+)?\()', content)
            functions = [f[0] or f[1] or f[2] for f in functions if any(f)]
        
        # Extract classes
        classes = []
        if language == 'python':
            classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
        elif language in ('javascript', 'typescript'):
            classes = re.findall(r'class\s+(\w+)', content)
        
        # Extract imports
        imports = []
        if language == 'python':
            imports = re.findall(r'^(?:import|from)\s+([^\s]+)', content, re.MULTILINE)
        elif language in ('javascript', 'typescript'):
            imports = re.findall(r"(?:import|require)\s*\(?['\"]([^'\"]+)", content)
        
        # Basic issue detection
        issues = []
        if loc > 500:
            issues.append("File is large (>500 LOC), consider splitting")
        
        return CodeAnalysis(
            language=language,
            lines_of_code=loc,
            functions=functions,
            classes=classes,
            imports=imports,
            issues=issues,
        )
    
    # ─────────────────────────────────────────────────────────────────
    # Debug Assistance
    # ─────────────────────────────────────────────────────────────────
    
    async def explain_error(self, error: str, language: str = "python") -> str:
        """Get explanation for error message.
        
        Args:
            error: Error message/traceback
            language: Programming language
            
        Returns:
            Human-readable explanation
        """
        # Common Python errors
        python_errors = {
            "SyntaxError": "There's a syntax mistake in the code. Check for missing colons, brackets, or quotes.",
            "IndentationError": "The code has incorrect indentation. Python requires consistent spaces/tabs.",
            "NameError": "A variable or function name is used before it's defined.",
            "TypeError": "An operation was performed on incompatible types.",
            "ValueError": "A function received an argument of the right type but wrong value.",
            "KeyError": "A dictionary key doesn't exist.",
            "IndexError": "A list index is out of range.",
            "ImportError": "A module couldn't be imported. Check if it's installed.",
            "AttributeError": "An object doesn't have the requested attribute/method.",
            "FileNotFoundError": "The specified file doesn't exist.",
        }
        
        for error_type, explanation in python_errors.items():
            if error_type in error:
                return f"{error_type}: {explanation}"
        
        return "Unable to identify the specific error. Please check the full traceback for details."


# Singleton
_agent: Optional[CodeAgent] = None


def get_code_agent(**kwargs) -> CodeAgent:
    """Get or create CodeAgent singleton."""
    global _agent
    if _agent is None:
        _agent = CodeAgent(**kwargs)
    return _agent
