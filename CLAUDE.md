# CLAUDE.md - Copilot Context for LADA

## 1. Project Overview

**LADA** (Language Agnostic Digital Assistant) is a modular Python desktop AI assistant.

- **133 Python modules** organized under `modules/` and `core/`
- **36 AI models** across **12 providers** via **4 protocol adapters**
- **PyQt5 desktop GUI** + **Next.js web frontend** + **Web dashboard** + **WebSocket gateway**
- **Always-on voice control** (Tamil + English)
- **Autonomous screen control** via Comet agent (See-Think-Act loop)
- **12 communication channels**: Desktop GUI, Web Dashboard, Next.js Frontend, Telegram, Discord, Slack, WhatsApp, Mattermost, Teams, LINE, Signal, Matrix
- **System integrations**: Spotify, Gmail, Calendar, Smart Home
- **Per-provider rate limiting** with TokenBucket + CircuitBreaker
- **Plugin marketplace** with install/uninstall/update and hot-reload
- **Executor-based command architecture** with 8 domain-specific executors
- **Centralized service registry** for lazy-loading optional modules
- **Platform**: Windows 10/11 primary, Python 3.11+

## 2. Key Architecture

| Layer | File | Role |
|-------|------|------|
| GUI entry | `lada_desktop_app.py` | PyQt5 desktop application (6,010 lines) |
| CLI entry | `main.py` | Command-line interface |
| API entry | `modules/api_server.py` | Thin FastAPI launcher (244 lines), delegates to `modules/api/` |
| API routers | `modules/api/routers/` | 8 FastAPI router modules (1,666 lines total) |
| Next.js frontend | `frontend/` | TypeScript web app (chat, models, settings) |
| Command processor | `lada_jarvis_core.py` | Thin facade (1,753 lines) dispatching to 8 executors |
| Executors | `core/executors/` | 8 domain-specific command handlers (3,524 lines total) |
| Service registry | `core/services.py` | Centralized lazy-loading module registry (280 lines, 64 modules) |
| AI command agent | `modules/ai_command_agent.py` | AI-first command execution with ReAct tool loop |
| AI routing | `lada_ai_router.py` | ProviderManager-only routing (865 lines) |
| Provider orchestrator | `modules/providers/provider_manager.py` | Central provider management |
| Rate limiter | `modules/rate_limiter.py` | Per-provider TokenBucket + CircuitBreaker |
| Memory | `lada_memory.py` | Per-day JSON conversation persistence |
| Voice | `voice_tamil_free.py` | gTTS/pyttsx3/Kokoro + speech_recognition |
| Theme | `theme.py` | Centralized colors, typography, and QSS styles (258 lines) |
| Plugin marketplace | `modules/plugin_marketplace.py` | Plugin install/uninstall/update/search |

## 3. Critical File Map

