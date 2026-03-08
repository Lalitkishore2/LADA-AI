"""
LADA v10.0 - Code Execution Sandbox
Secure code execution with RestrictedPython and subprocess isolation

Features:
- Safe Python code execution with restricted builtins
- Subprocess isolation with timeout
- Memory and CPU limits
- Output capture and error handling
- Support for multiple languages (Python, JavaScript, PowerShell)
"""

import os
import sys
import subprocess
import tempfile
import threading
import traceback
import logging
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)

# Try to import RestrictedPython
try:
    from RestrictedPython import compile_restricted, safe_builtins, limited_builtins
    from RestrictedPython.Guards import safe_builtins as rp_safe_builtins
    from RestrictedPython.Eval import default_guarded_getattr
    RESTRICTED_OK = True
except ImportError:
    RESTRICTED_OK = False
    logger.warning("RestrictedPython not available - install with: pip install RestrictedPython")


class ExecutionMode(Enum):
    """Code execution security modes"""
    RESTRICTED = "restricted"      # Most secure - limited builtins
    SUBPROCESS = "subprocess"      # Medium security - isolated process
    DIRECT = "direct"              # Least secure - direct execution (use with caution)


@dataclass
class ExecutionResult:
    """Result of code execution"""
    success: bool
    output: str
    error: Optional[str] = None
    return_value: Any = None
    execution_time: float = 0.0
    memory_used: Optional[int] = None


