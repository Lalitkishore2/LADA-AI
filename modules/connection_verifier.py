"""
LADA Connection Verifier

Tests all module imports, orchestration wiring, provider status,
and data directories. Used by `python main.py verify`.

Usage:
    from modules.connection_verifier import verify_all
    verify_all()
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

_pass = 0
_fail = 0
_warn = 0


def _ok(msg):
    global _pass
    _pass += 1
    print(f"  [OK]   {msg}")


def _fail_msg(msg):
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}")


def _warn_msg(msg):
    global _warn
    _warn += 1
    print(f"  [WARN] {msg}")


def _header(title):
    print()
    print(f"{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def verify_core_modules():
    """Test core third-party and LADA module imports."""
    _header("Core Module Imports")

    third_party = [
        ("requests", "HTTP Client"),
        ("dotenv", "Environment Loader"),
        ("psutil", "System Monitor"),
        ("fastapi", "API Framework"),
        ("uvicorn", "ASGI Server"),
    ]

    for mod, desc in third_party:
        try:
            __import__(mod)
            _ok(f"{desc} ({mod})")
        except ImportError:
            _fail_msg(f"{desc} ({mod})")

    print()

    lada_modules = [
        ("lada_ai_router", "HybridAIRouter", "AI Router"),
        ("lada_jarvis_core", "JarvisCommandProcessor", "Command Processor"),
        ("lada_memory", "MemorySystem", "Memory System"),
        ("modules.api_server", "LADAAPIServer", "API Server"),
        ("modules.rate_limiter", None, "Rate Limiter"),
        ("modules.model_registry", None, "Model Registry"),
        ("modules.token_counter", None, "Token Counter"),
        ("modules.providers.provider_manager", None, "Provider Manager"),
        ("modules.web_search", None, "Web Search"),
        ("modules.voice_nlu", None, "Voice NLU"),
        ("modules.error_types", None, "Error Types"),
        ("modules.context_manager", None, "Context Manager"),
        ("modules.tool_registry", None, "Tool Registry"),
        ("modules.plugin_marketplace", None, "Plugin Marketplace"),
    ]

    for entry in lada_modules:
        mod_path, cls_name, desc = entry
        try:
            mod = __import__(mod_path, fromlist=[cls_name or mod_path.split(".")[-1]])
            if cls_name:
                getattr(mod, cls_name)
            _ok(desc)
        except (ImportError, AttributeError) as e:
            _fail_msg(f"{desc}: {e}")
        except Exception as e:
            _warn_msg(f"{desc}: {type(e).__name__}: {e}")


def verify_orchestration_modules():
    """Test orchestration layer: planner, workflow, tasks, skills."""
    _header("Orchestration Modules")

    modules = [
        ("modules.advanced_planner", "AdvancedPlanner", "Advanced Planner"),
        ("modules.workflow_engine", "WorkflowEngine", "Workflow Engine"),
        ("modules.task_automation", "TaskChoreographer", "Task Choreographer"),
        ("modules.skill_generator", "SkillGenerator", "Skill Generator"),
    ]

    for mod_path, cls_name, desc in modules:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            _ok(f"{desc} ({cls_name})")
        except (ImportError, AttributeError) as e:
            _fail_msg(f"{desc}: {e}")
        except Exception as e:
            _warn_msg(f"{desc}: {type(e).__name__}: {e}")


def verify_providers():
    """Check which AI providers have API keys configured."""
    _header("Provider Configuration")

    providers = {
        "Gemini": "GEMINI_API_KEY",
        "Groq": "GROQ_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "Mistral": "MISTRAL_API_KEY",
        "xAI": "XAI_API_KEY",
        "DeepSeek": "DEEPSEEK_API_KEY",
        "Together": "TOGETHER_API_KEY",
        "Fireworks": "FIREWORKS_API_KEY",
        "Cerebras": "CEREBRAS_API_KEY",
        "Ollama": "LOCAL_OLLAMA_URL",
    }

    configured = 0
    for name, env_key in providers.items():
        val = os.getenv(env_key, "")
        if val:
            _ok(f"{name} ({env_key})")
            configured += 1
        else:
            _warn_msg(f"{name} — {env_key} not set")

    if configured == 0:
        print()
        _fail_msg("No AI providers configured! Set at least one API key in .env")
        print("  Minimum: GEMINI_API_KEY (free from https://aistudio.google.com/apikey)")
    else:
        print(f"\n  {configured}/{len(providers)} providers configured")


def verify_data_directories():
    """Check that required data directories exist."""
    _header("Data Directories")

    dirs = [
        "data",
        "data/conversations",
        "data/sessions",
        "data/rag_knowledge",
        "logs",
        "plugins",
    ]

    for d in dirs:
        path = PROJECT_ROOT / d
        if path.exists():
            _ok(d)
        else:
            _warn_msg(f"{d} — missing (will be created on first run)")


def verify_api_server():
    """Test that the API server can be instantiated."""
    _header("API Server Instantiation")

    try:
        from modules.api_server import LADAAPIServer
        server = LADAAPIServer()
        _ok("LADAAPIServer created successfully")
        _ok(f"Routes registered: {len(server.app.routes)} endpoints")
    except Exception as e:
        _fail_msg(f"API Server creation failed: {e}")


def verify_all():
    """Run all verification checks and print summary."""
    global _pass, _fail, _warn
    _pass = _fail = _warn = 0

    # Ensure project root is in path
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    print()
    print("  LADA Connection Verifier")
    print("  Testing all module imports, connections, and configuration")

    verify_core_modules()
    verify_orchestration_modules()
    verify_providers()
    verify_data_directories()
    verify_api_server()

    _header("Summary")
    print()
    print(f"  Results: {_pass} passed, {_fail} failed, {_warn} warnings")
    print()

    if _fail == 0:
        print("  All checks passed! LADA is ready to run.")
    else:
        print(f"  {_fail} issue(s) found. Review the output above.")

    print()
    return _fail == 0
