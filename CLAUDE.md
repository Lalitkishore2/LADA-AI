# CLAUDE.md - Copilot Context for LADA

## 1. Project Overview

**LADA** (Language Agnostic Digital Assistant) is a modular Python desktop AI assistant.

- **100+ Python modules** organized under `modules/`
- **36 AI models** across **12 providers** via **4 protocol adapters**
- **PyQt5 desktop GUI** + **Next.js web frontend** + **Web dashboard** + **WebSocket gateway**
- **Always-on voice control** (Tamil + English)
- **Autonomous screen control** via Comet agent (See-Think-Act loop)
- **12 communication channels**: Desktop GUI, Web Dashboard, Next.js Frontend, Telegram, Discord, Slack, WhatsApp, Mattermost, Teams, LINE, Signal, Matrix
- **System integrations**: Spotify, Gmail, Calendar, Smart Home
- **Per-provider rate limiting** with TokenBucket + CircuitBreaker
- **Plugin marketplace** with install/uninstall/update and hot-reload
- **Platform**: Windows 10/11 primary, Python 3.11+

## 2. Key Architecture

| Layer | File | Role |
|-------|------|------|
| GUI entry | `lada_desktop_app.py` | PyQt5 desktop application |
| CLI entry | `main.py` | Command-line interface |
| API entry | `modules/api_server.py` | FastAPI REST + WebSocket gateway |
| Next.js frontend | `frontend/` | TypeScript web app (chat, models, settings) |
| Command processor | `lada_jarvis_core.py` | Routes voice/text to system commands or AI |
| AI command agent | `modules/ai_command_agent.py` | AI-first command execution with ReAct tool loop |
| AI routing | `lada_ai_router.py` | Phase 2 ProviderManager first, legacy 5-backend fallback |
| Provider orchestrator | `modules/providers/provider_manager.py` | Central provider management |
| Rate limiter | `modules/rate_limiter.py` | Per-provider TokenBucket + CircuitBreaker |
| Memory | `lada_memory.py` | Per-day JSON conversation persistence |
| Voice | `voice_tamil_free.py` | gTTS/pyttsx3/Kokoro + speech_recognition |
| Plugin marketplace | `modules/plugin_marketplace.py` | Plugin install/uninstall/update/search |

## 3. Critical File Map

```
lada_desktop_app.py                     PyQt5 GUI main application (~2000 lines)
lada_ai_router.py                       Multi-backend AI routing engine (~1200 lines)
lada_jarvis_core.py                     Command processor + NLU routing (~4750 lines)
lada_memory.py                          Persistent memory system
lada_webui.py                           Web UI launcher (API server + browser)
models.json                             AI model catalog (35 models, 12 providers)

modules/providers/provider_manager.py   Provider orchestrator (tier routing, health, cost)
modules/providers/base_provider.py      Provider ABC + data classes
modules/providers/openai_provider.py    OpenAI-compatible adapter (Groq, Mistral, xAI, DeepSeek, Together, Fireworks, Cerebras)
modules/providers/anthropic_provider.py Anthropic adapter
modules/providers/google_provider.py    Google GenAI adapter
modules/providers/ollama_provider.py    Ollama adapter (local + cloud)

modules/model_registry.py              Model catalog loader
modules/tool_registry.py               Structured tool system (31 tools)
modules/tool_handlers.py               Tool handler bindings + implementations
modules/ai_command_agent.py            AI-first command agent with ReAct tool loop
modules/context_manager.py             Context window management
modules/token_counter.py               Token counting + cost tracking
modules/session_manager.py             Session isolation
modules/error_types.py                 Classified error system
modules/rate_limiter.py                Per-provider rate limiting (273 lines)
modules/plugin_marketplace.py          Plugin marketplace (690 lines)

modules/api_server.py                  FastAPI REST + WebSocket gateway
modules/comet_agent.py                 Autonomous screen control agent
modules/voice_nlu.py                   Voice command patterns (50+)
modules/system_control.py              Volume/brightness/WiFi/power
modules/web_search.py                  Web search engine
modules/deep_research.py               Multi-source research
modules/safety_controller.py           Action validation + undo
modules/permission_system.py           Permission levels

modules/messaging/                     12 messaging connectors
  base_connector.py                    Connector ABC
  telegram_connector.py                Telegram bot
  discord_connector.py                 Discord bot
  slack_connector.py                   Slack app
  whatsapp_connector.py                WhatsApp (Twilio)
  mattermost_connector.py              Mattermost bot
  teams_connector.py                   Microsoft Teams
  line_connector.py                    LINE Messaging
  signal_connector.py                  Signal (via signal-cli)
  matrix_connector.py                  Matrix / Element
  message_router.py                    Unified message routing

web/index.html                         Legacy web dashboard frontend
frontend/                              Next.js/TypeScript web frontend
  src/app/page.tsx                     Chat page
  src/app/models/page.tsx              Models page
  src/app/settings/page.tsx            Settings page
  src/lib/ws-client.ts                 WebSocket client
  src/types/ws-protocol.ts             WS message types
  Dockerfile                           Frontend container

plugins/marketplace_index.json         Plugin marketplace seed data (5 plugins)
docker-compose.yml                     Full stack: lada + ollama + chromadb + frontend
LADA-AutoStart.bat                     Headless auto-start for Task Scheduler

docs/                                  Documentation (SETUP, ARCHITECTURE, CONTRIBUTING, etc.)
tests/                                 All test files (pytest + E2E)
```

