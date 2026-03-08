# Contributing to LADA

Thanks for your interest in contributing to LADA. This guide covers the project conventions, how to set up a development environment, and how to submit changes.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Windows 10/11 (primary platform)
- Git

### Environment

```powershell
git clone <repo-url> C:\JarvisAI
cd C:\JarvisAI
python -m venv jarvis_env
.\jarvis_env\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .env.example .env   # Edit with your API keys
```

### Verify Setup

```powershell
python main.py status    # Check backend connectivity
python test_e2e_complete.py   # Run E2E validation
```

---

## Project Structure

```
lada_desktop_app.py       Main GUI application (PyQt5)
lada_ai_router.py         Multi-backend AI routing engine
lada_jarvis_core.py       Command processor + NLU routing
lada_memory.py            Persistent memory system
voice_tamil_free.py       TTS/STT engine
main.py                   CLI entry point
models.json               Model catalog (35 models, 12 providers)

modules/                   Feature modules (100+ files)
modules/agents/            Specialized task agents (7 files)
modules/messaging/         Platform connectors (11 files, 9 platforms)
modules/providers/         Protocol adapters for AI providers (5 files)
modules/model_registry.py  Config-driven model catalog (35 models, 12 providers)
modules/tool_registry.py   Structured tool system with JSON schemas
modules/error_types.py     Classified error system
modules/token_counter.py   Token counting + cost tracking
modules/session_manager.py Session isolation
modules/context_manager.py Context window management
modules/advanced_planner.py Multi-step planning with dependencies
modules/rate_limiter.py    Per-provider TokenBucket + CircuitBreaker
modules/plugin_marketplace.py Plugin marketplace (install/uninstall/update)
tests/                     Test suite (73 files)
data/                      Runtime data
web/                       Legacy web dashboard frontend
frontend/                  Next.js/TypeScript web frontend
plugins/                   Plugin directory + marketplace index
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed component documentation.

---

## Code Conventions

### Module Pattern

Every module follows this pattern:

```python
"""
Module description - what it does and why
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MyModule:
    """Class docstring explaining purpose"""

    def __init__(self):
        """Initialize with ENV configuration"""
        self.setting = os.getenv('MY_SETTING', 'default')

    def do_something(self, input: str) -> str:
        """Method docstring"""
        pass


def create_my_module() -> Optional[MyModule]:
    """Factory function for safe creation"""
    try:
        return MyModule()
    except Exception as e:
        logger.error(f"Failed to create MyModule: {e}")
        return None
```

### Import Pattern

All module imports in core files use try/except with availability flags:

```python
try:
    from modules.my_module import MyModule
    MY_MODULE_OK = True
except ImportError:
    MyModule = None
    MY_MODULE_OK = False
```

This ensures missing dependencies disable features without crashing the app.

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Import flags: `MODULE_NAME_OK` (bool)

### Configuration

- All settings read from environment variables via `os.getenv()`
- Provide sensible defaults: `os.getenv('KEY', 'default_value')`
- Document new env vars in `.env.example`

---

## Adding a New Module

1. Create `modules/my_feature.py` following the module pattern above
2. Add the try/except import to `lada_jarvis_core.py`
3. Wire up the command patterns in `JarvisCommandProcessor`
4. Add any new dependencies to `requirements.txt`
5. Add new env vars to `.env.example`
6. Write tests in `tests/test_my_feature.py`

**Phase 2 patterns:** When adding new modules, prefer these approaches where applicable:

- For AI-related modules, use the provider adapter pattern (see "Adding a New AI Provider" below)
- For tool modules, register capabilities in the ToolRegistry with JSON schema
- Use `ErrorCategory` for classified errors instead of generic exceptions

### Plugin System

For self-contained features, consider using the plugin system instead:

1. Create `plugins/my_plugin/` directory
2. Add `manifest.yaml` with metadata and capabilities
3. Add `plugin.py` with your plugin class
4. The plugin system auto-discovers and loads plugins from `plugins/`
5. Hot-reload via watchdog PluginWatcher (changes take effect immediately)

For marketplace distribution:
1. Add your plugin entry to `plugins/marketplace_index.json`
2. Users can install via `PluginMarketplace.install_plugin(plugin_id)`

---

## Adding a New AI Provider

### Legacy Approach

The original approach was to add a hardcoded backend to `lada_ai_router.py` with enum values, health checks, and query methods. This still works but is not the preferred path for new providers.

### Phase 2 Approach (Config-Driven)

The Phase 2 approach is config-driven and requires no code changes for supported protocols:

1. Add the model entry to `models.json` with: `id`, `name`, `provider`, `tier`, `context_window`, `cost_input`, `cost_output`, `base_url`
2. Add the provider entry to `models.json` providers section with: `type` (API protocol), `name`, `configKeys` (ENV var names), `local` (bool), `priority`
3. If the provider uses an existing protocol (`openai-completions`, `anthropic-messages`, `google-generative-ai`, `ollama`), no code changes are needed
4. If the provider uses a new protocol, create `modules/providers/new_protocol_provider.py` extending `BaseProvider`
5. Add the protocol to `PROTOCOL_MAP` in `modules/providers/provider_manager.py`
6. Add any new ENV keys to `.env.example`

### Provider Adapter Pattern

When implementing a new protocol adapter, extend `BaseProvider`:

```python
from modules.providers.base_provider import BaseProvider, ProviderConfig, ProviderResponse, StreamChunk

class MyProvider(BaseProvider):
    """Adapter for MyProtocol API."""

    def check_health(self) -> ProviderStatus:
        """Check if provider is reachable."""
        ...

    def complete(self, messages, model_id, temperature, max_tokens, **kwargs) -> ProviderResponse:
        """Send a completion request."""
        ...

    def stream_complete(self, messages, model_id, temperature, max_tokens, **kwargs):
        """Stream a completion request. Yields StreamChunk objects."""
        ...
```

---

## Testing

### Run Tests

```powershell
python test_e2e_complete.py      # Full E2E validation
pytest tests/                     # Unit tests
pytest tests/test_ai_router.py   # Single test file
pytest tests/test_phase2_modules.py   # Phase 2 module tests (67 tests)
pytest tests/ -v                       # All tests with verbose output
```

### Test Guidelines

- Test files go in `tests/` named `test_*.py`
- Mock external API calls (AI backends, web search)
- Test both success and failure paths
- Verify graceful degradation when modules are missing

---

## Submitting Changes

### Commit Messages

Use clear, descriptive messages:

```
Add deep research engine with multi-source synthesis

- Query decomposition into sub-queries
- Parallel search across DuckDuckGo, Wikipedia
- AI synthesis with inline citations
```

### Pull Requests

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes following the conventions above
3. Run the E2E tests: `python test_e2e_complete.py`
4. Push and open a PR with:
   - Summary of changes
   - Any new dependencies added
   - Any new env vars required
   - Test results

### What Makes a Good PR

- Focused scope -- one feature or fix per PR
- Follows existing patterns (import guards, factory functions, env config)
- Doesn't break existing features (E2E tests pass)
- New dependencies are optional where possible (conditional imports)
- Includes test coverage

---

## Areas for Contribution

### High Impact
- Additional AI backend integrations
- New AI provider protocol adapters (modules/providers/)
- Model registry expansion (models.json)
- Voice engine improvements
- GUI enhancements
- New system control commands
- New messaging connectors (extend `BaseConnector` in `modules/messaging/`)

### Medium Impact
- New specialized agents (in `modules/agents/`)
- Integration modules (new services)
- Token counting accuracy improvements
- Context window management strategies
- Plugin marketplace contributions (new plugins for `marketplace_index.json`)
- Next.js frontend improvements (`frontend/`)
- Test coverage improvements
- Documentation improvements

### Good First Issues
- Add command patterns to `voice_nlu.py`
- Add file format support to document reader
- Improve error messages
- Add missing type hints

---

## Architecture Decisions

Before making significant architectural changes, read [ARCHITECTURE.md](ARCHITECTURE.md) to understand:
- The module import pattern and why it exists
- The backend failover chain design
- The threading model and Qt signal communication
- The safety and permission system

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