```
lada_desktop_app.py                     PyQt5 GUI main application (6,010 lines)
lada_ai_router.py                       ProviderManager-only AI routing (865 lines)
lada_jarvis_core.py                     Command processor facade (1,753 lines)
lada_memory.py                          Persistent memory system
lada_webui.py                           Web UI launcher (API server + browser)
models.json                             AI model catalog (36 models, 12 providers)
theme.py                                Centralized colors, typography, QSS styles (258 lines)

core/
  __init__.py                           Core package init
  services.py                           Service registry — lazy-loading 64 modules (280 lines)
  executors/
    __init__.py                         BaseExecutor ABC (41 lines)
    app_executor.py                     Open/close/launch apps (137 lines)
    system_executor.py                  Volume, brightness, WiFi, power, screenshots (634 lines)
    web_media_executor.py               Web search, research, NLU, news, weather (393 lines)
    browser_executor.py                 Comet agent, smart browser, tabs, summarizers (387 lines)
    desktop_executor.py                 Windows, file finder, GUI automation, typing (537 lines)
    productivity_executor.py            Alarms, timers, Gmail, Calendar, Spotify, smart home (423 lines)
    workflow_executor.py                Workflows, routines, planner, skills, pipelines (362 lines)
    agent_executor.py                   Screenshot analysis, patterns, proactive, RAG, MCP (610 lines)

modules/providers/
  provider_manager.py                   Provider orchestrator (tier routing, health, cost)
  base_provider.py                      Provider ABC + data classes
  openai_provider.py                    OpenAI-compatible adapter (Groq, Mistral, xAI, etc.)
  anthropic_provider.py                 Anthropic adapter
  google_provider.py                    Google GenAI adapter
  ollama_provider.py                    Ollama adapter (local + cloud)

modules/api/
  __init__.py                           API package init
  deps.py                               Shared dependencies (get_router, get_jarvis, etc.)
  models.py                             Pydantic request/response models
  routers/
    __init__.py                         Router registry
    auth.py                             /auth/* endpoints
    chat.py                             /chat, /chat/stream, /conversations/*
    app.py                              /app, /sessions/*, /cost, /dashboard
    marketplace.py                      /marketplace/*, /plugins
    orchestration.py                    /plans/*, /workflows/*, /tasks/*, /skills/*
    openai_compat.py                    /v1/models, /v1/chat/completions
    websocket.py                        /ws gateway

modules/
  model_registry.py                     Model catalog loader
  tool_registry.py                      Structured tool system (32 tools)
  tool_handlers.py                      Tool handler bindings + implementations
  ai_command_agent.py                   AI-first command agent with ReAct tool loop
  context_manager.py                    Context window management
  token_counter.py                      Token counting + cost tracking
  session_manager.py                    Session isolation
  error_types.py                        Classified error system
  rate_limiter.py                       Per-provider rate limiting (273 lines)
  plugin_marketplace.py                 Plugin marketplace (690 lines)
  api_server.py                         Thin FastAPI launcher (244 lines)
  comet_agent.py                        Autonomous screen control agent
  voice_nlu.py                          Voice command patterns (50+)
  system_control.py                     Volume/brightness/WiFi/power
  web_search.py                         Web search engine
  deep_research.py                      Multi-source research
  safety_controller.py                  Action validation + undo
  browser_automation.py                 Playwright/Selenium browser automation
  browser_tab_controller.py             Chrome DevTools Protocol tab control
  multi_tab_orchestrator.py             Multi-tab coordination
  window_manager.py                     Window/app control
  gui_automator.py                      GUI automation (Comet agent uses this)
  advanced_system_control.py            File management
  desktop_control.py                    Smart file finder, window controller, browser

modules/messaging/                      12 messaging connectors
  base_connector.py                     Connector ABC
  telegram_connector.py                 Telegram bot
  discord_connector.py                  Discord bot
  slack_connector.py                    Slack app
  whatsapp_connector.py                 WhatsApp (Twilio)
  mattermost_connector.py              Mattermost bot
  teams_connector.py                    Microsoft Teams
  line_connector.py                     LINE Messaging
  signal_connector.py                   Signal (via signal-cli)
  matrix_connector.py                   Matrix / Element
  message_router.py                     Unified message routing

web/index.html                          Legacy web dashboard frontend
frontend/                               Next.js/TypeScript web frontend
  src/app/page.tsx                      Chat page
  src/app/models/page.tsx               Models page
  src/app/settings/page.tsx             Settings page
  src/lib/ws-client.ts                  WebSocket client
  src/types/ws-protocol.ts              WS message types
  Dockerfile                            Frontend container

plugins/marketplace_index.json          Plugin marketplace seed data (5 plugins)
docker-compose.yml                      Full stack: lada + ollama + chromadb + frontend
LADA-AutoStart.bat                      Headless auto-start for Task Scheduler

docs/                                   Documentation (SETUP, ARCHITECTURE, CONTRIBUTING, etc.)
tests/                                  72 test files (pytest + E2E)
```

## 4. Module Patterns