## 4. Module Patterns

- All modules use **try/except imports** with `MODULE_OK` flags.
- Factory functions: `create_*()` or `get_*()` singletons.
- Configuration via `os.getenv()` with sensible defaults.
- **Graceful degradation**: missing dependencies disable features, never crash.

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
- **Model dropdown**: Desktop GUI calls `get_all_available_models()` from Phase 2 ProviderManager, stores model IDs as QComboBox itemData. Dropdown is inside `InputBar` (Perplexity-style, near chat input).

## 6. AI Query Flow

```
1. User input --> lada_desktop_app.py  OR  api_server.py  OR  messaging connectors
2. System commands --> lada_jarvis_core.py (pattern match --> execute)
2b. AI Command Agent --> ai_command_agent.py (ReAct tool loop for complex commands)
3. AI queries --> lada_ai_router.py
4. Rate limit check --> rate_limiter.py (TokenBucket per provider)
5. Phase 2 path: ProviderManager.query() --> best model by tier --> protocol adapter --> response
6. Legacy fallback: Local Ollama --> Gemini --> Kaggle --> Ollama Cloud --> Groq
7. Response --> chat display + memory save + cost tracking
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
pytest tests/ -v                        # All tests
pytest tests/test_phase2_modules.py     # Phase 2 specific (67 tests)
python tests/test_e2e_complete.py       # E2E validation
```

- Tests use `unittest.mock` for external API calls.
- Phase 2 router tests need `router._use_phase2 = False` for legacy backend mocking.

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
| Add a system command | Add to `modules/system_control.py` + wire in `lada_jarvis_core.py` |
| Add a tool | Register in `modules/tool_registry.py` with JSON schema |
| Add a messaging connector | Create connector in `modules/messaging/` extending `BaseConnector` |
| Add a plugin | Create `plugins/my_plugin/` with manifest + plugin.py |
| Install marketplace plugin | Use `PluginMarketplace.install_plugin(plugin_id)` |
| Run the GUI | `python lada_desktop_app.py` |
| Run CLI mode | `python main.py text` |
| Run API server | `python modules/api_server.py` (FastAPI on port 5000) |
| Run WebUI mode | `python main.py webui` or double-click `LADA-WebUI.bat` |
| Run Next.js frontend | `cd frontend && npm run dev` (port 3000) |
| Run full stack | `docker-compose up` (lada + ollama + chromadb + frontend) |

## 12. Known Architectural Notes

- `lada_jarvis_core.py` is **4750+ lines** -- it is the command routing monolith, kept as a thin facade over submodules.
- Provider auto-configuration reads ENV + `models.json` at startup.
- `ProviderEntry` uses **dataclass attributes** (not dict `.get()`): use `pinfo.type`, not `pinfo.get('type')`.
- Complexity analysis uses **word count + keyword matching** (not character length).
- Tier fallback order: `coding --> smart --> balanced --> fast`, `reasoning --> smart --> balanced --> fast`.
- WebSocket endpoint at `/ws`, web dashboard at `/dashboard`.
- Model dropdown uses `currentData()` (not `currentText()`) to get Phase 2 model IDs. Located in `InputBar.model_selector`, aliased as `self.model` in MainWindow.
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
3. If token exists → GET /auth/check (validates token)
4. If no token or invalid → show login screen
5. User enters password → POST /auth/login
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

### Local Model Upgrade
- **Removed**: `mistral:7b-instruct-q4_0`, `neural-chat:7b-v3.3-q5_K_M` (freed ~9.2 GB VRAM)
- **Added**: `qwen2.5:7b-instruct-q4_K_M` (fast tier, ~4.1 GB), `llama3.1:8b-instruct-q4_K_M` (smart tier, ~4.9 GB)
- Hardware: RTX 3050 6 GB VRAM — both models fit simultaneously with headroom

