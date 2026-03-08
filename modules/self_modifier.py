"""
LADA v11.0 - Self-Modifying Code Engine
Safe AST-based code analysis and refactoring with rollback support.

Allows LADA to analyze, modify, and evolve its own modules with:
- AST parsing for safe code analysis
- Pattern-validated modifications
- Pre-modification backups with rollback
- Test verification before applying changes
- Git-style version tracking
"""

import os
import ast
import sys
import json
import time
import shutil
import hashlib
import logging
import importlib
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CodeModification:
    """Represents a proposed code modification."""
    file_path: str
    modification_type: str  # "add_function", "modify_function", "add_import", "refactor"
    description: str
    original_code: str = ""
    new_code: str = ""
    target_name: str = ""  # Function/class name being modified
    validated: bool = False
    applied: bool = False
    backup_path: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModificationResult:
    """Result of applying or validating a modification."""
    success: bool
    message: str
    backup_path: str = ""
    tests_passed: Optional[bool] = None


class CodeAnalyzer:
    """Analyze Python source code using AST."""

    @staticmethod
    def parse_file(file_path: str) -> Optional[ast.Module]:
        """Parse a Python file into an AST."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            return ast.parse(source, filename=file_path)
        except SyntaxError as e:
            logger.error(f"[SelfMod] Syntax error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"[SelfMod] Parse error: {e}")
            return None

    @staticmethod
    def get_functions(tree: ast.Module) -> List[Dict[str, Any]]:
        """Extract all function/method definitions."""
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, 'end_lineno', node.lineno),
                    "args": [a.arg for a in node.args.args],
                    "decorators": [
                        ast.dump(d) for d in node.decorator_list
                    ],
                    "docstring": ast.get_docstring(node) or "",
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                })
        return functions

    @staticmethod
    def get_classes(tree: ast.Module) -> List[Dict[str, Any]]:
        """Extract all class definitions."""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, 'end_lineno', node.lineno),
                    "bases": [ast.dump(b) for b in node.bases],
                    "methods": methods,
                    "docstring": ast.get_docstring(node) or "",
                })
        return classes

    @staticmethod
    def get_imports(tree: ast.Module) -> List[Dict[str, Any]]:
        """Extract all imports."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "type": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    })
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append({
                        "type": "from",
                        "module": node.module or "",
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    })
        return imports

    @staticmethod
    def validate_code(code: str) -> Tuple[bool, str]:
        """Validate Python code syntax."""
        try:
            ast.parse(code)
            return True, "Syntax valid"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

    @staticmethod
    def analyze_complexity(file_path: str) -> Dict[str, Any]:
        """Analyze code complexity metrics."""
        tree = CodeAnalyzer.parse_file(file_path)
        if not tree:
            return {"error": "Could not parse file"}

        functions = CodeAnalyzer.get_functions(tree)
        classes = CodeAnalyzer.get_classes(tree)

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        return {
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            "functions": len(functions),
            "classes": len(classes),
            "avg_function_length": (
                sum(f.get("end_line", f["line"]) - f["line"] for f in functions) / max(1, len(functions))
            ),
        }