- **Service Registry**: All 52 optional modules are registered in `core/services.py` via `build_default_registry()`. At startup, `probe_all()` import-tests each module and sets availability flags. Backward-compatible `_OK` flags (e.g., `SYSTEM_OK = _svc.ok('system')`) and class references (e.g., `SystemController = _svc.get('system', 'SystemController')`) are generated at module level in `lada_jarvis_core.py` for existing code compatibility.
- **Executor pattern**: The `process()` method in `JarvisCommandProcessor` is a thin facade (~131 lines) that iterates through 8 domain-specific executors. Each executor subclasses `BaseExecutor` and implements `try_handle(cmd) -> Tuple[bool, str]`. If an executor handles a command, it returns `(True, response)`. Otherwise `(False, "")`.
- Factory functions: `create_*()` or `get_*()` singletons.
- Configuration via `os.getenv()` with sensible defaults.
- **Graceful degradation**: missing dependencies disable features, never crash.

### Executor Dispatch Order

```python
self.executors = [
    WorkflowExecutor(self),       # Workflows, routines, planner, skills, pipelines, hooks
    ProductivityExecutor(self),    # Alarms, timers, focus, Gmail, Calendar, Spotify, smart home
    BrowserExecutor(self),         # Comet agent, smart browser, tabs, summarizers
    DesktopExecutor(self),         # Window management, file finder, GUI automation, typing
    SystemExecutor(self),          # Volume, brightness, WiFi, power, battery, screenshots
    AppExecutor(self),             # Open/close/launch applications
    WebMediaExecutor(self),        # Web search, research, NLU, news, weather
    AgentExecutor(self),           # Screenshot analysis, patterns, proactive, RAG, MCP, webhooks
]
```

## 5. Provider System

Four protocol adapters cover all 12 providers:

| Protocol Adapter | Providers |
|------------------|-----------|
| `openai-completions` | OpenAI, Groq, Mistral, xAI, DeepSeek, Together AI, Fireworks AI, Cerebras, HuggingFace |
| `anthropic-messages` | Anthropic (Claude) |
| `google-generative-ai` | Google (Gemini) |
| `ollama` | Local Ollama, Ollama Cloud, Kaggle T4 GPU |

- **Adding a new provider**: Edit `models.json` only -- no code changes needed if an existing protocol adapter covers it.
- **Tier-based routing**: fast, balanced, smart, reasoning, coding.
- **Fallback chains**: if requested tier is unavailable, progressively tries simpler tiers.
- **Rate limiting**: Per-provider TokenBucket (RPM/RPD) + CircuitBreaker with auto-recovery (`modules/rate_limiter.py`).
- **Model dropdown**: Desktop GUI calls `get_all_available_models()` from ProviderManager, stores model IDs as QComboBox itemData. Dropdown is inside `InputBar` (Perplexity-style, near chat input).

## 6. AI Query Flow

```
1. User input --> lada_desktop_app.py  OR  api_server.py  OR  messaging connectors
2. System commands --> lada_jarvis_core.py (executor dispatch --> execute)
2b. AI Command Agent --> ai_command_agent.py (ReAct tool loop for complex commands)
3. AI queries --> lada_ai_router.py
4. Rate limit check --> rate_limiter.py (TokenBucket per provider)
5. ProviderManager.query() --> best model by tier --> protocol adapter --> response
6. Response --> chat display + memory save + cost tracking
```

### Command Processing Flow

```
1. process(command) called
2. Handle pending confirmations (if any)
3. Handle privacy mode toggles
4. Executor dispatch loop:
   for executor in self.executors:
       handled, response = executor.try_handle(cmd)
       if handled: return True, response
5. Inline utility handlers (undo, file ops, time/date, greetings)
6. System status v11
7. return False, "" (not a system command -- will be sent to AI)
```

### Web Search Logic

Web search is triggered ONLY when:
- User explicitly enables the web search toggle in the UI (`web_search_enabled = True`), AND
- The query needs real-time data (`_is_knowledge_query()` returns True)

`_is_knowledge_query()` matches: temporal queries (latest, current, 2025, today), price/cost queries, live data (weather, stock, traffic). It does NOT match conceptual questions like "what is X" or "explain Y" -- those go to AI reasoning.

### Response Caching