### AI Task Execution Enforcement
Three fixes to stop AI from giving instructions instead of doing tasks:

1. **`modules/voice_nlu.py`** — JARVIS AI prompt now enforces strict `ACTION: <verb> | <args>` only. Added few-shot examples for: create folder, find location, write file.
2. **`lada_ai_router.py`** — LADA system prompt updated to executor mindset: "When the user gives you a command, execute it. Never give step-by-step instructions for the user to follow."
3. **`lada_desktop_app.py`** `_check_system_command()` — `system_keywords` list expanded with: `open `, `create `, `make a `, `launch `, `run `, `execute `, `delete `, `rename `, `move file`, `copy file`, `new folder`, `new file`, `write a ` — these route through `voice_nlu` for execution.

### Voice Master Toggle
Full on/off for ALL voice activity via single `self._voice_enabled` flag:

- **`lada_desktop_app.py` `__init__`** — Added `self._voice_enabled = True`
- **`_toggle_always_on_voice()`** — Now a master toggle: OFF fully stops continuous listener, closes mic overlay, disables Mic button, no farewell speech. ON restarts listener, re-enables Mic button, speaks "Voice control on."
- **5 `voice.speak()` calls** — All gated with `and self._voice_enabled`
- **`_toggle_voice()` / `_listen()`** — Both return early if `not self._voice_enabled`

### Ollama Cloud — gpt-oss:120b Integration
- **`models.json`** — Added `gpt-oss:120b` (36th model): ollama-cloud provider, reasoning tier, 131K context, tools+thinking
- **`.env`** — `OLLAMA_CLOUD_MODEL=gpt-oss:120b`
- **`lada_ai_router.py`** — `ollama_cloud_models` dict: `reasoning` and `default` tiers now use `gpt-oss:120b`
- **`lada_ai_router.py`** — Added `_sync_ollama_cloud_models()`: runs at startup, queries local Ollama API for `size=0` models (cloud-registered), auto-assigns each to the best matching tier. Adding any new Ollama cloud model and restarting LADA is sufficient for it to be picked up automatically.

### OpenAI-compatible /v1 Endpoints
- **`modules/api_server.py`** — Added OpenAI-compatible endpoints: `GET /v1/models` (lists non-local models in OpenAI format) + `POST /v1/chat/completions` (streaming SSE + non-streaming). Routes through ProviderManager for rate limiting and tier-based routing. Special `auto` model uses LADA's complexity analysis.
- **`.env`** — Added `LADA_API_KEY=lada-local-key`

### WebUI Launcher
- **`lada_webui.py`** — Unified launcher: starts LADA API server (0.0.0.0:5000, background thread), auto-opens browser at `/app`. Shows both local and LAN URLs for remote device access. Graceful shutdown via Ctrl+C. No Docker required.
- **`LADA-WebUI.bat`** — Windows double-click launcher.
- **`main.py`** — Added `webui` mode: `python main.py webui`. Updated help text and docstring.

### Improvement 1: RAG + Vector Memory wired into AI Router
- **`lada_ai_router.py`** — Added `VectorMemorySystem` + `RAGEngine` init in `__init__` (guarded by `VECTOR_MEMORY_OK` flag). Both modules were previously feature-complete but unused.
- **`lada_ai_router.py` `_query_via_provider_manager()`** — Before building the message list, retrieves up to 800-token vector memory context and 1000-token RAG document context; appends both to `web_context`. After getting a response, stores the exchange in vector memory for future retrieval.
- **`lada_ai_router.py` `_stream_via_provider_manager()`** — Same memory/RAG injection applied to the streaming path; stores completed response in vector memory.

### Improvement 2: AI Tool Calling (Function Calling) Integration
- **`modules/providers/base_provider.py`** — Added `tool_calls: List[Dict[str, Any]] = field(default_factory=list)` to `ProviderResponse` dataclass.
- **`modules/providers/openai_provider.py`** — `complete()` now accepts optional `tools: List[Dict]` parameter; passes `tools` + `tool_choice="auto"` to API payload when provided; parses `tool_calls` from the response message and returns them in `ProviderResponse`.
- **`lada_ai_router.py`** — Added `ToolRegistry` init + tool execution loop (max 3 rounds) in `_query_via_provider_manager()`. When AI returns tool calls, each call is executed via `tool_registry.execute()`, results appended as `role=tool` messages, then AI continues the conversation with tool results.

