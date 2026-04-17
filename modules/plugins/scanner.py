"""
LADA Plugin Security Scanner

Scans plugins at install-time for security issues.

Features:
- Static code analysis
- Dangerous pattern detection
- Import analysis
- Capability verification
"""

import os
import re
import ast
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from modules.plugins.trust import RiskLevel

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ScanSeverity(str, Enum):
    """Severity of scan findings."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ScanCategory(str, Enum):
    """Category of scan finding."""
    DANGEROUS_IMPORT = "dangerous_import"
    DANGEROUS_CALL = "dangerous_call"
    NETWORK_ACCESS = "network_access"
    FILE_SYSTEM = "file_system"
    PROCESS_SPAWN = "process_spawn"
    CODE_EXECUTION = "code_execution"
    CREDENTIAL_ACCESS = "credential_access"
    OBFUSCATION = "obfuscation"
    PERMISSION_MISMATCH = "permission_mismatch"
    UNSAFE_PATTERN = "unsafe_pattern"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ScanFinding:
    """
    A single security finding.
    """
    finding_id: str
    category: ScanCategory
    severity: ScanSeverity
    message: str
    
    # Location
    file_path: str = ""
    line_number: int = 0
    code_snippet: str = ""
    
    # Context
    pattern_matched: str = ""
    recommendation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "pattern_matched": self.pattern_matched,
            "recommendation": self.recommendation,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScanFinding":
        return cls(
            finding_id=data["finding_id"],
            category=ScanCategory(data["category"]),
            severity=ScanSeverity(data["severity"]),
            message=data["message"],
            file_path=data.get("file_path", ""),
            line_number=data.get("line_number", 0),
            code_snippet=data.get("code_snippet", ""),
            pattern_matched=data.get("pattern_matched", ""),
            recommendation=data.get("recommendation", ""),
        )


@dataclass
class ScanResult:
    """
    Complete scan result for a plugin.
    """
    plugin_id: str
    passed: bool
    risk_level: RiskLevel
    
    # Findings
    findings: List[ScanFinding] = field(default_factory=list)
    
    # Stats
    files_scanned: int = 0
    lines_scanned: int = 0
    scan_duration_ms: int = 0
    
    # Metadata
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat())
    scanner_version: str = "1.0"
    
    @property
    def critical_count(self) -> int:
        return len([f for f in self.findings if f.severity == ScanSeverity.CRITICAL])
    
    @property
    def error_count(self) -> int:
        return len([f for f in self.findings if f.severity == ScanSeverity.ERROR])
    
    @property
    def warning_count(self) -> int:
        return len([f for f in self.findings if f.severity == ScanSeverity.WARNING])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "passed": self.passed,
            "risk_level": self.risk_level.value,
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "lines_scanned": self.lines_scanned,
            "scan_duration_ms": self.scan_duration_ms,
            "scanned_at": self.scanned_at,
            "scanner_version": self.scanner_version,
            "summary": {
                "critical": self.critical_count,
                "error": self.error_count,
                "warning": self.warning_count,
            },
        }


# ============================================================================
# Dangerous Patterns
# ============================================================================

# Dangerous imports
DANGEROUS_IMPORTS = {
    "os": ("file_system", ScanSeverity.WARNING, "OS module allows file system and process operations"),
    "subprocess": ("process_spawn", ScanSeverity.ERROR, "subprocess allows arbitrary command execution"),
    "ctypes": ("code_execution", ScanSeverity.ERROR, "ctypes allows native code execution"),
    "socket": ("network_access", ScanSeverity.WARNING, "socket allows network connections"),
    "requests": ("network_access", ScanSeverity.WARNING, "requests allows HTTP operations"),
    "urllib": ("network_access", ScanSeverity.WARNING, "urllib allows HTTP operations"),
    "httpx": ("network_access", ScanSeverity.WARNING, "httpx allows HTTP operations"),
    "aiohttp": ("network_access", ScanSeverity.WARNING, "aiohttp allows async HTTP operations"),
    "paramiko": ("network_access", ScanSeverity.ERROR, "paramiko allows SSH connections"),
    "pyautogui": ("code_execution", ScanSeverity.WARNING, "pyautogui can control mouse/keyboard"),
    "keyboard": ("code_execution", ScanSeverity.WARNING, "keyboard module can monitor keystrokes"),
    "win32api": ("code_execution", ScanSeverity.ERROR, "win32api allows Windows API calls"),
    "winreg": ("credential_access", ScanSeverity.ERROR, "winreg allows registry access"),
    "keyring": ("credential_access", ScanSeverity.ERROR, "keyring accesses system credentials"),
    "pickle": ("code_execution", ScanSeverity.ERROR, "pickle can execute arbitrary code on deserialization"),
    "marshal": ("code_execution", ScanSeverity.ERROR, "marshal can execute arbitrary code"),
    "importlib": ("code_execution", ScanSeverity.WARNING, "importlib allows dynamic imports"),
}

# Dangerous function calls
DANGEROUS_CALLS = {
    "eval": ("code_execution", ScanSeverity.CRITICAL, "eval executes arbitrary Python code"),
    "exec": ("code_execution", ScanSeverity.CRITICAL, "exec executes arbitrary Python code"),
    "compile": ("code_execution", ScanSeverity.ERROR, "compile can create executable code objects"),
    "os.system": ("process_spawn", ScanSeverity.CRITICAL, "os.system executes shell commands"),
    "os.popen": ("process_spawn", ScanSeverity.CRITICAL, "os.popen executes shell commands"),
    "os.execl": ("process_spawn", ScanSeverity.CRITICAL, "os.exec* replaces current process"),
    "os.execv": ("process_spawn", ScanSeverity.CRITICAL, "os.exec* replaces current process"),
    "os.spawn": ("process_spawn", ScanSeverity.CRITICAL, "os.spawn* starts new processes"),
    "subprocess.call": ("process_spawn", ScanSeverity.ERROR, "subprocess.call executes commands"),
    "subprocess.run": ("process_spawn", ScanSeverity.ERROR, "subprocess.run executes commands"),
    "subprocess.Popen": ("process_spawn", ScanSeverity.ERROR, "subprocess.Popen executes commands"),
    "__import__": ("code_execution", ScanSeverity.WARNING, "__import__ allows dynamic imports"),
    "getattr": ("code_execution", ScanSeverity.INFO, "getattr can access arbitrary attributes"),
    "setattr": ("code_execution", ScanSeverity.INFO, "setattr can modify arbitrary attributes"),
    "delattr": ("code_execution", ScanSeverity.INFO, "delattr can delete arbitrary attributes"),
}

# Regex patterns for suspicious code
SUSPICIOUS_PATTERNS = [
    # Obfuscation
    (r"\\x[0-9a-fA-F]{2}", "obfuscation", ScanSeverity.WARNING, "Hex-encoded strings may indicate obfuscation"),
    (r"base64\.(b64)?decode", "obfuscation", ScanSeverity.WARNING, "Base64 decoding may hide malicious content"),
    (r"codecs\.decode", "obfuscation", ScanSeverity.WARNING, "Codec decoding may hide malicious content"),
    (r"zlib\.decompress", "obfuscation", ScanSeverity.WARNING, "Decompression may hide malicious content"),
    
    # Credentials
    (r"password\s*=\s*['\"]", "credential_access", ScanSeverity.ERROR, "Hardcoded password detected"),
    (r"api_key\s*=\s*['\"]", "credential_access", ScanSeverity.ERROR, "Hardcoded API key detected"),
    (r"secret\s*=\s*['\"]", "credential_access", ScanSeverity.ERROR, "Hardcoded secret detected"),
    (r"token\s*=\s*['\"]", "credential_access", ScanSeverity.WARNING, "Possible hardcoded token"),
    
    # File operations
    (r"open\([^)]*['\"][wa]", "file_system", ScanSeverity.WARNING, "File write operation detected"),
    (r"shutil\.rmtree", "file_system", ScanSeverity.ERROR, "Recursive directory deletion detected"),
    (r"os\.remove", "file_system", ScanSeverity.WARNING, "File deletion detected"),
    (r"os\.unlink", "file_system", ScanSeverity.WARNING, "File deletion detected"),
    
    # Network
    (r"socket\.socket\(", "network_access", ScanSeverity.WARNING, "Raw socket creation detected"),
    (r"\.connect\([^)]+\d+\.\d+\.\d+\.\d+", "network_access", ScanSeverity.WARNING, "Hardcoded IP connection"),
]


# ============================================================================
# Scanner
# ============================================================================

class PluginScanner:
    """
    Security scanner for plugins.
    
    Features:
    - AST-based import analysis
    - Pattern-based code scanning
    - Risk assessment
    """
    
    def __init__(
        self,
        plugins_dir: Optional[str] = None,
        reports_dir: Optional[str] = None,
    ):
        self._plugins_dir = Path(plugins_dir or os.getenv("LADA_PLUGINS_DIR", "plugins"))
        self._reports_dir = Path(reports_dir or os.getenv("LADA_SCAN_REPORTS_DIR", "data/scan_reports"))
        
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        
        self._finding_counter = 0
        self._lock = threading.Lock()
        
        logger.info("[PluginScanner] Initialized")
    
    def scan(
        self,
        plugin_id: str,
        plugin_path: Optional[str] = None,
        declared_permissions: Optional[List[str]] = None,
    ) -> ScanResult:
        """
        Scan a plugin for security issues.
        
        Args:
            plugin_id: Plugin identifier
            plugin_path: Path to plugin directory (defaults to plugins_dir/plugin_id)
            declared_permissions: Permissions the plugin claims to need
        
        Returns:
            ScanResult with findings and risk assessment
        """
        import time
        start_time = time.time()
        
        plugin_dir = Path(plugin_path) if plugin_path else self._plugins_dir / plugin_id
        
        if not plugin_dir.exists():
            return ScanResult(
                plugin_id=plugin_id,
                passed=False,
                risk_level=RiskLevel.CRITICAL,
                findings=[
                    ScanFinding(
                        finding_id=self._next_finding_id(),
                        category=ScanCategory.UNSAFE_PATTERN,
                        severity=ScanSeverity.CRITICAL,
                        message=f"Plugin directory not found: {plugin_dir}",
                    )
                ],
            )
        
        findings: List[ScanFinding] = []
        files_scanned = 0
        lines_scanned = 0
        
        # Scan all Python files
        for py_file in plugin_dir.rglob("*.py"):
            file_findings, line_count = self._scan_file(py_file, plugin_dir)
            findings.extend(file_findings)
            files_scanned += 1
            lines_scanned += line_count
        
        # Check permission mismatches
        if declared_permissions:
            findings.extend(self._check_permission_mismatches(findings, declared_permissions))
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(findings)
        
        # Determine pass/fail
        passed = not any(f.severity in (ScanSeverity.CRITICAL, ScanSeverity.ERROR) for f in findings)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        result = ScanResult(
            plugin_id=plugin_id,
            passed=passed,
            risk_level=risk_level,
            findings=findings,
            files_scanned=files_scanned,
            lines_scanned=lines_scanned,
            scan_duration_ms=duration_ms,
        )
        
        # Save report
        self._save_report(result)
        
        logger.info(
            f"[PluginScanner] Scanned {plugin_id}: "
            f"{len(findings)} findings, risk={risk_level.value}, passed={passed}"
        )
        
        return result
    
    def _scan_file(
        self,
        file_path: Path,
        plugin_root: Path,
    ) -> Tuple[List[ScanFinding], int]:
        """Scan a single Python file."""
        findings: List[ScanFinding] = []
        
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            findings.append(ScanFinding(
                finding_id=self._next_finding_id(),
                category=ScanCategory.UNSAFE_PATTERN,
                severity=ScanSeverity.ERROR,
                message=f"Failed to read file: {e}",
                file_path=str(file_path.relative_to(plugin_root)),
            ))
            return findings, 0
        
        lines = content.split('\n')
        line_count = len(lines)
        rel_path = str(file_path.relative_to(plugin_root))
        
        # AST-based analysis
        try:
            tree = ast.parse(content)
            findings.extend(self._analyze_ast(tree, rel_path, lines))
        except SyntaxError as e:
            findings.append(ScanFinding(
                finding_id=self._next_finding_id(),
                category=ScanCategory.UNSAFE_PATTERN,
                severity=ScanSeverity.WARNING,
                message=f"Syntax error in file: {e.msg}",
                file_path=rel_path,
                line_number=e.lineno or 0,
            ))
        
        # Pattern-based analysis
        findings.extend(self._scan_patterns(content, rel_path, lines))
        
        return findings, line_count
    
    def _analyze_ast(
        self,
        tree: ast.AST,
        file_path: str,
        lines: List[str],
    ) -> List[ScanFinding]:
        """Analyze AST for dangerous constructs."""
        findings: List[ScanFinding] = []
        
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module in DANGEROUS_IMPORTS:
                        cat, sev, msg = DANGEROUS_IMPORTS[module]
                        findings.append(ScanFinding(
                            finding_id=self._next_finding_id(),
                            category=ScanCategory(cat),
                            severity=sev,
                            message=msg,
                            file_path=file_path,
                            line_number=node.lineno,
                            code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                            pattern_matched=f"import {module}",
                        ))
            
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split('.')[0]
                if module in DANGEROUS_IMPORTS:
                    cat, sev, msg = DANGEROUS_IMPORTS[module]
                    findings.append(ScanFinding(
                        finding_id=self._next_finding_id(),
                        category=ScanCategory(cat),
                        severity=sev,
                        message=msg,
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                        pattern_matched=f"from {module} import ...",
                    ))
            
            # Check function calls
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in DANGEROUS_CALLS:
                    cat, sev, msg = DANGEROUS_CALLS[func_name]
                    findings.append(ScanFinding(
                        finding_id=self._next_finding_id(),
                        category=ScanCategory(cat),
                        severity=sev,
                        message=msg,
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                        pattern_matched=func_name,
                    ))
        
        return findings
    
    def _get_call_name(self, node: ast.Call) -> str:
        """Get the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        return ""
    
    def _scan_patterns(
        self,
        content: str,
        file_path: str,
        lines: List[str],
    ) -> List[ScanFinding]:
        """Scan content with regex patterns."""
        findings: List[ScanFinding] = []
        
        for pattern, cat, sev, msg in SUSPICIOUS_PATTERNS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(ScanFinding(
                        finding_id=self._next_finding_id(),
                        category=ScanCategory(cat),
                        severity=sev,
                        message=msg,
                        file_path=file_path,
                        line_number=i,
                        code_snippet=line.strip(),
                        pattern_matched=pattern,
                    ))
        
        return findings
    
    def _check_permission_mismatches(
        self,
        findings: List[ScanFinding],
        declared_permissions: List[str],
    ) -> List[ScanFinding]:
        """Check if findings require undeclared permissions."""
        mismatches: List[ScanFinding] = []
        
        # Map categories to required permissions
        category_permissions = {
            ScanCategory.NETWORK_ACCESS: "network",
            ScanCategory.FILE_SYSTEM: "filesystem",
            ScanCategory.PROCESS_SPAWN: "process",
            ScanCategory.CREDENTIAL_ACCESS: "credentials",
        }
        
        detected_needs = set()
        for finding in findings:
            if finding.category in category_permissions:
                detected_needs.add(category_permissions[finding.category])
        
        declared_set = set(declared_permissions)
        undeclared = detected_needs - declared_set
        
        for perm in undeclared:
            mismatches.append(ScanFinding(
                finding_id=self._next_finding_id(),
                category=ScanCategory.PERMISSION_MISMATCH,
                severity=ScanSeverity.ERROR,
                message=f"Plugin uses '{perm}' capability but did not declare it",
                recommendation=f"Add '{perm}' to plugin manifest permissions",
            ))
        
        return mismatches
    
    def _calculate_risk_level(self, findings: List[ScanFinding]) -> RiskLevel:
        """Calculate overall risk level from findings."""
        if any(f.severity == ScanSeverity.CRITICAL for f in findings):
            return RiskLevel.CRITICAL
        
        error_count = len([f for f in findings if f.severity == ScanSeverity.ERROR])
        if error_count >= 3:
            return RiskLevel.CRITICAL
        elif error_count >= 1:
            return RiskLevel.HIGH
        
        warning_count = len([f for f in findings if f.severity == ScanSeverity.WARNING])
        if warning_count >= 5:
            return RiskLevel.HIGH
        elif warning_count >= 2:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def _next_finding_id(self) -> str:
        """Generate next finding ID."""
        with self._lock:
            self._finding_counter += 1
            return f"SCAN-{self._finding_counter:05d}"
    
    def _save_report(self, result: ScanResult):
        """Save scan report to disk."""
        report_file = self._reports_dir / f"{result.plugin_id}.json"
        try:
            with open(report_file, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[PluginScanner] Failed to save report: {e}")
    
    def get_report(self, plugin_id: str) -> Optional[ScanResult]:
        """Get saved scan report for a plugin."""
        report_file = self._reports_dir / f"{plugin_id}.json"
        if report_file.exists():
            try:
                with open(report_file, 'r') as f:
                    data = json.load(f)
                return ScanResult(
                    plugin_id=data["plugin_id"],
                    passed=data["passed"],
                    risk_level=RiskLevel(data["risk_level"]),
                    findings=[ScanFinding.from_dict(f) for f in data.get("findings", [])],
                    files_scanned=data.get("files_scanned", 0),
                    lines_scanned=data.get("lines_scanned", 0),
                    scan_duration_ms=data.get("scan_duration_ms", 0),
                    scanned_at=data.get("scanned_at", ""),
                    scanner_version=data.get("scanner_version", "1.0"),
                )
            except Exception as e:
                logger.warning(f"[PluginScanner] Failed to load report: {e}")
        return None
    
    def get_scan_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent scan history across all plugins.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of scan result summaries
        """
        history = []
        try:
            # Read all JSON files in reports directory
            report_files = list(self._reports_dir.glob("*.json"))
            
            # Sort by modification time (newest first)
            report_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            for report_file in report_files[:limit]:
                try:
                    with open(report_file, 'r') as f:
                        data = json.load(f)
                    history.append({
                        "plugin_id": data.get("plugin_id", report_file.stem),
                        "passed": data.get("passed", False),
                        "risk_level": data.get("risk_level", "unknown"),
                        "findings_count": len(data.get("findings", [])),
                        "scanned_at": data.get("scanned_at", ""),
                    })
                except Exception as e:
                    logger.debug(f"[PluginScanner] Skipping report {report_file}: {e}")
        except Exception as e:
            logger.warning(f"[PluginScanner] Failed to get scan history: {e}")
        
        return history


# ============================================================================
# Singleton
# ============================================================================

_scanner_instance: Optional[PluginScanner] = None
_scanner_lock = threading.Lock()


def get_scanner() -> PluginScanner:
    """Get singleton PluginScanner instance."""
    global _scanner_instance
    if _scanner_instance is None:
        with _scanner_lock:
            if _scanner_instance is None:
                _scanner_instance = PluginScanner()
    return _scanner_instance


# Alias for API compatibility
get_plugin_scanner = get_scanner