Caching only activates when conversation history is empty (first message in a session). Uses full `prompt.lower().strip()` as cache key. This prevents stale/repeated responses in ongoing conversations.

## 7. Messaging Connectors

12 communication channels via `modules/messaging/`:

| Connector | File | Protocol |
|-----------|------|----------|
| Desktop GUI | `lada_desktop_app.py` | Qt signals |
| Web Dashboard | `web/index.html` | WebSocket |
| Next.js Frontend | `frontend/` | WebSocket |
| Telegram | `telegram_connector.py` | Telegram Bot API |
| Discord | `discord_connector.py` | Discord.py |
| Slack | `slack_connector.py` | Slack Bolt |
| WhatsApp | `whatsapp_connector.py` | Twilio |
| Mattermost | `mattermost_connector.py` | Mattermost Driver |
| Teams | `teams_connector.py` | Bot Framework |
| LINE | `line_connector.py` | LINE Messaging API |
| Signal | `signal_connector.py` | signal-cli REST |
| Matrix | `matrix_connector.py` | matrix-nio |

Features: DM pairing (6-digit codes), away messages, admin approval, per-platform auto-reply.

## 8. Plugin System

- **Plugin discovery**: `modules/plugin_system.py` -- YAML/JSON manifest, auto-load from `plugins/`
- **Plugin marketplace**: `modules/plugin_marketplace.py` (690 lines) -- install/uninstall/update/search
- **Marketplace index**: `plugins/marketplace_index.json` -- 5 seed plugins
- **Hot-reload**: `modules/lazy_loader.py` -- watchdog PluginWatcher with 500ms debounce
- **Sandboxing**: `modules/code_sandbox.py` -- RestrictedPython execution environment

## 9. Testing

```powershell
pytest tests/ -v                        # All tests (72 test files)
pytest tests/test_router.py tests/test_api_server.py -o "addopts=" --tb=short -q  # Quick core tests (20 pass)
pytest tests/test_phase2_modules.py     # Phase 2 specific (67 tests)
python tests/test_e2e_complete.py       # E2E validation
```

- Tests use `unittest.mock` for external API calls.
- Use `-o "addopts="` to override pytest.ini `--cov` flags when running quick tests.
- Pre-existing test failures (safe to ignore): `test_model_count`/`test_provider_count` (stale counts), `test_file_operations` (missing `send2trash`), `test_browser_automation` (missing `playwright`), `test_comet_agent` (missing `pytest-asyncio`).

## 10. Configuration

- `.env` file with API keys (see `.env.example` for full reference with ~400 lines).
- Key variables:
  - `GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`
  - `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, `FIREWORKS_API_KEY`
  - `LOCAL_OLLAMA_URL` (default: `http://localhost:11434`)
  - `LOCAL_FAST_MODEL` (current: `qwen2.5:7b-instruct-q4_K_M`)
  - `LOCAL_SMART_MODEL` (current: `llama3.1:8b-instruct-q4_K_M`)
  - `OLLAMA_CLOUD_KEY`, `OLLAMA_CLOUD_MODEL` (current: `gpt-oss:120b`)
- Per-provider rate limits: `GROQ_RPM`, `GROQ_RPD`, `ANTHROPIC_RPM`, etc.
- Messaging tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.
- Plugin config: `PLUGIN_INDEX_URL`, `PLUGIN_INDEX_FILE`
- Web App Auth: `LADA_WEB_PASSWORD` (default: `lada1434`), `LADA_SESSION_TTL` (default: `86400`)
- API Key: `LADA_API_KEY` (for `/v1/` OpenAI-compat endpoints)
- AI Command Agent: `LADA_AI_AGENT_ENABLED` (default: `1`), `LADA_AI_AGENT_MAX_ROUNDS` (default: `5`)
- Tunnel config: `LADA_TAILSCALE_FUNNEL` (Tailscale Funnel for free permanent public URL)
- At least **one** AI provider key is required.

## 11. Common Development Tasks

