# LADA -- Language Agnostic Digital Assistant

Your own personal AI assistant. Any backend. Any voice. Full system control.

LADA is a modular desktop AI assistant that runs on your machine with config-driven multi-provider AI routing (36 models across 12 providers via 4 protocol adapters), per-provider rate limiting (TokenBucket + CircuitBreaker), always-on voice control, autonomous screen automation, a WebSocket gateway with web dashboard and Next.js frontend, plugin marketplace with hot-reload, 12 communication channels (including 9 messaging connectors), and 100+ Python modules. The provider system supports Local Ollama, Google Gemini, Groq Cloud, Kaggle T4 GPU, Ollama Cloud, Anthropic, Mistral, xAI, DeepSeek, Together AI, Fireworks AI, Cerebras, and more -- with tier-based routing, automatic failover, and per-request cost tracking.

Inspired by [OpenClaw](https://github.com/openclaw/openclaw) agent architecture: heartbeat system, context compaction, model failover chains, event hooks, and workflow pipelines.

---

## Quick Start

**Runtime: Python 3.11+**

```powershell
cd C:\JarvisAI
python -m venv jarvis_env
.\jarvis_env\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # Edit with your API keys
python lada_desktop_app.py    # Launch GUI
```

Or use the batch launcher:
```powershell
.\LADA-GUI.bat
```

### Minimum Setup

You need **at least one AI backend** configured. The fastest option:

1. Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Put it in `.env`: `GEMINI_API_KEY=your_key_here`
3. Run `python lada_desktop_app.py`

### Operational Runbooks

For runtime operations and incident triage, see:

- `docs/RUNTIME_STABILIZATION_CLOSEOUT_2026-04-07.md`
- `docs/RUNTIME_HARDENING_BACKLOG_2026-04-07.md`
- `docs/RUNTIME_FALLBACK_SEVERITY_RUNBOOK_2026-04-07.md`
- `docs/STARTUP_DIAGNOSTICS_TRIAGE_RUNBOOK_2026-04-07.md`
- `docs/RUNTIME_STABILIZATION_COMMIT_PLAN_2026-04-07.md`

---

## Features

### AI Engine
- **36 AI models across 12 providers** with 4 protocol adapters (OpenAI-compatible, Anthropic, Google, Ollama) and tier-based routing with automatic failover
- **Config-driven model registry** (`models.json`) with per-model cost, context window, and tier classification
- **Per-provider rate limiting** with TokenBucket (RPM/RPD) and CircuitBreaker with auto-recovery
- **Token and cost tracking** with per-request token counting, context window fit checking, and per-model input/output pricing
- **Context window management** with per-model enforcement, token budget calculation, and automatic message fitting/compaction
- **Advanced planning** with multi-step plan generation, dependency graphs, conditional branching, plan revision on failure, and verification steps
- **Streaming responses** with ChatGPT-style typing effect
- **Web search** with real-time context injection and source citations
- **Deep research** mode with multi-source synthesis
- **Response caching** for repeated queries
- **Query complexity analysis** -- routes simple vs complex queries to appropriate models

### Voice
- **Always-on listening** with "Hey LADA" wake word detection
- **Tamil + English** support with auto language detection
- **Compound commands**: "set volume to 30 and then open spotify"
- **Offline fallback**: pyttsx3 TTS when internet unavailable
- **Voice sessions**: separate history for voice conversations

### Desktop Control
- Volume, brightness, mute, WiFi, Bluetooth toggle
- Open/close/focus any application
- Screenshots, screen recording
- Process management (list, kill)
- Shutdown, restart, lock, sleep
- Window snap, minimize, maximize

### Autonomous Agent (Comet)
- **See-Think-Act loop**: captures screen, AI plans next action, executes with pyautogui
- Browser automation: navigate, click, type, scroll, fill forms
- Multi-step task execution with retry and self-correction
- Progress overlay with live action log and stop button
- Up to 50 steps per task, 3 retries per step

### File Analysis
- Attach and analyze 25+ file formats in chat
- PDF reading (pdfplumber fallback), DOCX (python-docx fallback)
- Code files: .py, .js, .ts, .java, .cpp, .go, .rs, .rb, and more
- CSV, HTML, XML, YAML, JSON, TOML, SQL
- 50MB file size guard, 12KB content window per file

### AI Generation & Code Execution
- **Image generation** with Stability AI (SDXL) + Gemini Imagen backends
- **Video generation** with Google Veo + Stability AI backends
- **Secure code sandbox** with RestrictedPython + subprocess isolation (Python, JavaScript, PowerShell)
- **Document reading** with AI summarization (PDF/DOCX/TXT)
- Commands: `generate image of...`, `generate video of...`, `run code`, `read document`

### Integrations
- **Spotify**: play, pause, next, previous, search, queue, shuffle, playlists
- **Smart Home**: Philips Hue + Home Assistant + Tuya device control
- **Gmail**: read, compose, send, search emails (OAuth2)
- **Google Calendar**: events, reminders, scheduling
- **Weather**: daily briefings with OpenWeatherMap

### Messaging Connectors
- **Telegram**, **Discord**, **Slack**, **WhatsApp**, **Mattermost**, **Teams**, **LINE**, **Signal**, **Matrix** connectors with unified MessageRouter
- DM pairing (6-digit codes), away messages, admin approval, per-platform auto-reply
- Consistent interface across all platforms via `modules/messaging/`

### Web Dashboard
- **Single-page chat interface** at the `/dashboard` endpoint served by the API server
- WebSocket-based real-time bidirectional messaging (JSON protocol with chat, agent, system, ping/pong message types)
- Dark theme, streaming messages, model selector dropdown, markdown rendering, source chips
- Access by starting the API server and navigating to `http://localhost:<port>/dashboard`

### Next.js Frontend
- **TypeScript/React web application** with 3 pages: Chat, Models, Settings
- WebSocket client with typed message protocol (`src/types/ws-protocol.ts`)
- Tailwind CSS dark theme, streaming chat messages
- Runs on port 3000 (standalone or via Docker)
- Start: `cd frontend && npm run dev` or via `docker-compose up`

### Plugin Marketplace
- **Plugin marketplace** with install/uninstall/update/search (`modules/plugin_marketplace.py`, 690 lines)
- **5 seed plugins** in `plugins/marketplace_index.json`
- **Hot-reload** via watchdog PluginWatcher with 500ms debounce
- **Plugin sandboxing** via RestrictedPython execution environment

### REST API
- **12+ endpoints** via FastAPI: chat, stream, agents, conversations, voice, health, export
- **WebSocket gateway** at `/ws` for real-time streaming
- **OpenClaw compatibility routes** at `/openclaw/*` for status, connect, navigate, action, and snapshot

### OpenClaw-Inspired Systems
- **Heartbeat**: proactive periodic check-ins with daily memory logs
- **Context Compaction**: auto-summarization before context window limits
- **Model Failover**: auth profile rotation with cooldown tracking
- **Workflow Pipelines**: deterministic multi-step execution with approval gates
- **Event Hooks**: 20 event types, async dispatch, directory-based hook discovery
- **Native OpenClaw compatibility mode**: `openclaw ...` commands in core browser executor, API compatibility at `/openclaw/*`, and optional gateway adapter via `LADA_OPENCLAW_ADAPTER_ENABLED=true`

### Safety
- **Permission system** with enforced permission levels (1,135 lines)
- **Code sandbox** with RestrictedPython execution environment
- **Safety controller** with action validation and undo stack
- **Safety gate** with confirmation gates for dangerous operations
- **Tool registry** with JSON-schema-based structured tool system, permission levels (SAFE/MODERATE/DANGEROUS/CRITICAL), and categories
- Protected paths (blocks system directory modifications)
- Command blacklist (blocks destructive commands)
- Sensitive data auto-redaction in logs
- Privacy modes: PUBLIC / PRIVATE / SECURE

---

## Architecture

```
                    +-------------------+
                    |   User Interface  |
                    | PyQt5 Desktop GUI |
                    | Voice | CLI | Web |
                    | Next.js Frontend  |
                    +--------+----------+
                             |
              +--------------+--------------+-----------+-----------+
              |              |              |           |           |
     +--------v--------+  +-v----------+ +-v---------+ +-v-----------+
     |   Voice NLU      | | Telegram   | | WebSocket | | REST API    |
     | Pattern matching  | | Discord    | | Gateway   | | (FastAPI)   |
     | 50+ patterns      | | Slack      | | /ws       | | 12+ routes  |
     +--------+---------+ | WhatsApp   | +-+----+----+ +------+------+
              |            | Mattermost |   |    |             |
              |            | Teams/LINE |   |    |             |
              |            | Signal     |   |    |             |
              |            | Matrix     |   |    |             |
              | (no match) +-----+------+   |    |             |
              v                  v          v    |             |
     +-------------------------------------------+            |
     |           Hybrid AI Router                 |<-----------+
     +-------------------------------------------+  (complex queries)
     |  Rate Limiter: TokenBucket + CircuitBreaker  |
     |  Phase 2: ProviderManager (preferred)      |
     |    - Tier-based routing with fallback      |
     |    - Health monitoring + cost tracking     |
     |    - Token budget + context fitting        |
     |  Legacy fallback if Phase 2 unavailable    |
     +--------+----------------------------------+
              |
     +--------v------------------------------+
     |         Provider Manager               |
     | 4 protocol adapters, 12 providers      |
     +---------+----------+---------+--------+
     | OpenAI  | Anthropic| Google  | Ollama |
     | compat. | Messages | GenAI   | REST   |
     | (Groq,  | API      | API     | API    |
     | Mistral,|          |         |        |
     | xAI,    |          |         |        |
     | DeepSeek|          |         |        |
     | Together|          |         |        |
     | Firewrks|          |         |        |
     | Cerebras|          |         |        |
     | etc.)   |          |         |        |
     +---------+----------+---------+--------+
              |
     +--------v---------+
     |  Response Output   |
     | Chat display       |
     | Voice TTS          |
     | WebSocket stream   |
     | Memory save        |
     +--------------------+
```

### Data Flow: User Message

1. User types in GUI, speaks via microphone, sends via messaging connector, or connects through WebSocket/REST API
2. Text goes to `_check_system_command()` in `lada_desktop_app.py`
3. VoiceNLU checks 50+ patterns (volume, apps, screenshots, etc.)
4. If pattern matches: execute directly via `system_control.py`, return response
5. If no match: create `StreamingAIWorker` thread
6. Worker calls `HybridAIRouter.stream_query()` with file context prepended
7. Router tries Phase 2 ProviderManager first (tier-based routing, token/cost tracking, context fitting), falls back to legacy backends
8. Router checks web search toggle, injects real-time web data if enabled
9. ProviderManager selects best provider via health monitoring and tier priority, checks rate limits (TokenBucket + CircuitBreaker), tries fallback providers if primary fails
10. Chunks stream back to GUI/WebSocket via Qt signals or WebSocket frames, displayed with typing effect
11. Full response saved to conversation history and memory; token usage and cost recorded

### Data Flow: Voice Command

1. `ContinuousListener` runs background thread with `speech_recognition`
2. Recognized text fires `wake_triggered` Qt signal
3. `_on_wake_command()` checks wake/stop phrases
4. If active: strips wake prefix, routes to `_check_system_command()` or AI
5. Pauses listener while speaking response, resumes after

---

## Model Support

### Provider System (v8)

LADA uses a config-driven provider system with 4 protocol adapters that support 12+ providers and 36 models. The `models.json` registry defines per-model cost, context window size, and tier classification.

| Provider | Protocol Adapter | Example Models | Speed | Privacy | Cost |
|----------|-----------------|----------------|-------|---------|------|
| Local Ollama | Ollama REST | Any local model | Fastest | Full | Free |
| Google Gemini | Google GenAI | gemini-2.0-flash, gemini-1.5-pro | Fast | Cloud | Free tier |
| Groq | OpenAI-compatible | llama-3.3-70b, mixtral-8x7b | Very fast | Cloud | Free tier |
| Anthropic | Anthropic Messages | claude-3.5-sonnet, claude-3-haiku | Fast | Cloud | Paid |
| Mistral | OpenAI-compatible | mistral-large, mistral-small | Fast | Cloud | Paid |
| xAI | OpenAI-compatible | grok-2, grok-2-mini | Fast | Cloud | Paid |
| DeepSeek | OpenAI-compatible | deepseek-chat, deepseek-coder | Fast | Cloud | Paid |
| Together AI | OpenAI-compatible | mixtral, llama, code models | Fast | Cloud | Paid |
| Fireworks AI | OpenAI-compatible | fast inference models | Very fast | Cloud | Paid |
| Cerebras | OpenAI-compatible | llama3.1-70b, llama3.1-8b | Very fast | Cloud | Free tier |
| Ollama Cloud | Ollama REST | llama3.1:8b, qwen2.5:32b | Medium | Cloud | Varies |
| Kaggle T4 | OpenAI-compatible | Custom (via ngrok) | Medium | Cloud | Free |

The ProviderManager automatically selects the best available provider using tier-based routing with health monitoring. If a provider fails or is unavailable, it falls back to the next healthy provider. You can also force a specific backend from the model selector dropdown in the GUI or the web dashboard.

---

## Project Structure

```
C:\JarvisAI\
|
|-- lada_desktop_app.py          # PyQt5 GUI (main entry point)
|-- lada_ai_router.py            # Multi-backend AI routing engine (Phase 2 ProviderManager + legacy fallback)
|-- lada_jarvis_core.py          # Command processor + voice command routing
|-- lada_memory.py               # Persistent memory + context management
|-- voice_tamil_free.py          # TTS (gTTS/pyttsx3) + STT engine
|-- main.py                      # CLI entry point (voice/text/gui/status)
|-- models.json                  # Model registry config (36 models, 12 providers)
|-- .env                         # API keys and configuration
|-- .env.example                 # Configuration template (~400 lines)
|-- requirements.txt             # Python dependencies
|-- docker-compose.yml           # Full stack deployment (lada + ollama + chromadb + frontend)
|-- ARCHITECTURE.md              # Detailed technical documentation
|-- CONTRIBUTING.md              # Contribution guidelines
|
|-- modules/                     # 100+ feature modules
|   |
|   |-- Provider System (Phase 2)
|   |   |-- providers/
|   |   |   |-- base_provider.py       # BaseProvider ABC, ProviderConfig, ProviderResponse, StreamChunk
|   |   |   |-- openai_provider.py     # OpenAI-compatible adapter (Groq, Mistral, xAI, DeepSeek, Together, Fireworks, Cerebras)
|   |   |   |-- anthropic_provider.py  # Anthropic Messages API adapter
|   |   |   |-- google_provider.py     # Google Generative AI adapter
|   |   |   |-- ollama_provider.py     # Ollama REST API adapter (local + cloud)
|   |   |   |-- provider_manager.py    # Central orchestrator: auto-config, tier routing, health, cost
|   |   |-- model_registry.py          # Config-driven catalog (36 models, 12 providers, per-model costs)
|   |   |-- token_counter.py           # Per-request token counting, cost tracking, context fit checking
|   |   |-- context_manager.py         # Per-model context window enforcement, message fitting/compaction
|   |   |-- advanced_planner.py        # Multi-step plans, dependency graphs, conditional branching
|   |   |-- rate_limiter.py            # Per-provider TokenBucket + CircuitBreaker (273 lines)
|   |
|   |-- Tool & Session System (Phase 1)
|   |   |-- tool_registry.py           # JSON-schema structured tools, permission levels, categories
|   |   |-- error_types.py             # Classified errors (TIMEOUT, AUTH, RATE_LIMITED, etc.), recovery strategies
|   |   |-- session_manager.py         # Session isolation (GUI_CHAT, VOICE, CLI, TELEGRAM), per-session context
|   |
|   |-- Plugin System
|   |   |-- plugin_system.py           # Plugin discovery, loading, activation
|   |   |-- plugin_marketplace.py      # Plugin marketplace: install/uninstall/update/search (690 lines)
|   |
|   |-- Voice & Input
|   |   |-- voice_nlu.py             # Voice command NLU (50+ patterns)
|   |   |-- continuous_listener.py   # Always-on microphone listener
|   |   |-- hybrid_stt.py            # Google + Whisper STT
|   |   |-- wake_word.py             # Wake word detection (Silero)
|   |   |-- advanced_voice.py        # Voice cloning, emotion
|   |   |-- realtime_voice.py        # LiveKit real-time streaming
|   |
|   |-- System Control
|   |   |-- system_control.py        # Volume, brightness, WiFi, power
|   |   |-- window_manager.py        # Window focus, snap, minimize
|   |   |-- advanced_system_control.py # Registry, services
|   |   |-- desktop_control.py       # Virtual desktops
|   |   |-- focus_modes.py           # Do-not-disturb modes
|   |
|   |-- AI & NLP
|   |   |-- nlu_engine.py            # Intent + entity extraction (spaCy)
|   |   |-- sentiment_analysis.py    # Emotion detection
|   |   |-- deep_research.py         # Multi-source research
|   |   |-- citation_engine.py       # MLA/APA/Chicago citations
|   |   |-- dynamic_prompts.py       # Context-aware prompting
|   |   |-- context_compaction.py    # Long-context compression
|   |   |-- token_optimizer.py       # Token counting
|   |   |-- pattern_learning.py      # User behavior learning
|   |
|   |-- Browser & Web
|   |   |-- web_search.py            # Web search + citations
|   |   |-- browser_automation.py    # Selenium browser control
|   |   |-- browser_tab_controller.py # Multi-tab management
|   |   |-- multi_tab_orchestrator.py # Multi-tab orchestration
|   |   |-- page_vision.py           # Page screenshot + OCR
|   |   |-- page_summarizer.py       # Webpage summarization
|   |
|   |-- Autonomous Agents
|   |   |-- comet_agent.py           # Screen control (See-Think-Act)
|   |   |-- computer_use_agent.py    # Vision-based GUI automation
|   |   |-- agent_actions.py         # Browser/email/calendar agent
|   |   |-- agent_orchestrator.py    # Multi-agent coordination
|   |   |-- agent_collaboration.py   # Agent-to-agent communication
|   |   |-- proactive_agent.py       # Battery/reminder alerts
|   |
|   |-- Task & Workflow
|   |   |-- task_orchestrator.py     # Parallel execution, DAG scheduling
|   |   |-- task_planner.py          # Plan decomposition
|   |   |-- event_hooks.py           # Event dispatch and triggers
|   |   |-- task_automation.py       # Task orchestration
|   |   |-- workflow_engine.py       # Workflow definition
|   |   |-- workflow_pipelines.py    # Pipeline composition
|   |   |-- routine_manager.py       # Save/load routines
|   |
|   |-- Integrations
|   |   |-- spotify_controller.py    # Spotify Web API (OAuth2 PKCE)
|   |   |-- smart_home.py           # Hue + Home Assistant + Tuya
|   |   |-- gmail_controller.py     # Gmail read/send/search
|   |   |-- google_calendar.py      # Calendar events
|   |   |-- calendar_controller.py  # Calendar operations
|   |   |-- weather_briefing.py     # Weather + morning briefing
|   |   |-- youtube_summarizer.py   # YouTube transcript summary
|   |
|   |-- Messaging Connectors
|   |   |-- messaging/
|   |       |-- base_connector.py      # Connector ABC
|   |       |-- telegram_connector.py  # Telegram bot
|   |       |-- discord_connector.py   # Discord bot
|   |       |-- slack_connector.py     # Slack app
|   |       |-- whatsapp_connector.py  # WhatsApp (Twilio)
|   |       |-- mattermost_connector.py # Mattermost bot
|   |       |-- teams_connector.py     # Microsoft Teams
|   |       |-- line_connector.py      # LINE Messaging
|   |       |-- signal_connector.py    # Signal (signal-cli)
|   |       |-- matrix_connector.py    # Matrix / Element
|   |       |-- message_router.py      # Unified message routing
|   |
|   |-- Memory & Learning
|   |   |-- lada_memory.py          # Conversation storage
|   |   |-- vector_memory.py        # Semantic search (ChromaDB)
|   |   |-- mcp_client.py           # Model Context Protocol
|   |
|   |-- Files & Documents
|   |   |-- file_operations.py      # File search, create, move
|   |   |-- document_reader.py      # PDF/DOCX/TXT parsing
|   |   |-- file_encryption.py      # Fernet + AES encryption
|   |   |-- export_manager.py       # CSV/PDF/DOCX export
|   |   |-- markdown_renderer.py    # Response formatting
|   |   |-- rag_engine.py           # Retrieval-Augmented Generation
|   |
|   |-- Safety & Monitoring
|   |   |-- safety_controller.py    # Action validation + undo stack
|   |   |-- safety_gate.py          # Confirmation gates for dangerous operations
|   |   |-- health_monitor.py       # CPU/RAM/disk monitoring
|   |   |-- heartbeat_system.py     # Proactive check-ins
|   |   |-- error_reporter.py       # Error logging
|   |
|   |-- OpenClaw-Inspired
|   |   |-- model_failover.py       # Auth rotation + fallback chains
|   |   |-- event_hooks.py          # Event dispatch (20 types)
|   |   |-- context_compaction.py   # Auto context management
|   |   |-- workflow_pipelines.py   # Deterministic pipelines
|   |   |-- heartbeat_system.py     # Periodic check-ins
|   |
|   |-- Advanced
|   |   |-- code_sandbox.py         # RestrictedPython execution environment
|   |   |-- image_generation.py     # DALL-E / Stable Diffusion
|   |   |-- self_modifier.py        # Self-modifying code engine
|   |   |-- skill_generator.py      # Dynamic skill generation
|   |   |-- api_server.py           # FastAPI backend + WebSocket gateway (/ws)
|   |
|   |-- agents/                     # Specialized task agents
|       |-- flight_agent.py         # Flight booking
|       |-- hotel_agent.py          # Hotel search
|       |-- product_agent.py        # Product research
|       |-- email_agent.py          # Email composition
|       |-- calendar_agent.py       # Calendar management
|       |-- restaurant_agent.py     # Restaurant discovery
|       |-- package_tracking_agent.py
|       |-- agent_memory.py         # Shared agent context
|
|-- frontend/                      # Next.js/TypeScript web frontend
|   |-- src/app/page.tsx           # Chat page
|   |-- src/app/models/page.tsx    # Models page
|   |-- src/app/settings/page.tsx  # Settings page
|   |-- src/lib/ws-client.ts       # WebSocket client
|   |-- src/types/ws-protocol.ts   # WS message types
|   |-- Dockerfile                 # Frontend container
|
|-- web/                            # Legacy web dashboard
|   |-- index.html                  # Single-page chat interface (WebSocket, dark theme, streaming)
|
|-- plugins/                        # Plugin system
|   |-- marketplace_index.json      # 5 seed plugins
|
|-- data/                           # Runtime persistent data
|   |-- conversations/              # Chat history (JSON per day)
|   |-- voice_sessions/             # Voice session logs
|
|-- assets/                         # Logo and icons
|-- config/                         # OAuth credentials + prompt templates
|-- logs/                           # Application logs
|-- tests/                          # Test suite (74+ files, including pytest suite)
|   |-- test_phase2_modules.py      # 67 tests covering Phase 1-4 modules
```

---

## Configuration

Copy `.env.example` to `.env` and configure your API keys.

### Required (at least one)

```env
GEMINI_API_KEY=your_key          # Google AI Studio (free)
GROQ_API_KEY=your_key            # console.groq.com (free)
```

### Optional AI Providers

```env
ANTHROPIC_API_KEY=your_key       # Anthropic Claude models
OPENAI_API_KEY=your_key          # OpenAI GPT models
MISTRAL_API_KEY=your_key         # Mistral AI models
XAI_API_KEY=your_key             # xAI Grok models
DEEPSEEK_API_KEY=your_key        # DeepSeek models
TOGETHER_API_KEY=your_key        # Together AI models
FIREWORKS_API_KEY=your_key       # Fireworks AI models
LOCAL_OLLAMA_URL=http://localhost:11434    # Install Ollama locally
KAGGLE_URL=https://your-ngrok-url         # Kaggle notebook + ngrok
OLLAMA_CLOUD_URL=https://api.ollama.cloud/v1
OLLAMA_CLOUD_KEY=your_key
```

### Rate Limiting (per-provider)

```env
GROQ_RPM=30                      # Requests per minute
GROQ_RPD=14400                   # Requests per day
ANTHROPIC_RPM=60
ANTHROPIC_RPD=10000
# ... see .env.example for all providers
```

### Messaging Connectors

```env
TELEGRAM_BOT_TOKEN=your_token    # Telegram bot
DISCORD_BOT_TOKEN=your_token     # Discord bot
SLACK_BOT_TOKEN=your_token       # Slack app
TWILIO_ACCOUNT_SID=your_sid      # WhatsApp (Twilio)
TWILIO_AUTH_TOKEN=your_token
MATTERMOST_URL=https://...       # Mattermost
MATTERMOST_TOKEN=your_token
TEAMS_APP_ID=your_id             # Microsoft Teams
LINE_CHANNEL_SECRET=your_secret  # LINE
SIGNAL_CLI_URL=http://...        # Signal
MATRIX_HOMESERVER=https://...    # Matrix / Element
```

### Optional Integrations

```env
OPENWEATHER_API_KEY=your_key     # Weather briefings
SPOTIFY_CLIENT_ID=your_id        # Spotify control
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_long_lived_token   # Smart home
```

### Plugin Marketplace

```env
PLUGIN_INDEX_URL=https://...     # Remote marketplace index URL
PLUGIN_INDEX_FILE=plugins/marketplace_index.json  # Local index
```

See [`.env.example`](.env.example) for the complete reference (~400 lines) with all options.

---

## Web Dashboard & Next.js Frontend

LADA includes two web interfaces:

### Legacy Web Dashboard

1. Start the API server (launches alongside the main application, or independently)
2. Open your browser and navigate to `http://localhost:<port>/dashboard`

Features: Real-time chat via WebSocket (`/ws`), model selector dropdown, dark theme, streaming messages, markdown rendering, source chips.

### Next.js Frontend

A full TypeScript/React web application with 3 pages:

```powershell
cd frontend && npm install && npm run dev    # Starts on port 3000
```

Or via Docker:
```powershell
docker-compose up frontend                   # Starts on port 3000
```

Features: Chat page with streaming responses, Models page to browse all 36 models across 12 providers, Settings page for configuration.

### Docker Deployment (Full Stack)

```powershell
docker-compose up                            # Starts all services
```

| Service | Port | Description |
|---------|------|-------------|
| lada | 5000 | Python backend (FastAPI + WebSocket) |
| ollama | 11434 | Local AI models |
| chromadb | 8000 | Vector memory |
| frontend | 3000 | Next.js web app |

---

## Voice Commands

### System (instant, no AI needed)
```
"set volume to 50"              "take a screenshot"
"mute" / "max volume"           "battery status"
"set brightness to 70"          "system info"
"open notepad"                  "lock screen"
"close chrome"                  "shutdown in 60 seconds"
```

### Music
```
"play music"                    "what's playing"
"pause" / "next song"           "shuffle on"
```

### Smart Home
```
"lights on" / "lights off"      "set temperature to 22"
"dim to 50%"                    "discover devices"
```

### AI Queries
```
"explain quantum computing"     "write a Python sort function"
"search the web for AI news"    "summarize this article"
```

### Compound
```
"set volume to 30 and then open spotify"
"take a screenshot and then open paint"
```

### Automation
```
"go to amazon.com and search for headphones"
"start heartbeat"
"search memory for yesterday"
```

---

## Modes

```powershell
python lada_desktop_app.py   # GUI mode (recommended)
python main.py gui           # Same as above
python main.py voice         # Voice-only mode (microphone)
python main.py text          # Text-only CLI mode
python main.py status        # Show system and backend status
```

---

## GUI

ChatGPT-style dark interface with:

- **Header**: Model selector dropdown, backend status, voice toggle, mic button
- **Sidebar**: Chat history with search, voice sessions, settings, export
- **Chat area**: Welcome screen with suggestion chips, streaming messages, markdown rendering
- **Input bar**: Text input, file attach (+), quick actions (/), send button, web search toggle
- **Overlays**: Voice input overlay, Comet task progress overlay
- **Global hotkeys**: Ctrl+Shift+L (show), Ctrl+Shift+V (voice), Ctrl+Shift+Space (quick command)

---

## Troubleshooting

### "Can't connect to AI"
- Check `.env` has valid API keys for at least one backend
- For Local Ollama: run `ollama serve` first
- Verify internet for cloud backends

### Voice not working
- Check microphone permissions in Windows Settings
- Install audio: `pip install pyaudio SpeechRecognition pyttsx3`
- Test mic: `python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"`

### GUI not launching
- Install PyQt5: `pip install PyQt5`
- Check error output in terminal

### File attachment not reading PDF
- Install: `pip install pdfplumber` or `pip install python-docx`

---

## Testing

### Pytest Suite

```powershell
pytest tests/test_phase2_modules.py -v
```

This runs 67 tests covering model registry, tool registry, error types, token counter, session manager, provider base, provider manager, context manager, advanced planner, router Phase 2 integration, and API server WebSocket.

### End-to-End Validation

```powershell
python test_e2e_complete.py
```

This runs comprehensive checks on all modules, imports, AI routing, voice NLU patterns, and system commands.

---

## Platform

- **Primary**: Windows 10/11
- **Runtime**: Python 3.11+
- **GUI**: PyQt5

---

## License

MIT License -- Free for personal and commercial use.