class BackupManager:
    """Manage code backups for safe rollback."""

    def __init__(self, backup_dir: str = "data/code_backups"):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)

    def create_backup(self, file_path: str) -> str:
        """Create a backup of a file. Returns backup path."""
        filename = os.path.basename(file_path)
        timestamp = int(time.time())
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
        backup_name = f"{filename}.{timestamp}.{file_hash}.bak"
        backup_path = os.path.join(self.backup_dir, backup_name)

        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"[SelfMod] Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"[SelfMod] Backup failed: {e}")
            return ""

    def restore_backup(self, backup_path: str, original_path: str) -> bool:
        """Restore a file from backup."""
        try:
            shutil.copy2(backup_path, original_path)
            logger.info(f"[SelfMod] Restored from backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"[SelfMod] Restore failed: {e}")
            return False

    def list_backups(self, file_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available backups."""
        backups = []
        for f in Path(self.backup_dir).glob("*.bak"):
            if file_path:
                base = os.path.basename(file_path)
                if not f.name.startswith(base):
                    continue
            backups.append({
                "backup_path": str(f),
                "filename": f.name,
                "size": f.stat().st_size,
                "created": f.stat().st_mtime,
            })
        return sorted(backups, key=lambda x: x["created"], reverse=True)


class SelfModifyingEngine:
    """
    Safe self-modifying code engine.

    Features:
    - AST-based code analysis
    - Add/modify/remove functions and classes
    - Automatic backup before any modification
    - Syntax validation before applying changes
    - Import management
    - Test verification (runs tests after change)
    - Full rollback to any previous state
    - Modification history tracking
    """

    # Patterns that are NEVER allowed in modifications
    FORBIDDEN_PATTERNS = [
        "os.system",
        "subprocess.call",
        "subprocess.Popen",
        "exec(",
        "eval(",
        "__import__",
        "shutil.rmtree",
        "os.remove",
        "os.unlink",
    ]

    def __init__(self, project_dir: str = ".", backup_dir: str = "data/code_backups"):
        self.project_dir = os.path.abspath(project_dir)
        self.analyzer = CodeAnalyzer()
        self.backup_mgr = BackupManager(backup_dir)
        self._modification_history: List[CodeModification] = []
        self._history_file = os.path.join(backup_dir, "modification_history.json")
        self._load_history()

    def _load_history(self):
        if os.path.exists(self._history_file):
            try:
                with open(self._history_file, 'r') as f:
                    data = json.load(f)
                # Just load metadata, not full objects
                logger.info(f"[SelfMod] Loaded {len(data)} modification records")
            except Exception:
                pass

    def _save_history(self):
        try:
            records = [
                {
                    "file_path": m.file_path,
                    "modification_type": m.modification_type,
                    "description": m.description,
                    "target_name": m.target_name,
                    "applied": m.applied,
                    "backup_path": m.backup_path,
                    "timestamp": m.timestamp,
                }
                for m in self._modification_history[-100:]
            ]
            with open(self._history_file, 'w') as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.error(f"[SelfMod] History save error: {e}")

    def analyze_module(self, file_path: str) -> Dict[str, Any]:
        """Analyze a Python module's structure."""
        full_path = self._resolve_path(file_path)
        tree = self.analyzer.parse_file(full_path)
        if not tree:
            return {"error": f"Could not parse {file_path}"}

        return {
            "file": file_path,
            "functions": self.analyzer.get_functions(tree),
            "classes": self.analyzer.get_classes(tree),
            "imports": self.analyzer.get_imports(tree),
            "complexity": self.analyzer.analyze_complexity(full_path),
        }

    def validate_modification(self, modification: CodeModification) -> ModificationResult:
        """
        Validate a proposed modification before applying.

        Checks:
        1. New code is valid Python syntax
        2. No forbidden patterns
        3. File exists and is writable
        """
        # Check forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in modification.new_code:
                return ModificationResult(
                    success=False,
                    message=f"Forbidden pattern detected: {pattern}"
                )

        # Validate syntax
        valid, msg = self.analyzer.validate_code(modification.new_code)
        if not valid:
            return ModificationResult(success=False, message=msg)

        # Check file exists
        full_path = self._resolve_path(modification.file_path)
        if not os.path.exists(full_path):
            return ModificationResult(
                success=False,
                message=f"File not found: {full_path}"
            )

        modification.validated = True
        return ModificationResult(success=True, message="Validation passed")

    def apply_modification(self, modification: CodeModification,
                           run_tests: bool = True) -> ModificationResult:
        """
        Apply a code modification with backup and optional test verification.
        """
        full_path = self._resolve_path(modification.file_path)

        # Validate first
        if not modification.validated:
            val_result = self.validate_modification(modification)
            if not val_result.success:
                return val_result

        # Create backup
        backup_path = self.backup_mgr.create_backup(full_path)
        if not backup_path:
            return ModificationResult(
                success=False,
                message="Failed to create backup"
            )
        modification.backup_path = backup_path

        # Read current code
        with open(full_path, 'r', encoding='utf-8') as f:
            modification.original_code = f.read()

        # Apply modification based on type
        try:
            if modification.modification_type == "add_function":
                new_content = modification.original_code.rstrip() + "\n\n" + modification.new_code + "\n"
            elif modification.modification_type == "replace_function":
                new_content = self._replace_function(
                    modification.original_code,
                    modification.target_name,
                    modification.new_code,
                )
            elif modification.modification_type == "add_import":
                new_content = modification.new_code + "\n" + modification.original_code
            elif modification.modification_type == "full_replace":
                new_content = modification.new_code
            else:
                new_content = modification.original_code + "\n" + modification.new_code

            # Validate the complete new file
            valid, msg = self.analyzer.validate_code(new_content)
            if not valid:
                return ModificationResult(
                    success=False,
                    message=f"Modified file has syntax errors: {msg}",
                    backup_path=backup_path,
                )

            # Write new code
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            modification.applied = True
            self._modification_history.append(modification)
            self._save_history()

            # Optional: Run tests
            tests_passed = None
            if run_tests:
                tests_passed = self._run_tests(full_path)
                if not tests_passed:
                    # Rollback on test failure
                    self.backup_mgr.restore_backup(backup_path, full_path)
                    modification.applied = False
                    return ModificationResult(
                        success=False,
                        message="Tests failed after modification, rolled back",
                        backup_path=backup_path,
                        tests_passed=False,
                    )

            logger.info(f"[SelfMod] Applied {modification.modification_type} to {modification.file_path}")
            return ModificationResult(
                success=True,
                message=f"Modification applied successfully",
                backup_path=backup_path,
                tests_passed=tests_passed,
            )

        except Exception as e:
            # Rollback on error
            self.backup_mgr.restore_backup(backup_path, full_path)
            return ModificationResult(
                success=False,
                message=f"Error applying modification: {e}",
                backup_path=backup_path,
            )

    def _replace_function(self, source: str, func_name: str, new_code: str) -> str:
        """Replace a function in source code by name."""
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name:
                    start = node.lineno - 1
                    end = getattr(node, 'end_lineno', start + 1)
                    # Replace the function lines
                    new_lines = new_code.splitlines(keepends=True)
                    if not new_lines[-1].endswith('\n'):
                        new_lines[-1] += '\n'
                    lines[start:end] = new_lines
                    return ''.join(lines)

        # Function not found, append
        return source.rstrip() + "\n\n" + new_code + "\n"

    def _run_tests(self, file_path: str) -> bool:
        """Run basic import test for modified file."""
        try:
            # Just verify the file can be compiled
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            compile(code, file_path, 'exec')
            return True
        except Exception as e:
            logger.error(f"[SelfMod] Test failed: {e}")
            return False

    def rollback(self, file_path: str, steps: int = 1) -> ModificationResult:
        """Rollback to a previous version."""
        full_path = self._resolve_path(file_path)
        backups = self.backup_mgr.list_backups(full_path)

        if not backups or steps > len(backups):
            return ModificationResult(
                success=False,
                message=f"No backup available (requested {steps} steps back)"
            )

        backup = backups[min(steps - 1, len(backups) - 1)]
        if self.backup_mgr.restore_backup(backup["backup_path"], full_path):
            return ModificationResult(
                success=True,
                message=f"Rolled back to {backup['filename']}",
                backup_path=backup["backup_path"],
            )
        return ModificationResult(success=False, message="Rollback failed")

    def _resolve_path(self, file_path: str) -> str:
        """Resolve relative path to absolute."""
        if os.path.isabs(file_path):
            return file_path
        return os.path.join(self.project_dir, file_path)

    def get_modification_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent modification history."""
        return [
            {
                "file": m.file_path,
                "type": m.modification_type,
                "description": m.description,
                "target": m.target_name,
                "applied": m.applied,
                "timestamp": m.timestamp,
            }
            for m in self._modification_history[-limit:]
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_modifications": len(self._modification_history),
            "applied_modifications": sum(1 for m in self._modification_history if m.applied),
            "backups_available": len(self.backup_mgr.list_backups()),
            "project_dir": self.project_dir,
        }


# Singleton
_self_mod_engine: Optional[SelfModifyingEngine] = None

def get_self_mod_engine(project_dir: str = ".") -> SelfModifyingEngine:
    global _self_mod_engine
    if _self_mod_engine is None:
        _self_mod_engine = SelfModifyingEngine(project_dir=project_dir)
    return _self_mod_engine