| Task | How |
|------|-----|
| Add a new AI provider | Edit `models.json`; optionally add protocol adapter in `modules/providers/` |
| Add a voice command | Add pattern to `modules/voice_nlu.py` |
| Add a system command | Create handler in the relevant executor in `core/executors/`, register in service registry if needed |
| Add a tool | Register in `modules/tool_registry.py` with JSON schema |
| Add a messaging connector | Create connector in `modules/messaging/` extending `BaseConnector` |
| Add a plugin | Create `plugins/my_plugin/` with manifest + plugin.py |
| Install marketplace plugin | Use `PluginMarketplace.install_plugin(plugin_id)` |
| Add a new module | Register in `core/services.py` `build_default_registry()`, add handler to appropriate executor |
| Add an API endpoint | Create route in appropriate `modules/api/routers/*.py` file |
| Run the GUI | `python lada_desktop_app.py` |
| Run CLI mode | `python main.py text` |
| Run API server | `python modules/api_server.py` (FastAPI on port 5000) |
| Run WebUI mode | `python main.py webui` or double-click `LADA-WebUI.bat` |
| Run Next.js frontend | `cd frontend && npm run dev` (port 3000) |
| Run full stack | `docker-compose up` (lada + ollama + chromadb + frontend) |

## 12. Known Architectural Notes

- `lada_jarvis_core.py` is **1,753 lines** — a thin facade over 8 domain-specific executors in `core/executors/`. The `process()` method is ~131 lines (executor dispatch + small inline handlers).
- `lada_desktop_app.py` is **6,010 lines** with 17+ classes. Styles are centralized in `theme.py` (258 lines).
- `lada_ai_router.py` is **865 lines** — ProviderManager-only routing (legacy dual-routing code removed).
- `modules/api_server.py` is **244 lines** — thin launcher that delegates to 8 FastAPI routers in `modules/api/routers/` (1,666 lines total).
- **Service registry** (`core/services.py`): 64 modules registered with `build_default_registry()`. Module-level `_OK` flags and class references are generated for backward compatibility.
- Provider auto-configuration reads ENV + `models.json` at startup.
- `ProviderEntry` uses **dataclass attributes** (not dict `.get()`): use `pinfo.type`, not `pinfo.get('type')`.
- Complexity analysis uses **word count + keyword matching** (not character length).
- Tier fallback order: `coding --> smart --> balanced --> fast`, `reasoning --> smart --> balanced --> fast`.
- WebSocket endpoint at `/ws`, web dashboard at `/dashboard`.
- Model dropdown uses `currentData()` (not `currentText()`) to get model IDs. Located in `InputBar.model_selector`, aliased as `self.model` in MainWindow.
- `_is_knowledge_query()` only matches real-time data needs (temporal, price, live) -- conceptual questions go to AI reasoning.
- Response cache only activates for first message in a session (empty conversation history).
- Comet agent's `_think()` disables web search and caching for internal AI calls to avoid interference.
- Rate limiter uses TokenBucket (RPM/RPD) + CircuitBreaker per provider with configurable thresholds.
- **Voice master toggle**: `self._voice_enabled` in `lada_desktop_app.py` is the single flag that gates ALL voice: speaking, listening, mic overlay, and Ctrl+M. Toggle via the "Voice ON/OFF" button; when OFF, the continuous listener fully stops (not just standby) and the Mic button is disabled.
- **AI executor mindset**: `voice_nlu.py` JARVIS prompt enforces strict `ACTION: <verb> | <args>` format only. The LADA system prompt in `lada_ai_router.py` instructs the AI to execute tasks and report what was done, never to give step-by-step instructions to the user.
- **system_keywords routing**: Commands starting with `open`, `create`, `launch`, `run`, `delete`, `rename`, etc. in `_check_system_command()` are routed through `voice_nlu` for action execution before falling through to the AI router.
- **Ollama cloud model auto-detection**: `_sync_ollama_cloud_models()` in `lada_ai_router.py` runs at every startup, queries `localhost:11434/api/tags`, finds models with `size=0` (Ollama cloud models), and auto-assigns them to the best matching routing tier. Current primary cloud model: `gpt-oss:120b` (116.8B, 131K context, tools+thinking).
- **WebUI launcher**: `lada_webui.py` starts LADA API on `0.0.0.0:5000` (background thread), auto-opens browser at `/app`. Password-protected via `LADA_WEB_PASSWORD` env var (default: `lada1434`). Shows LAN IP for remote device access. No Docker required.
- **AI Command Agent**: `modules/ai_command_agent.py` provides AI-first command execution. Classifies input as actionable vs conversational, selects model tier (fast local for simple, smart cloud for complex), runs a ReAct tool-calling loop (native function calling for OpenAI-compatible providers, prompt-based fallback for others). Has 31 tools including `find_files`, `get_app_data_paths`, `run_powershell`, `list_directory`, etc. Integrated into `_check_system_command()` after pattern matchers but before action_indicators. Config: `LADA_AI_AGENT_ENABLED`, `LADA_AI_AGENT_MAX_ROUNDS`.
- **Tailscale Funnel**: Permanent free public URL via Tailscale. Enabled with `LADA_TAILSCALE_FUNNEL=true` in `.env`. No domain purchase needed. URL format: `https://<machine>.<tailnet>.ts.net/app`.

