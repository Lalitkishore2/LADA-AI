"""
LADA One-Click Installer

Sets up everything needed to run LADA on a fresh machine.

Usage:
    python setup_lada.py              # Full install
    python setup_lada.py --minimal    # Core packages only (no voice/GUI)
    python setup_lada.py --verify     # Verify existing installation
    python setup_lada.py --help       # Show help

Steps performed:
    1. Check Python version (3.11+ required)
    2. Create virtual environment (jarvis_env/) if not present
    3. Upgrade pip
    4. Install dependencies from requirements.txt
    5. Copy .env.example -> .env (if .env missing)
    6. Create data directories
    7. Download NLP models (spaCy)
    8. Verify core module imports
    9. Print next steps
"""

import subprocess
import sys
import os
import shutil
import platform
from pathlib import Path

# ─── Constants ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / "jarvis_env"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"
MIN_PYTHON = (3, 11)

DATA_DIRS = [
    "data",
    "data/conversations",
    "data/sessions",
    "data/rag_knowledge",
    "data/patterns",
    "data/permissions",
    "data/routines",
    "data/tab_sessions",
    "logs",
    "plugins",
]

# Minimal set for headless / text-only operation
MINIMAL_PACKAGES = [
    "python-dotenv",
    "requests",
    "psutil",
    "google-generativeai",
    "fastapi",
    "uvicorn[standard]",
]

# Core modules to verify after install
VERIFY_MODULES = [
    ("requests", "HTTP client"),
    ("dotenv", "Environment loader"),
    ("psutil", "System monitoring"),
    ("fastapi", "API framework"),
    ("uvicorn", "ASGI server"),
]

VERIFY_LADA_MODULES = [
    ("lada_ai_router", "HybridAIRouter", "AI Router"),
    ("lada_jarvis_core", "JarvisCommandProcessor", "Command Processor"),
    ("lada_memory", "MemorySystem", "Memory"),
    ("modules.api_server", "LADAAPIServer", "API Server"),
    ("modules.rate_limiter", None, "Rate Limiter"),
    ("modules.model_registry", None, "Model Registry"),
    ("modules.token_counter", None, "Token Counter"),
    ("modules.providers.provider_manager", None, "Provider Manager"),
    ("modules.advanced_planner", None, "Advanced Planner"),
    ("modules.workflow_engine", None, "Workflow Engine"),
    ("modules.task_automation", None, "Task Automation"),
    ("modules.plugin_marketplace", None, "Plugin Marketplace"),
    ("modules.tool_registry", None, "Tool Registry"),
    ("modules.context_manager", None, "Context Manager"),
    ("modules.error_types", None, "Error Types"),
    ("modules.web_search", None, "Web Search"),
    ("modules.voice_nlu", None, "Voice NLU"),
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

_pass = 0
_fail = 0
_warn = 0


def ok(msg):
    global _pass
    _pass += 1
    print(f"  [OK]   {msg}")


def fail(msg):
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}")


def warn(msg):
    global _warn
    _warn += 1
    print(f"  [WARN] {msg}")


def info(msg):
    print(f"  [INFO] {msg}")