### Improvement 3: Cost Dashboard in GUI Status Bar
- **`lada_desktop_app.py`** — Added `CostTracker` import (try/except, graceful fallback). Initialized `_cost_tracker` and `_last_prompt` in `MainWindow.__init__` after `_init_advanced_modules()`.
- **`lada_desktop_app.py`** — Added `$0.00` cost button in header bar (after voice button). Updates to real cost (e.g., `$0.0023`) after each AI response. Clicking opens a QDialog with total requests/tokens/cost, budget remaining, and per-provider breakdown.
- **`lada_desktop_app.py` `_on_ai_done()`** — After `_save()`, records the exchange via `_cost_tracker.record_from_text()`. Extracts `cost_input`/`cost_output` per million tokens from the model registry. Updates cost button text + status bar message.

### Improvement 4: Local Offline Wake Word Detection (openwakeword)
- **`requirements.txt`** — Added `openwakeword>=0.6.0` (local offline wake word detection, optional).
- **`voice_tamil_free.py`** — Added module-level openwakeword init: loads "alexa" ONNX model at import time; sets `_OWW_OK = True` if successful, falls back silently if not installed.
- **`voice_tamil_free.py` `listen_for_wake_word()`** — Checks `_OWW_OK` first; if available, delegates to `_listen_oww_with_validation(timeout)` for local detection. Falls back to original Google STT path if openwakeword is not installed.
- **`voice_tamil_free.py` `_listen_oww_with_validation()`** — Two-stage detection: Stage 1 streams 80ms PCM chunks (16kHz) through OWW model; any score ≥ 0.3 triggers Stage 2 validation. Stage 2 captures 0.8s of additional audio and runs local Whisper (or Google STT fallback) to confirm the transcript contains an actual LADA wake phrase. Eliminates false positives.
- **`voice_tamil_free.py` `_oww_confirm_phrase()`** — Helper that creates an `sr.AudioData` from raw PCM bytes, runs `_transcribe_hybrid_stt` (Faster-Whisper), and matches the result against `self.wake_words`.

### Improvement 5: Per-Topic Persistent Sessions
- **`lada_memory.py`** — Added `current_session_name: Optional[str]` and `_sessions_dir` (under `data/sessions/`) to `MemorySystem.__init__`. Added 4 new methods: `start_named_session(name)` (saves current session, loads named session from file or starts fresh, returns bool whether existing session was loaded), `save_named_session()` (writes `{session_name, updated_at, messages}` to `data/sessions/{name}.json`), `list_named_sessions()` (returns sorted list of session stems), `delete_named_session(name)` (unlinks file, clears `current_session_name` if it matches).
- **`lada_desktop_app.py`** — Added `Session` button in header bar. Clicking opens a QDialog (`_open_session_picker`) listing all existing sessions in a `QListWidget` plus a `QLineEdit` for creating new sessions. "Switch / Start" saves the current session (if named), loads the target session JSON into `self.conv`, rebuilds the chat view, and updates the button label.
- **`lada_desktop_app.py` `_save()`** — Auto-saves current conversation to `data/sessions/{_current_session_name}.json` whenever `_save()` is called, so session state persists automatically after every message exchange.

### Web App as Sole UI + Password Auth
Removed Open WebUI as secondary interface. Made `web/lada_app.html` the sole browser-based UI with password login and remote device access.

- **`modules/api_server.py`** — Added session-based auth: `_auth_password`, `_session_tokens`, `_session_ttl` state. Added `_create_session_token()` and `_validate_session_token()` helpers. Added `_register_auth_routes()` with `POST /auth/login`, `GET /auth/check`, `POST /auth/logout`. Added HTTP auth middleware (public paths: `/app`, `/auth/login`, `/health`, `/docs`, `/static`; `/v1/*` uses separate `LADA_API_KEY` auth). Added WebSocket token validation via `?token=` query param. Changed default host from `127.0.0.1` to `0.0.0.0`. Removed "Open WebUI" references from comments.
- **`web/lada_app.html`** — Added full-screen login overlay with password input. Added `authFetch()` wrapper that injects `Authorization: Bearer` header and auto-redirects to login on 401. Replaced all 23 `fetch()` calls with `authFetch()`. Updated `connectWS()` to pass token as `?token=` query param. Changed `DOMContentLoaded` to validate stored token before `init()`.
- **`docker-compose.yml`** — Removed `open-webui` service and `open-webui-data` volume.
- **`.env`** — Removed `OPEN_WEBUI_PORT=3001`. Added `LADA_WEB_PASSWORD=lada1434`, `LADA_SESSION_TTL=86400`.
- **`lada_webui.py`** — Removed Open WebUI references. Added LAN IP detection via `socket` for remote access URLs.
- **`main.py`** — Updated help text and docstring (removed "Docker"/"Open WebUI" references).
- **`SETUP.md`** — Documented password login and remote access. Removed Open WebUI from Docker description.
- **`CLAUDE.md`** — Rewrote section 14 from "Open WebUI Integration" to "Web App Authentication". Updated docker service list, config section, dev tasks table, and all changelog entries.