## 13. Docker Deployment

```yaml
# docker-compose.yml services:
lada:       Python backend (port 8080)
ollama:     Local AI models (port 11434)
chromadb:   Vector memory (port 8000)
frontend:   Next.js web app (port 3000)
```

## 14. Web App Authentication

LADA's web app (`web/lada_app.html`) is the sole browser-based UI, served at `/app`. It is password-protected for secure remote access from any device on the local network.

### Auth Flow
```
1. Browser loads /app (public, no auth needed)
2. JS checks localStorage for auth token
3. If token exists -> GET /auth/check (validates token)
4. If no token or invalid -> show login screen
5. User enters password -> POST /auth/login
6. Server returns session token (24h TTL)
7. All subsequent API calls use Authorization: Bearer <token>
8. WebSocket connects with ?token= query param
```

### Endpoints
| Endpoint | Purpose |
|----------|---------|
| `POST /auth/login` | Validate password, return session token |
| `GET /auth/check` | Validate existing session token |
| `POST /auth/logout` | Invalidate session token |

### Configuration
| Env Var | Default | Purpose |
|---------|---------|---------|
| `LADA_WEB_PASSWORD` | `lada1434` | Login password |
| `LADA_SESSION_TTL` | `86400` | Token lifetime in seconds (24h) |