def header(title):
    print()
    print(f"{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def run_cmd(args, desc=None, check=True, capture=False):
    """Run a subprocess command."""
    if desc:
        info(desc)
    try:
        result = subprocess.run(
            args,
            check=check,
            capture_output=capture,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture and e.stderr:
            fail(f"{desc or args[0]}: {e.stderr.strip()[:200]}")
        else:
            fail(f"{desc or args[0]} failed (exit code {e.returncode})")
        return None
    except FileNotFoundError:
        fail(f"Command not found: {args[0]}")
        return None


def get_pip():
    """Return path to pip in venv or system."""
    if VENV_DIR.exists():
        pip = VENV_DIR / "Scripts" / "pip.exe"
        if pip.exists():
            return str(pip)
    return [sys.executable, "-m", "pip"]


def get_python():
    """Return path to python in venv or system."""
    if VENV_DIR.exists():
        py = VENV_DIR / "Scripts" / "python.exe"
        if py.exists():
            return str(py)
    return sys.executable


# ─── Setup Steps ─────────────────────────────────────────────────────────────

def check_python_version():
    """Step 1: Verify Python version."""
    header("Step 1: Python Version Check")
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        ok(f"Python {version_str} (>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required)")
        return True
    else:
        fail(f"Python {version_str} is too old. Need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+")
        print()
        print("  Download Python 3.11+: https://www.python.org/downloads/")
        return False


def check_platform():
    """Check OS platform."""
    p = platform.system()
    if p == "Windows":
        ok(f"Platform: {p} {platform.release()}")
    else:
        warn(f"Platform: {p} (LADA is optimized for Windows, some features may not work)")


def create_venv():
    """Step 2: Create virtual environment."""
    header("Step 2: Virtual Environment")
    if VENV_DIR.exists():
        py = VENV_DIR / "Scripts" / "python.exe"
        if py.exists():
            ok(f"Virtual environment exists: {VENV_DIR.name}/")
            return True
        else:
            warn("Venv directory exists but Python not found, recreating...")
            shutil.rmtree(VENV_DIR, ignore_errors=True)

    info(f"Creating virtual environment in {VENV_DIR.name}/...")
    result = run_cmd(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        desc="Creating venv",
        capture=True,
    )
    if result and result.returncode == 0:
        ok("Virtual environment created")
        return True
    else:
        fail("Could not create virtual environment")
        return False


def upgrade_pip():
    """Upgrade pip in venv."""
    py = get_python()
    args = [py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"] if isinstance(py, str) else py + ["-m", "pip", "install", "--upgrade", "pip", "--quiet"]
    if isinstance(py, str):
        run_cmd([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
                desc="Upgrading pip", check=False, capture=True)
    else:
        run_cmd(py + ["install", "--upgrade", "pip", "--quiet"],
                desc="Upgrading pip", check=False, capture=True)


def install_dependencies(minimal=False):
    """Step 3: Install dependencies."""
    header("Step 3: Install Dependencies")
    py = get_python()

    if minimal:
        info(f"Installing {len(MINIMAL_PACKAGES)} minimal packages...")
        for pkg in MINIMAL_PACKAGES:
            if isinstance(py, str):
                result = run_cmd(
                    [py, "-m", "pip", "install", pkg, "--quiet"],
                    check=False, capture=True,
                )
            else:
                result = run_cmd(
                    [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                    check=False, capture=True,
                )
            if result and result.returncode == 0:
                ok(f"Installed {pkg}")
            else:
                fail(f"Failed to install {pkg}")
    else:
        if not REQUIREMENTS.exists():
            fail(f"requirements.txt not found at {REQUIREMENTS}")
            return False
        info(f"Installing all dependencies from requirements.txt...")
        info("This may take several minutes on first run.")
        if isinstance(py, str):
            result = run_cmd(
                [py, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"],
                desc="pip install -r requirements.txt",
                check=False, capture=True,
            )
        else:
            result = run_cmd(
                [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"],
                desc="pip install -r requirements.txt",
                check=False, capture=True,
            )
        if result and result.returncode == 0:
            ok("All dependencies installed")
        else:
            warn("Some packages may have failed. Check output above.")

    return True


def setup_env_file():
    """Step 4: Copy .env.example to .env if needed."""
    header("Step 4: Environment Configuration")
    if ENV_FILE.exists():
        ok(".env file exists")
        return True

    if ENV_EXAMPLE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        ok(f"Created .env from .env.example")
        print()
        print("  IMPORTANT: Edit .env to add your API keys.")
        print("  Minimum: set GEMINI_API_KEY for free AI access.")
        print("  Get a key: https://aistudio.google.com/apikey")
        print()

        # Prompt for Gemini key
        try:
            key = input("  Enter your Gemini API key (or press Enter to skip): ").strip()
            if key:
                content = ENV_FILE.read_text(encoding="utf-8")
                content = content.replace("GEMINI_API_KEY=", f"GEMINI_API_KEY={key}", 1)
                ENV_FILE.write_text(content, encoding="utf-8")
                ok(f"Gemini API key saved to .env")
        except (EOFError, KeyboardInterrupt):
            info("Skipped API key entry")

        return True
    else:
        warn(".env.example not found, creating minimal .env")
        ENV_FILE.write_text(
            "# LADA Configuration\n"
            "# Add at least one AI provider key\n"
            "GEMINI_API_KEY=\n"
            "LOCAL_OLLAMA_URL=http://localhost:11434\n",
            encoding="utf-8",
        )
        return True


def create_directories():
    """Step 5: Create data directories."""
    header("Step 5: Data Directories")
    created = 0
    for d in DATA_DIRS:
        path = PROJECT_ROOT / d
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created += 1
    if created > 0:
        ok(f"Created {created} directories")
    else:
        ok("All directories exist")


def download_nlp_models():
    """Step 6: Download NLP models."""
    header("Step 6: NLP Models")
    py = get_python()
    python = py if isinstance(py, str) else sys.executable

    # spaCy
    try:
        result = run_cmd(
            [python, "-m", "spacy", "download", "en_core_web_sm", "--quiet"],
            desc="Downloading spaCy English model",
            check=False, capture=True,
        )
        if result and result.returncode == 0:
            ok("spaCy en_core_web_sm downloaded")
        else:
            warn("spaCy model download failed (optional, voice NLU may be limited)")
    except Exception:
        warn("spaCy not available (optional)")


def verify_installation():
    """Step 7: Verify core imports."""
    header("Step 7: Verify Installation")

    # Add project root to path so LADA modules can be imported
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Third-party modules
    info("Checking third-party packages...")
    for mod_name, desc in VERIFY_MODULES:
        try:
            __import__(mod_name)
            ok(f"{desc} ({mod_name})")
        except ImportError:
            fail(f"{desc} ({mod_name})")

    # LADA modules
    print()
    info("Checking LADA modules...")
    for mod_path, cls_name, desc in VERIFY_LADA_MODULES:
        try:
            mod = __import__(mod_path, fromlist=[cls_name] if cls_name else [mod_path.split(".")[-1]])
            if cls_name:
                getattr(mod, cls_name)
            ok(f"{desc}")
        except (ImportError, AttributeError) as e:
            fail(f"{desc}: {e}")
        except Exception as e:
            warn(f"{desc}: {type(e).__name__}: {e}")


def check_ollama():
    """Optional: Check if Ollama is installed and offer to pull models."""
    header("Step 8: Local AI (Optional)")
    result = run_cmd(
        ["ollama", "version"],
        check=False, capture=True,
    )
    if result and result.returncode == 0:
        ok(f"Ollama installed: {result.stdout.strip()}")
        try:
            answer = input("  Pull recommended local models? (qwen2.5:7b + llama3.1:8b) [y/N]: ").strip().lower()
            if answer == "y":
                for model in ["qwen2.5:7b-instruct-q4_K_M", "llama3.1:8b-instruct-q4_K_M"]:
                    info(f"Pulling {model}...")
                    run_cmd(["ollama", "pull", model], check=False)
        except (EOFError, KeyboardInterrupt):
            info("Skipped model download")
    else:
        info("Ollama not installed (optional, for offline local AI)")
        info("Install from: https://ollama.com/download")


def print_summary():
    """Print final summary and next steps."""
    header("Setup Complete")
    print()
    print(f"  Results: {_pass} passed, {_fail} failed, {_warn} warnings")
    print()

    if _fail == 0:
        print("  LADA is ready to run!")
    else:
        print(f"  {_fail} issue(s) detected. Check the output above.")
    print()
    print("  ── How to Run LADA ──")
    print()
    if (VENV_DIR / "Scripts" / "python.exe").exists():
        py_cmd = f".\\jarvis_env\\Scripts\\python.exe"
    else:
        py_cmd = "python"
    print(f"  Web UI (recommended):  {py_cmd} main.py webui")
    print(f"  Desktop GUI:           {py_cmd} main.py gui")
    print(f"  Text mode:             {py_cmd} main.py text")
    print(f"  Voice mode:            {py_cmd} main.py voice")
    print(f"  Verify installation:   {py_cmd} main.py verify")
    print()
    print("  Or double-click:")
    print("    LADA-WebUI.bat   (browser)")
    print("    LADA-GUI.bat     (desktop)")
    print()
    if not ENV_FILE.exists() or ENV_FILE.read_text(encoding="utf-8").count("=") < 3:
        print("  IMPORTANT: Edit .env to add your AI API key(s).")
        print("  Minimum: GEMINI_API_KEY (free from https://aistudio.google.com/apikey)")
        print()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print()
    print("  LADA - Language Agnostic Digital Assistant")
    print("  One-Click Installer")
    print()

    # Parse args
    args = sys.argv[1:]
    minimal = "--minimal" in args
    verify_only = "--verify" in args

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    if verify_only:
        check_python_version()
        check_platform()
        verify_installation()
        print_summary()
        return

    # Full install flow
    if not check_python_version():
        return

    check_platform()
    create_venv()
    upgrade_pip()
    install_dependencies(minimal=minimal)
    setup_env_file()
    create_directories()

    if not minimal:
        download_nlp_models()

    verify_installation()
    check_ollama()
    print_summary()


if __name__ == "__main__":
    main()