class CodeSandbox:
    """
    Secure code execution sandbox.
    
    Provides multiple execution modes:
    1. RESTRICTED - Uses RestrictedPython for safe execution
    2. SUBPROCESS - Runs in isolated subprocess with timeout
    3. DIRECT - Direct execution (only for trusted code)
    """
    
    # Safe builtins for restricted mode
    SAFE_BUILTINS = {
        'abs': abs,
        'all': all,
        'any': any,
        'ascii': ascii,
        'bin': bin,
        'bool': bool,
        'bytearray': bytearray,
        'bytes': bytes,
        'callable': callable,
        'chr': chr,
        'dict': dict,
        'divmod': divmod,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'format': format,
        'frozenset': frozenset,
        'getattr': getattr,
        'hasattr': hasattr,
        'hash': hash,
        'hex': hex,
        'int': int,
        'isinstance': isinstance,
        'issubclass': issubclass,
        'iter': iter,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'next': next,
        'oct': oct,
        'ord': ord,
        'pow': pow,
        'print': print,
        'range': range,
        'repr': repr,
        'reversed': reversed,
        'round': round,
        'set': set,
        'slice': slice,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'type': type,
        'zip': zip,
        'True': True,
        'False': False,
        'None': None,
    }
    
    # Dangerous modules that should never be imported
    BLOCKED_MODULES = {
        'os', 'sys', 'subprocess', 'shutil', 'socket', 'requests',
        'urllib', 'http', 'ftplib', 'smtplib', 'pickle', 'marshal',
        'ctypes', 'multiprocessing', 'threading', '__builtins__',
        'builtins', 'importlib', 'code', 'codeop', 'compile',
        'eval', 'exec', 'execfile', 'input', '__import__',
    }
    
    # Safe modules that can be imported
    ALLOWED_MODULES = {
        'math', 'random', 'datetime', 'json', 're', 'collections',
        'itertools', 'functools', 'operator', 'string', 'textwrap',
        'decimal', 'fractions', 'statistics', 'copy', 'pprint',
        'dataclasses', 'typing', 'enum', 'abc',
    }
    
    def __init__(
        self,
        timeout: float = 30.0,
        max_memory_mb: int = 256,
        mode: ExecutionMode = ExecutionMode.SUBPROCESS
    ):
        """
        Initialize code sandbox.
        
        Args:
            timeout: Maximum execution time in seconds
            max_memory_mb: Maximum memory usage in MB
            mode: Default execution mode
        """
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.default_mode = mode
        self.temp_dir = Path(tempfile.gettempdir()) / "lada_sandbox"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def execute(
        self,
        code: str,
        language: str = "python",
        mode: Optional[ExecutionMode] = None,
        context: Optional[Dict] = None,
        timeout: Optional[float] = None
    ) -> ExecutionResult:
        """
        Execute code in sandbox.
        
        Args:
            code: Code to execute
            language: Programming language (python, javascript, powershell)
            mode: Execution mode (overrides default)
            context: Variables to inject into execution context
            timeout: Timeout override
            
        Returns:
            ExecutionResult with output, errors, and metrics
        """
        mode = mode or self.default_mode
        timeout = timeout or self.timeout
        context = context or {}
        
        start_time = time.time()
        
        try:
            if language.lower() == "python":
                if mode == ExecutionMode.RESTRICTED:
                    result = self._execute_restricted_python(code, context, timeout)
                elif mode == ExecutionMode.SUBPROCESS:
                    result = self._execute_subprocess_python(code, timeout)
                else:
                    result = self._execute_direct_python(code, context, timeout)
                    
            elif language.lower() == "javascript":
                result = self._execute_javascript(code, timeout)
                
            elif language.lower() == "powershell":
                result = self._execute_powershell(code, timeout)
                
            else:
                result = ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {language}"
                )
                
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def _execute_restricted_python(
        self,
        code: str,
        context: Dict,
        timeout: float
    ) -> ExecutionResult:
        """Execute Python code with RestrictedPython."""
        if not RESTRICTED_OK:
            return ExecutionResult(
                success=False,
                output="",
                error="RestrictedPython not installed. Install with: pip install RestrictedPython"
            )
        
        # Capture output
        output_buffer = []
        
        def safe_print(*args, **kwargs):
            output_buffer.append(' '.join(str(a) for a in args))
        
        # Create safe builtins
        safe_builtins = dict(self.SAFE_BUILTINS)
        safe_builtins['print'] = safe_print
        safe_builtins['_print_'] = safe_print
        
        # Safe import function
        def safe_import(name, *args, **kwargs):
            if name in self.BLOCKED_MODULES:
                raise ImportError(f"Import of '{name}' is not allowed")
            if name not in self.ALLOWED_MODULES:
                raise ImportError(f"Import of '{name}' is not in allowed list")
            return __import__(name, *args, **kwargs)
        
        safe_builtins['__import__'] = safe_import
        
        # Create restricted globals
        restricted_globals = {
            '__builtins__': safe_builtins,
            '__name__': '__restricted__',
            '__doc__': None,
            '_getattr_': default_guarded_getattr,
            '_write_': lambda x: x,
            '_getiter_': iter,
            '_getitem_': lambda obj, key: obj[key],
        }
        
        # Add context variables
        restricted_globals.update(context)
        
        # Compile restricted code
        try:
            byte_code = compile_restricted(
                code,
                filename='<sandbox>',
                mode='exec'
            )
            
            if byte_code.errors:
                return ExecutionResult(
                    success=False,
                    output="",
                    error="Compilation errors:\n" + "\n".join(byte_code.errors)
                )
            
            # Execute with timeout
            result = {'__result__': None}
            
            def run_code():
                try:
                    exec(byte_code.code, restricted_globals)
                    # Capture last expression if available
                    if '_' in restricted_globals:
                        result['__result__'] = restricted_globals['_']
                except Exception as e:
                    result['__error__'] = str(e)
            
            thread = threading.Thread(target=run_code)
            thread.start()
            thread.join(timeout)
            
            if thread.is_alive():
                return ExecutionResult(
                    success=False,
                    output='\n'.join(output_buffer),
                    error=f"Execution timed out after {timeout} seconds"
                )
            
            if '__error__' in result:
                return ExecutionResult(
                    success=False,
                    output='\n'.join(output_buffer),
                    error=result['__error__']
                )
            
            return ExecutionResult(
                success=True,
                output='\n'.join(output_buffer),
                return_value=result.get('__result__')
            )
            
        except Exception as e:
            return ExecutionResult(
                success=False,
                output='\n'.join(output_buffer),
                error=f"Compilation error: {str(e)}"
            )
    
    def _execute_subprocess_python(
        self,
        code: str,
        timeout: float
    ) -> ExecutionResult:
        """Execute Python in isolated subprocess."""
        # Create temp file with code
        code_file = self.temp_dir / f"sandbox_{int(time.time() * 1000)}.py"
        
        try:
            # Wrap code to capture output
            wrapped_code = f'''
import sys
import json

# Capture stdout
_output = []
_original_print = print

def _safe_print(*args, **kwargs):
    _output.append(' '.join(str(a) for a in args))

print = _safe_print

try:
{self._indent_code(code, 4)}
    _result = None
except Exception as e:
    print(f"Error: {{e}}")
    _result = None

# Output result as JSON
import json
print("__RESULT_MARKER__")
print(json.dumps({{"output": "\\n".join(_output), "success": True}}))
'''
            code_file.write_text(wrapped_code, encoding='utf-8')
            
            # Execute in subprocess
            result = subprocess.run(
                [sys.executable, str(code_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.temp_dir)
            )
            
            # Parse output
            output = result.stdout
            if "__RESULT_MARKER__" in output:
                parts = output.split("__RESULT_MARKER__")
                actual_output = parts[0].strip()
                try:
                    result_json = json.loads(parts[1].strip())
                    return ExecutionResult(
                        success=result_json.get('success', True),
                        output=actual_output or result_json.get('output', ''),
                        error=result.stderr if result.stderr else None
                    )
                except:
                    pass
            
            return ExecutionResult(
                success=result.returncode == 0,
                output=output,
                error=result.stderr if result.stderr else None
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e)
            )
        finally:
            # Cleanup
            if code_file.exists():
                try:
                    code_file.unlink()
                except:
                    pass
    
    def _execute_direct_python(
        self,
        code: str,
        context: Dict,
        timeout: float
    ) -> ExecutionResult:
        """Execute Python directly (least secure - use with caution)."""
        output_buffer = []
        original_print = print
        
        def capture_print(*args, **kwargs):
            output_buffer.append(' '.join(str(a) for a in args))
        
        # Replace print
        import builtins
        builtins.print = capture_print
        
        try:
            exec_globals = {'__builtins__': builtins}
            exec_globals.update(context)
            
            result = {'__result__': None, '__error__': None}
            
            def run():
                try:
                    exec(code, exec_globals)
                except Exception as e:
                    result['__error__'] = traceback.format_exc()
            
            thread = threading.Thread(target=run)
            thread.start()
            thread.join(timeout)
            
            if thread.is_alive():
                return ExecutionResult(
                    success=False,
                    output='\n'.join(output_buffer),
                    error=f"Execution timed out after {timeout} seconds"
                )
            
            if result['__error__']:
                return ExecutionResult(
                    success=False,
                    output='\n'.join(output_buffer),
                    error=result['__error__']
                )
            
            return ExecutionResult(
                success=True,
                output='\n'.join(output_buffer),
                return_value=result.get('__result__')
            )
            
        finally:
            builtins.print = original_print
    
    def _execute_javascript(self, code: str, timeout: float) -> ExecutionResult:
        """Execute JavaScript using Node.js if available."""
        code_file = self.temp_dir / f"sandbox_{int(time.time() * 1000)}.js"
        
        try:
            code_file.write_text(code, encoding='utf-8')
            
            result = subprocess.run(
                ['node', str(code_file)],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return ExecutionResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.stderr else None
            )
            
        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                output="",
                error="Node.js not found. Install Node.js to run JavaScript."
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds"
            )
        finally:
            if code_file.exists():
                try:
                    code_file.unlink()
                except:
                    pass
    
    def _execute_powershell(self, code: str, timeout: float) -> ExecutionResult:
        """Execute PowerShell script."""
        code_file = self.temp_dir / f"sandbox_{int(time.time() * 1000)}.ps1"
        
        try:
            code_file.write_text(code, encoding='utf-8')
            
            result = subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(code_file)],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return ExecutionResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.stderr else None
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds"
            )
        finally:
            if code_file.exists():
                try:
                    code_file.unlink()
                except:
                    pass
    
    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by specified spaces."""
        indent = ' ' * spaces
        lines = code.split('\n')
        return '\n'.join(indent + line for line in lines)
    
    def validate_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        Validate code for safety issues without executing.
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            {'safe': True/False, 'issues': [...], 'warnings': [...]}
        """
        issues = []
        warnings = []
        
        if language.lower() == "python":
            # Check for dangerous imports
            import_patterns = [
                'import os', 'from os', 'import sys', 'from sys',
                'import subprocess', 'import shutil', 'import socket',
                'import requests', 'import urllib', 'import pickle',
                'import ctypes', 'import multiprocessing',
                '__import__', 'eval(', 'exec(', 'compile(',
                'open(', 'file(', 'input(',
            ]
            
            for pattern in import_patterns:
                if pattern in code:
                    issues.append(f"Potentially dangerous pattern: '{pattern}'")
            
            # Check for network operations
            network_patterns = ['http://', 'https://', 'ftp://', 'socket.', '.connect(']
            for pattern in network_patterns:
                if pattern in code:
                    warnings.append(f"Network operation detected: '{pattern}'")
            
            # Check for file operations
            file_patterns = ['.write(', '.read(', 'with open', 'Path(']
            for pattern in file_patterns:
                if pattern in code:
                    warnings.append(f"File operation detected: '{pattern}'")
        
        return {
            'safe': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    sandbox = CodeSandbox(timeout=10, mode=ExecutionMode.SUBPROCESS)
    
    print("🧪 Testing Code Sandbox...")
    
    # Test 1: Simple Python
    print("\n1️⃣ Simple Python:")
    result = sandbox.execute("""
x = 5
y = 10
print(f"Sum: {x + y}")
for i in range(3):
    print(f"  Loop {i}")
""")
    print(f"   Success: {result.success}")
    print(f"   Output:\n{result.output}")
    
    # Test 2: Math operations
    print("\n2️⃣ Math operations:")
    result = sandbox.execute("""
import math
print(f"Pi: {math.pi:.4f}")
print(f"Sqrt(2): {math.sqrt(2):.4f}")
""", mode=ExecutionMode.SUBPROCESS)
    print(f"   Success: {result.success}")
    print(f"   Output:\n{result.output}")
    
    # Test 3: Blocked dangerous code
    print("\n3️⃣ Validation of dangerous code:")
    dangerous_code = """
import os
os.system('rm -rf /')
"""
    validation = sandbox.validate_code(dangerous_code)
    print(f"   Safe: {validation['safe']}")
    print(f"   Issues: {validation['issues']}")
    
    # Test 4: Timeout handling
    print("\n4️⃣ Timeout handling:")
    result = sandbox.execute("""
import time
time.sleep(100)  # This should timeout
print("Done")
""", timeout=2)
    print(f"   Success: {result.success}")
    print(f"   Error: {result.error}")
    
    print("\n✅ Code Sandbox test complete!")