### /v1 API Endpoints (OpenAI-compatible)
LADA also exposes OpenAI-compatible endpoints for external tools:

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/models` | List available models (excludes local Ollama to avoid duplicates) |
| `POST /v1/chat/completions` | Chat completion (streaming SSE + non-streaming) |

### Special model: "auto"
When model is `auto`, LADA uses complexity-based tier routing (fast/balanced/smart/reasoning/coding).

### /v1 Auth
Bearer token via `LADA_API_KEY` env var. Empty = no auth (local dev). Separate from web app session auth.

## 15. Recent Changes (Changelog)

### Major Refactor: God Object Decomposition + Service Registry (2026-03-08/09)

Complete 6-phase refactoring of the LADA codebase. See `LADA-REFACTOR-PLAN.md` for full details.

**Phase 1 -- Kill Dual Routing**: Removed ~1,000 lines of legacy routing from `lada_ai_router.py`. ProviderManager is now the only AI path. File went from 1,856 to 865 lines.

**Phase 2 -- Split God Object**: Decomposed the 4,933-line `JarvisCommandProcessor` into a 1,753-line facade + 8 domain-specific executors in `core/executors/` (3,524 lines total). The `process()` method went from 1,934 lines to ~131 lines. Each executor handles one domain (system, browser, desktop, productivity, workflow, agent, app, web/media).

**Phase 3 -- Delete Unused Modules**: Removed 5 unused/superseded files (2,333 lines):
- `modules/permission_system.py` (1,135 lines) -- unused in production
- `modules/memory_system.py` (274 lines) -- superseded by `lada_memory.py`
- `modules/browser_control.py` (282 lines) -- superseded by `browser_automation.py`
- `modules/elevenlabs_voice.py` (215 lines) -- zero production imports
- `modules/task_scheduler.py` (427 lines) -- zero production imports

**Phase 4 -- Split API Server**: Decomposed the 2,240-line `api_server.py` into 8 FastAPI routers in `modules/api/routers/` (1,666 lines total). The original file is now a 244-line thin launcher.

**Phase 5 -- Desktop App Improvements**:
- 5a: Fixed model dropdown (Perplexity-style, in InputBar near chat input)
- 5b: Added animated streaming typing indicator (QTimer-based dot animation)
- 5c: Extracted theme/styles to `theme.py` (258 lines) -- centralized colors, typography, GLOBAL_QSS

**Phase 6 -- Service Registry**: Created `core/services.py` (253 lines) with `ServiceRegistry` class. Replaced 52 try/except import blocks in `lada_jarvis_core.py` with `build_default_registry()` + `probe_all()`. Backward-compatible `_OK` flags and class references maintained at module level.

**Net impact**: ~3,700 lines removed across all files. God class reduced by 64% (4,933 -> 1,753). AI router reduced by 53% (1,856 -> 865). API server reduced by 89% (2,240 -> 244).

### "One of One" Enhancement Phase (2026-03-09)

Comprehensive enhancement to make LADA a best-in-class AI assistant, surpassing competitors like OpenClaw, Open Interpreter, Claude Cowork, and AutoGPT.

**Phase 3 - Full Memory Integration:** Vector memory (`vector_memory.py`) and RAG engine (`rag_engine.py`) already fully wired into AI router. Every AI conversation enriched with semantic memory (800 tokens) and document RAG (1,000 tokens). Conversations stored with importance scoring.

**Phase 4 - Proactive Intelligence Activation:**
- Activated dormant `proactive_agent.py` (~700 lines) in desktop app
- Background monitoring thread with time/idle/app triggers
- Morning briefings (8 AM), evening summaries (6 PM)
- Suggestions displayed as notifications or chat messages by priority
- Integration hook: `register_callback()` for UI notifications

**Phase 5 - Rich Code Execution Output:**
- Added `RichExecutionResult` dataclass with `plot_data` (base64 PNG) and `table_html`
- New `execute_with_rich_output()` method in `code_sandbox.py`
- Captures matplotlib plots and pandas DataFrames
- Plots render inline in chat with `PLOT:` prefix
- Updated `_handle_execute_code` in both `tool_handlers.py` and `agent_executor.py`

**Phase 6 - Extended Tool Ecosystem:**
Added 3 new tools to AI Command Agent (32 -> 35 tools):
- **`git`** - Read-only git operations (status, log, diff, branch, stash)
- **`http_request`** - HTTP requests to APIs (GET/POST/PUT/DELETE)
- **`database_query`** - Read-only SELECT queries on SQLite databases

Files modified: `modules/tool_registry.py`, `modules/tool_handlers.py`

**New capabilities after this phase:**
- Proactive suggestions based on time, idle state, app context
- Matplotlib plot rendering inline in chat
- Git repository inspection
- API/HTTP endpoint testing
- SQLite database querying

### Gap-Closing: Wire Dormant Modules (2026-03-09)

Wired 12 existing-but-disconnected modules into the service registry, executors, and tool system based on competitive analysis vs Open Interpreter, PyGPT, Jan AI, and OpenClaw.

**Newly wired modules:**
- **`image_generation.py`** (175 lines) -- AI image generation with Stability AI + Gemini Imagen backends. Commands: `generate image`, `create image`, `draw`. Images render inline in chat.
- **`video_generation.py`** (283 lines) -- AI video generation with Google Veo + Stability AI backends. Commands: `generate video`, `create video`, `animate`. Video links displayed in chat.
- **`code_sandbox.py`** (649 lines) -- Secure code execution with RestrictedPython + subprocess isolation. Supports Python, JavaScript, PowerShell. Commands: `run code`, `execute python`.
- **`document_reader.py`** (561 lines) -- PDF/DOCX/TXT reading with table extraction and AI summarization. Commands: `read document`, `summarize pdf`, `chat with document`.
- **`deep_research.py`** -- Multi-source research engine. Commands: `deep research about X`.
- **`visual_grounding.py`** -- Gemini Vision-based screen understanding for Comet agent.
- **`page_vision.py`** -- Web page visual analysis via Gemini Vision.
- **`sentiment_analysis.py`** -- Text sentiment analysis.
- **`weather_briefing.py`** -- Enhanced weather briefing system.
- **`focus_modes.py`** -- Advanced focus modes (coding, writing, study). Commands: `focus mode coding`, `exit focus`.
- **`citation_engine.py`** -- Academic citation generation.
- **`export_manager.py`** -- Conversation export to PDF/DOCX/MD.

**New AI Command Agent tools:** `generate_image`, `generate_video`, `execute_code`, `read_document`

**Service registry:** 52 -> 64 modules

### Local Model Upgrade
- **Removed**: `mistral:7b-instruct-q4_0`, `neural-chat:7b-v3.3-q5_K_M` (freed ~9.2 GB VRAM)
- **Added**: `qwen2.5:7b-instruct-q4_K_M` (fast tier, ~4.1 GB), `llama3.1:8b-instruct-q4_K_M` (smart tier, ~4.9 GB)
- Hardware: RTX 3050 6 GB VRAM -- both models fit simultaneously with headroom

### AI Task Execution Enforcement
Three fixes to stop AI from giving instructions instead of doing tasks:

1. **`modules/voice_nlu.py`** -- JARVIS AI prompt now enforces strict `ACTION: <verb> | <args>` only. Added few-shot examples for: create folder, find location, write file.
2. **`lada_ai_router.py`** -- LADA system prompt updated to executor mindset: "When the user gives you a command, execute it. Never give step-by-step instructions for the user to follow."
3. **`lada_desktop_app.py`** `_check_system_command()` -- `system_keywords` list expanded with: `open `, `create `, `make a `, `launch `, `run `, `execute `, `delete `, `rename `, `move file`, `copy file`, `new folder`, `new file`, `write a ` -- these route through `voice_nlu` for execution.

### Voice Master Toggle
Full on/off for ALL voice activity via single `self._voice_enabled` flag.

### Ollama Cloud -- gpt-oss:120b Integration
Added `gpt-oss:120b` (36th model): ollama-cloud provider, reasoning tier, 131K context, tools+thinking. Auto-detected at startup via `_sync_ollama_cloud_models()`.

### OpenAI-compatible /v1 Endpoints
`GET /v1/models` + `POST /v1/chat/completions` (streaming SSE + non-streaming). Routes through ProviderManager. Special `auto` model uses complexity analysis.

### AI Command Agent -- AI-First Intelligent Command Execution
`AICommandAgent` class with ReAct tool-calling loop. 38 tools. Dual strategies: native function calling for OpenAI-compatible providers, prompt-based fallback for others. Max 5 rounds per execution.

### RAG + Vector Memory in AI Router
Vector memory context (800 tokens) and RAG document context (1,000 tokens) injected into both streaming and non-streaming AI paths.

### AI Tool Calling Integration
OpenAI provider parses `tool_calls` from responses. AI router runs tool execution loop (max 3 rounds) when tools are returned.

### Cost Dashboard
`$0.00` cost button in header bar. Updates after each AI response. Click for per-provider breakdown dialog.

### Local Offline Wake Word (openwakeword)
Two-stage detection: OWW model (score >= 0.3) triggers Whisper/STT confirmation of actual wake phrase.

### Per-Topic Persistent Sessions
Named sessions saved to `data/sessions/{name}.json`. Session picker dialog in desktop app header.

### Web App Password Auth
Session-based auth with `POST /auth/login`, `GET /auth/check`, `POST /auth/logout`. All API calls use `Authorization: Bearer <token>`.