### AI Command Agent — AI-First Intelligent Command Execution
Replaced rigid pattern matching with an AI agent that understands any command, selects appropriate tools, and executes autonomously via a ReAct tool-calling loop. Fixes "find my WhatsApp photos" routing to Windows Search instead of actually locating files.

- **`modules/ai_command_agent.py`** — NEW. `AICommandAgent` class with `try_handle()` entry point. Classifies input as actionable vs conversational (`_is_actionable`), selects model tier — fast (local) for simple commands, smart (cloud) for complex (`_select_tier`). Dual tool-calling strategies: `_run_native_tool_loop` for OpenAI-compatible providers (Groq, OpenAI, Mistral), `_run_prompt_tool_loop` with `TOOL_CALL: {...}` parsing for Gemini/Ollama/Anthropic. Max 5 rounds per execution.
- **`modules/tool_handlers.py`** — NEW. Wires handler functions to all 31 registered tools. Contains implementations for 11 new agent tools: `find_files` (recursive glob search with file type maps), `get_app_data_paths` (lookup table for 15+ Windows apps — WhatsApp, Telegram, Chrome, Discord, Spotify, Steam, etc.), `run_powershell` (sandboxed with blocked command list), `list_directory`, `open_path`, `read_file_preview`, `search_file_content`, `get_folder_size`, `clipboard_read/write`, `get_recent_files`. Also wires 20 existing system tool handlers (volume, brightness, screenshot, open/close app, etc.).
- **`modules/tool_registry.py`** — Added `create_agent_tools()` with 11 new `ToolDefinition` objects. Updated `get_tool_registry()` to register both system and agent tools (31 total).
- **`lada_ai_router.py`** — Fixed bug: `tool_registry.execute(fn_name, **fn_args)` → `execute(fn_name, fn_args)` (was unpacking args dict into execute's kwargs). Added `wire_tool_handlers()` call at startup to bind handler functions to all tool definitions.
- **`lada_desktop_app.py`** — Initialized `AICommandAgent` in `_deferred_heavy_init()` after router/agents init. Inserted agent dispatch into `_check_system_command()` after pattern matchers but before action_indicators block. Both chat and voice benefit since both call `_check_system_command()`.
- **`.env`** — Added `LADA_AI_AGENT_ENABLED=1`, `LADA_AI_AGENT_MAX_ROUNDS=5`.

### Permanent Named Tunnel Support (Cloudflare) — REMOVED
Cloudflare tunnel code removed in favor of Tailscale Funnel (free, no domain needed).

### Model Selection Fix + Perplexity-Style Dropdown
Fixed model selection bug where the user's chosen model was ignored (always defaulted to auto-selected tier). Moved model dropdown from header bar to near the chat input area.

- **`lada_ai_router.py`** — Added `self._phase2_forced_model` field in `__init__`. Updated `set_phase2_model()` to store the model ID directly (previously called dead-code `force_provider()` which was never read by routing). Updated `_query_via_provider_manager()` and `_stream_via_provider_manager()` to check `_phase2_forced_model` first before falling back to `get_best_model()` auto-selection.
- **`lada_desktop_app.py`** — Fixed voice path in `_on_wake_command()`: now calls `get_backend_from_name()` before `query()` (was passing raw model ID string directly, bypassing Phase 2 gate). Moved model `QComboBox` from header bar into `InputBar` class as `model_selector` (Perplexity-style, below chat input). Aliased as `self.model` for backward compatibility. Removed 30-line header dropdown block.
- **`lada_webui.py`** — Removed `_start_public_tunnel()` function (95 lines), `_tunnel_process` global, and all Cloudflare tunnel logic. Simplified `main()` to call `_start_tailscale_funnel()` directly.
- **`.env`** — Removed `LADA_PUBLIC_TUNNEL`, `LADA_TUNNEL_NAME`, `LADA_TUNNEL_HOSTNAME` options.
- **`SETUP.md`** — Removed Cloudflare quick tunnel and named tunnel sections (~130 lines). Tailscale Funnel is now the sole public access method.
