# LADA Architecture

Technical reference for the internal design, data flows, and module interactions in LADA.

Current canonical operational references:
- `docs/WORKFLOW.md`
- `docs/API_WEBSOCKET_REFERENCE.md`
- `docs/VALIDATION_PLAYBOOK.md`
- `docs/CLEANUP_PLAN.md`

---

## System Overview

LADA is structured as a layered desktop application with multiple interface modes (GUI, voice, text, web dashboard, Next.js frontend, 9 messaging connectors) sharing a common AI routing engine, command processor, and memory system. AI queries pass through the ProviderManager routing system with tier-based model selection and fallback. Per-provider rate limiting (TokenBucket + CircuitBreaker) protects against API quota exhaustion.

```
                        User
             /    |    |    |    \
        GUI  Voice  CLI  Web  Messaging (9 connectors)
         |     |    |    |       |
         +-----+----+   |       |
               |         |       |
    +----------+---------+-------+
    |     Command Processor      |
    |     Pattern matching       |
    |     50+ system cmds        |
    +----------+-----------------+
               |
     (no match)|
               v
    +---------------------------+
    |    Rate Limiter           |  (rate_limiter.py)
    |    TokenBucket + Circuit  |
    +----------+----------------+
               |
               v
    +---------------------------+
    |    Provider Manager       |  (provider_manager.py)
    |    35 models, 11 provs    |
    |    4 protocol adapters    |
    |    tier-based routing     |
    +----------+----------------+
               |
     (all fail)|
               v
    +---------------------------+
    |  Legacy AI Router         |  (lada_ai_router.py)
    |  5 backends               |
    |  failover chain           |
    +----------+----------------+
               |
    +----------+----------------+
    |   Memory System           |  (lada_memory.py)
    |   Conversations           |
    |   Preferences             |
    +---------------------------+
```

---

## Core Components

### 1. Entry Points

#### `main.py` -- CLI Launcher

The CLI entry point. Supports four modes:

| Mode | Command | Description |
|------|---------|-------------|
| voice | `python main.py voice` | Microphone input, spoken responses |
| text | `python main.py text` | Terminal REPL |
| gui | `python main.py gui` | PyQt5 desktop app (recommended) |
| status | `python main.py status` | Print backend health and exit |

GUI mode takes a fast path -- it imports `lada_desktop_app.main()` directly without initializing the full CLI stack (voice engine, memory) to reduce startup time.

#### `lada_desktop_app.py` -- Desktop GUI

The main application. PyQt5-based with:

- **LadaApp (QMainWindow)**: Main window with sidebar, chat area, input bar
- **StreamingAIWorker (QThread)**: Background thread that streams AI responses via Qt signals
- **AIWorker (QThread)**: Non-streaming AI worker for one-shot queries
- **ContinuousListener**: Background thread for always-on voice input
- **CometOverlay**: Transparent overlay for autonomous agent progress

Key initialization order:
1. Load environment variables
2. Initialize HybridAIRouter (independent try/except)
3. Initialize FreeNaturalVoice (independent try/except, with pyttsx3 fallback)
4. Initialize JarvisCommandProcessor
5. Load chat history, set up UI
6. Lazy-check backend availability on first query

#### Web Dashboard (`web/index.html`)

A single-page chat interface served at `/dashboard` by the API server:

- WebSocket-based real-time communication (connects to `/ws`)
- Dark theme with model selector dropdown
- Markdown rendering for AI responses
- Lightweight alternative to the full PyQt5 desktop app

#### Next.js Frontend (`frontend/`)

A TypeScript/React web application with three pages:

- **Chat** (`src/app/page.tsx`): Real-time chat via WebSocket with streaming responses
- **Models** (`src/app/models/page.tsx`): Model browser showing all configured providers and models
- **Settings** (`src/app/settings/page.tsx`): Configuration management

Uses Tailwind CSS for styling, typed WebSocket client (`src/lib/ws-client.ts`), and has its own Docker container (port 3000).

### 2. AI Routing Engine

**File**: `lada_ai_router.py`
**Class**: `HybridAIRouter`

AI queries are routed through two layers. The Phase 2 Provider Manager is the primary path, offering config-driven model selection across 35 models and 12 providers. If no provider is configured or all providers fail, the system falls back to the legacy backend chain.

#### Layer 1: Provider Manager (Phase 2)

**File**: `modules/provider_manager.py`
**Class**: `ProviderManager`

The Provider Manager auto-configures available providers from environment variables and `models.json`. It selects models using tier-based routing with fallback chains:

```
Tier Fallback Chains:
    reasoning --> smart --> balanced --> fast
    coding    --> smart --> balanced --> fast
    smart     --> balanced --> fast
    balanced  --> fast
    fast      (no fallback)
```

When a query arrives, its complexity tier determines which models are eligible. The manager tries each matching model in priority order, falling through the chain if a tier has no available provider.

Four protocol adapters handle all provider communication:

| Adapter | Providers Served |
|---------|-----------------|
| `openai_provider.py` | OpenAI, Groq, Mistral, xAI, Cerebras, HuggingFace |
| `anthropic_provider.py` | Anthropic |
| `google_provider.py` | Google Generative AI |
| `ollama_provider.py` | Ollama Local, Ollama Cloud |

Each adapter extends `BaseProvider` (defined in `base_provider.py`) and implements a uniform interface for `generate()`, `stream()`, and `health_check()`. The base module defines shared data types: `ProviderConfig`, `ProviderResponse`, `StreamChunk`, and `ProviderStatus`.

Health monitoring runs automatically. The manager tracks provider status and cost accumulation across requests via the `CostTracker` singleton.

#### Layer 2: Legacy Backend Chain (Fallback)

```
1. Local Ollama    (localhost:11434)     -- fastest, offline, private
2. Google Gemini   (gemini-2.0-flash)   -- powerful, free tier
3. Kaggle T4 GPU   (ngrok tunnel)       -- most powerful, requires setup
4. Ollama Cloud    (ollama.com)         -- cloud fallback
5. Groq Cloud      (api.groq.com)      -- fast cloud backup, free tier
```

Each backend has a health check method (`_check_ollama_local()`, `_check_gemini()`, etc.) and a query method (`_query_local_ollama()`, `_query_gemini()`, etc.).

#### Query Flow

```
query(command)
    |
    +--> _ensure_backends_checked()     # lazy init, runs once
    +--> check response cache           # return cached if hit
    +--> _is_knowledge_query()?
    |       yes --> web_search.search()  # inject real-time context
    +--> _analyze_query_complexity()     # fast/balanced/smart/reasoning/coding
    |
    +--> ProviderManager.generate()     # Phase 2: tier-based routing
    |       try matching tier models in priority order
    |       fall through tier chain on failure
    |       success --> cache + return
    |       all fail --> continue to legacy
    |
    +--> try legacy backends in priority order:
    |       _query_local_ollama()
    |       _query_gemini()
    |       _query_kaggle()
    |       _query_ollama_cloud()       # selects model by complexity
    |       _query_groq()
    +--> cache response
    +--> return response
```

#### Streaming

`stream_query()` yields chunks via generator. The GUI's `StreamingAIWorker` consumes chunks and emits Qt signals (`chunk_ready`, `finished`) for the typing effect. The WebSocket gateway streams chunks as `chat.chunk` messages followed by a `chat.done` message.

#### Query Complexity Analysis

| Complexity | Criteria | Ollama Cloud Model |
|-----------|---------|-------------------|
| fast | Low word count, matches greeting set | llama3.2:3b |
| balanced | General queries | llama3.1:8b |
| smart | "how to", "explain" | llama3.1:70b |
| reasoning | "analyze", "compare" | qwen2.5:32b |
| coding | Code-related keywords | qwen2.5-coder:14b |

#### Web Search Integration

Web search is triggered only when BOTH conditions are met:
1. The user has explicitly enabled the web search toggle (`web_search_enabled = True`)
2. The query needs real-time data (`_is_knowledge_query()` returns True)

`_is_knowledge_query()` matches only queries needing current/live data:
- Temporal queries: "latest", "current", "today", "2025", "recent"
- Price/cost queries: "price of", "how much is", "buy"
- Live data: "weather", "stock price", "exchange rate", "flight status"

Conceptual questions ("what is X", "explain Y", "tell me about Z") go to AI reasoning, not web search.

#### Deep Research Mode

For complex research queries, `DeepResearchEngine` performs:
1. Query decomposition into sub-queries
2. Parallel multi-source search
3. AI synthesis of findings
4. Inline citation injection via `CitationEngine`

### 3. Command Processor

**File**: `lada_jarvis_core.py`
**Class**: `JarvisCommandProcessor`

Routes user input to system commands or AI. Uses a cascading pattern-matching approach:

```
process(command)
    |
    +--> VoiceNLU patterns (50+)    # volume, brightness, apps, etc.
    |       match --> execute directly via SystemController
    |       no match --> continue
    |
    +--> Agent patterns              # spotify, smart home, email, etc.
    |       match --> delegate to agent module
    |       no match --> continue
    |
    +--> AI Router                   # complex/knowledge queries
            query() --> return response
```

#### Integrated Modules (all optional, graceful degradation)

| Module | Import Flag | Purpose |
|--------|------------|---------|
| SystemController | SYSTEM_OK | Volume, brightness, WiFi, power |
| CometBrowserAgent | BROWSER_OK | Browser automation and web actions |
| FileSystemController | FILE_OK | File search, create, move |
| NLUEngine | NLU_OK | Intent + entity extraction (spaCy) |
| SafetyController | SAFETY_OK | Confirmation gates, undo |
| MemorySystem | MEMORY_OK | Conversation persistence |
| TaskChoreographer | TASK_OK | Multi-step workflows |
| WorkflowEngine | WORKFLOW_OK | Pipeline execution |
| RoutineManager | ROUTINE_OK | Saved routines |
| WindowManager | WINDOW_MANAGER_OK | Window snap, focus |
| GUIAutomator | GUI_AUTOMATOR_OK | Screen automation |
| BrowserTabController | BROWSER_TAB_OK | Tab management |
| GmailController | GMAIL_OK | Email read/send/search |
| CalendarController | CALENDAR_OK | Events, reminders |
| TaskOrchestrator | TASK_ORCHESTRATOR_OK | Parallel task execution |
| PatternLearner | PATTERN_LEARNER_OK | User behavior learning |
| ProactiveAgent | PROACTIVE_AGENT_OK | Background alerts |
| FlightAgent | FLIGHT_AGENT_OK | Flight booking |
| HotelAgent | HOTEL_AGENT_OK | Hotel search |
| ProductAgent | PRODUCT_AGENT_OK | Product research |
| RestaurantAgent | RESTAURANT_AGENT_OK | Restaurant discovery |
| EmailAgent | EMAIL_AGENT_OK | Email composition |
| CalendarAgent | CALENDAR_AGENT_OK | Calendar management |

### 4. Memory System

**File**: `lada_memory.py`
**Class**: `MemorySystem`

#### Data Model

```python
ConversationMessage:
    role: str           # 'user' or 'assistant'
    content: str        # message text
    timestamp: str      # ISO 8601
    language: str       # 'en', 'ta'
    metadata: dict      # custom fields

UserPreferences:
    preferred_language: str
    voice_speed: int
    voice_volume: float
    topics_of_interest: list
    response_style: str    # 'concise' | 'balanced' | 'detailed'
    custom_settings: dict
```

#### Storage Layout

```
data/
    conversations/          # one JSON file per day
        2026-02-18.json
        2026-02-17.json
    voice_sessions/         # voice conversation logs
    lada_memory.json        # long-term facts and context
    lada_memory_backup.json # automatic backup
    preferences.json        # learned user preferences
```

#### Auto-Save

A background thread saves memory to disk every 300 seconds (configurable via `MEMORY_AUTOSAVE_INTERVAL`). On shutdown, `MemorySystem.shutdown()` persists all data immediately.

### 5. Voice Engine

**File**: `voice_tamil_free.py`
**Class**: `FreeNaturalVoice`

| Component | Online | Offline |
|-----------|--------|---------|
| TTS | gTTS (Google) | pyttsx3 (SAPI5) |
| STT | Google Speech Recognition | Whisper (if installed) |

The voice engine detects language (Tamil vs English) and responds in the same language. When the primary `voice_tamil_free` module is unavailable, the desktop app creates a fallback `FreeNaturalVoice` class using pyttsx3 + speech_recognition.

**ContinuousListener** (`modules/continuous_listener.py`):
- Runs a background thread capturing microphone input
- State machine: STANDBY (waiting for wake word) / ACTIVE (processing commands)
- Fires `wake_triggered` Qt signal when wake word detected
- Pauses during TTS playback to avoid self-triggering

### 6. Provider System

**Directory**: `modules/providers/`

The provider system is the Phase 2 config-driven AI routing layer. It replaces hardcoded backend logic with a registry of models and protocol adapters.

#### Base Provider (`base_provider.py`)

Defines the `BaseProvider` ABC that all protocol adapters implement. Shared data types:

- **ProviderConfig**: Provider connection settings (API key, base URL, timeout)
- **ProviderResponse**: Standardized response wrapper (text, model, usage, latency)
- **StreamChunk**: Individual streaming token with metadata
- **ProviderStatus**: Health state (available, last_check, error_count)

#### Protocol Adapters

| File | Class | Protocol | Notes |
|------|-------|----------|-------|
| `openai_provider.py` | OpenAIProvider | OpenAI Chat Completions API | Serves any OpenAI-compatible endpoint (Groq, Mistral, xAI, DeepSeek, Together AI, Fireworks AI, Cerebras, HuggingFace) |
| `anthropic_provider.py` | AnthropicProvider | Anthropic Messages API | Claude models |
| `google_provider.py` | GoogleProvider | Google Generative AI | Gemini models |
| `ollama_provider.py` | OllamaProvider | Ollama REST API | Local and cloud Ollama instances |

#### Provider Manager (`provider_manager.py`)

Central orchestrator. On initialization:
1. Reads `models.json` for the full model registry
2. Scans environment variables for API keys
3. Auto-configures providers that have valid credentials
4. Builds tier-based routing tables with fallback chains

At query time:
1. Receives a complexity tier from the query analyzer
2. Selects candidate models matching that tier
3. Tries each in priority order
4. Falls through the tier chain (e.g., reasoning to smart to balanced) on failure
5. Tracks health status and accumulates cost per request

#### Model Registry (`modules/model_registry.py` + `models.json`)

`models.json` contains 35 models across 12 providers:

| Provider | Examples |
|----------|----------|
| Google | Gemini models |
| Groq | LLaMA, Mixtral |
| Ollama Local | Local LLaMA, Qwen, CodeLlama |
| Ollama Cloud | Cloud-hosted Ollama models |
| Anthropic | Claude models |
| Mistral | Mistral/Mixtral models |
| xAI | Grok models |
| OpenAI | GPT models |
| DeepSeek | DeepSeek Chat, DeepSeek Coder |
| Together AI | Open-source models (Mixtral, LLaMA, etc.) |
| Fireworks AI | Fast inference models |
| Kaggle | Kaggle T4 GPU models (via ngrok tunnel) |

Each model entry specifies: `id`, `name`, `provider`, `tier` (fast/balanced/smart/reasoning/coding), `context_window`, `cost_input`, `cost_output`, `base_url`.

`model_registry.py` provides `ProviderEntry` dataclass with fields: `type`, `name`, `config_keys`, `local`, `priority`. It handles loading and querying the model catalog.

#### Token Counter (`modules/token_counter.py`)

- **TokenCounter**: Whitespace-based token estimation for prompt sizing
- **CostTracker**: Singleton tracking per-request costs and cumulative totals across providers
- Context window fit checking to prevent exceeding model limits

#### Context Manager (`modules/context_manager.py`)

- **ContextBudget**: Calculates available token budget per model based on context window and reserved output tokens
- Message fitting and compaction to stay within context limits
- Usage ratio tracking for monitoring context utilization

#### Session Manager (`modules/session_manager.py`)

- **SessionType** enum: `GUI_CHAT`, `VOICE`, `CLI`, `TELEGRAM`
- Per-session context, conversation history, and token tracking
- Session lifecycle management (create, resume, expire)

#### Error Types (`modules/error_types.py`)

- **ErrorCategory** enum: `TIMEOUT`, `AUTH_FAILED`, `RATE_LIMITED`, `MODEL_UNAVAILABLE`, `MALFORMED_RESPONSE`
- Factory functions: `timeout_error()`, `auth_error()`, `rate_limit_error()` for consistent error creation
- **ErrorTracker** singleton for recording errors and querying error history by category or provider

### 7. Tool Registry

**File**: `modules/tool_registry.py`

Centralized registry for all tools the AI can invoke during task execution:

- **ToolDefinition**: Tool name, description, JSON schema parameters, handler function
- **PermissionLevel**: `SAFE`, `MODERATE`, `DANGEROUS`, `CRITICAL` -- determines confirmation requirements
- **ToolCategory**: `SYSTEM`, `BROWSER`, `FILE`, and others for organizational grouping
- Fuzzy matching for intent-to-tool resolution when the AI or user references a tool by description rather than exact name

### 8. Advanced Planner

**File**: `modules/advanced_planner.py`

Structured plan execution for multi-step tasks:

- **PlanNode**: Individual step with status tracking (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `VERIFYING`)
- Dependency graph between nodes to enforce execution order
- Plan revision on failure -- when a node fails, the planner can restructure remaining steps

### 9. WebSocket Gateway

**File**: `modules/api_server.py` (WebSocket endpoint)

The API server exposes a `/ws` WebSocket endpoint for real-time bidirectional messaging:

- JSON protocol with message types: `chat`, `chat.chunk`, `chat.done`, `agent`, `system`, `ping`/`pong`
- Per-connection session tracking via the Session Manager
- Streaming support -- AI responses arrive as a sequence of `chat.chunk` messages followed by `chat.done`
- Serves the web dashboard at `/dashboard`

### 10. Rate Limiter

**File**: `modules/rate_limiter.py` (273 lines)

Per-provider rate limiting with two mechanisms:

- **TokenBucket**: Enforces requests-per-minute (RPM) and requests-per-day (RPD) limits per provider. Configured via environment variables (e.g., `GROQ_RPM=30`, `GROQ_RPD=14400`).
- **CircuitBreaker**: Tracks consecutive failures per provider. After a threshold of failures, the circuit "opens" and blocks requests for a cooldown period. Auto-recovers after cooldown expires.

The rate limiter is checked before every AI provider call. If a provider is rate-limited or circuit-broken, the router skips to the next available provider.

### 11. Plugin Marketplace

**File**: `modules/plugin_marketplace.py` (690 lines)

Plugin lifecycle management beyond the basic plugin system:

- **Search**: Query the marketplace index for plugins by name, category, or keyword
- **Install**: Download and install plugins from the marketplace index
- **Uninstall**: Remove installed plugins cleanly
- **Update**: Check for and apply plugin updates
- **Index**: `plugins/marketplace_index.json` contains 5 seed plugins

### 12. Response Caching

Response caching only activates when `len(conversation_history) == 0` (first message in a session). This prevents stale/repeated responses during ongoing conversations. Cache key uses full `prompt.lower().strip()` (not truncated).

---

## Module Architecture

All modules live in `modules/` and follow a consistent pattern:

1. **Conditional import**: Every module is wrapped in `try/except ImportError` with a `MODULE_OK` flag
2. **Factory function**: Most modules export a `create_*()` factory alongside the class
3. **Graceful degradation**: Missing modules disable their features without crashing the app
4. **ENV configuration**: Modules read settings from environment variables via `os.getenv()`

### Module Categories

#### Provider System (6 modules)
- `providers/base_provider.py` -- BaseProvider ABC, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
- `providers/openai_provider.py` -- OpenAI-compatible adapter (also Groq, Mistral, xAI, DeepSeek, Together AI, Fireworks AI, Cerebras, HuggingFace)
- `providers/anthropic_provider.py` -- Anthropic Messages API adapter
- `providers/google_provider.py` -- Google Generative AI adapter
- `providers/ollama_provider.py` -- Ollama REST API adapter (local + cloud)
- `provider_manager.py` -- Central orchestrator, auto-config, tier routing, health monitoring, cost tracking

#### Model & Token Management (3 modules)
- `model_registry.py` -- ProviderEntry dataclass, model catalog loader, queries against models.json
- `token_counter.py` -- TokenCounter estimation, CostTracker singleton, context window fit checks
- `context_manager.py` -- ContextBudget calculation, message fitting/compaction, usage ratio tracking

#### Session & Error Handling (3 modules)
- `session_manager.py` -- SessionType enum, per-session context/history/tokens, lifecycle management
- `error_types.py` -- ErrorCategory enum, factory functions, ErrorTracker singleton
- `tool_registry.py` -- ToolDefinition, PermissionLevel, ToolCategory, fuzzy intent matching

#### Voice & Input (6 modules)
- `voice_nlu.py` -- 50+ regex patterns for voice command recognition
- `continuous_listener.py` -- Always-on microphone with wake word
- `hybrid_stt.py` -- Google + Whisper speech-to-text
- `wake_word.py` -- Wake word detection (Silero VAD)
- `advanced_voice.py` -- Voice cloning, emotion detection
- `realtime_voice.py` -- LiveKit real-time streaming

#### System Control (5 modules)
- `system_control.py` -- Volume, brightness, WiFi, power, process management
- `window_manager.py` -- Window focus, snap, minimize, maximize
- `advanced_system_control.py` -- Registry, services, deep system access
- `desktop_control.py` -- Virtual desktops
- `focus_modes.py` -- Do-not-disturb, research, coding modes

#### AI & NLP (7 modules)
- `nlu_engine.py` -- Intent classification + entity extraction (spaCy)
- `sentiment_analysis.py` -- Emotion detection (TextBlob)
- `deep_research.py` -- Multi-source research with sub-query decomposition
- `citation_engine.py` -- MLA/APA/Chicago formatted citations
- `dynamic_prompts.py` -- Context-aware prompt engineering
- `context_compaction.py` -- Long-context compression before window limits
- `token_optimizer.py` -- Token counting and budget management

#### Planning & Orchestration (2 modules)
- `advanced_planner.py` -- PlanNode with dependency graph, status tracking, plan revision on failure
- `task_planner.py` -- Plan decomposition

#### Browser & Web (6 modules)
- `web_search.py` -- DuckDuckGo search with result formatting
- `browser_automation.py` -- Selenium-based browser control
- `browser_tab_controller.py` -- Multi-tab management
- `multi_tab_orchestrator.py` -- Multi-tab orchestration
- `page_vision.py` -- Page screenshot + OCR analysis
- `page_summarizer.py` -- Webpage content summarization

#### Autonomous Agents (6 modules)
- `comet_agent.py` -- See-Think-Act screen control loop
- `computer_use_agent.py` -- Vision-based GUI automation
- `agent_actions.py` -- Browser/email/calendar agent actions
- `agent_orchestrator.py` -- Multi-agent coordination
- `agent_collaboration.py` -- Agent-to-agent communication
- `proactive_agent.py` -- Battery warnings, reminder alerts

#### Task & Workflow (6 modules)
- `task_orchestrator.py` -- Parallel execution, DAG scheduling
- `event_hooks.py` -- Event dispatch and automation hooks
- `task_automation.py` -- Task choreography
- `workflow_engine.py` -- Workflow definition and execution
- `workflow_pipelines.py` -- Pipeline composition with approval gates
- `routine_manager.py` -- Save/load reusable routines

#### Integrations (7 modules)
- `spotify_controller.py` -- Spotify Web API (OAuth2 PKCE)
- `smart_home.py` -- Philips Hue + Home Assistant + Tuya
- `gmail_controller.py` -- Gmail read/send/search (OAuth2)
- `google_calendar.py` -- Calendar events and reminders
- `calendar_controller.py` -- Calendar operations
- `weather_briefing.py` -- OpenWeatherMap daily briefings
- `youtube_summarizer.py` -- YouTube transcript summarization

#### Memory & Learning (4 modules)
- `lada_memory.py` -- Conversation history storage
- `vector_memory.py` -- Semantic search with ChromaDB embeddings
- `mcp_client.py` -- Model Context Protocol client
- `pattern_learning.py` -- User behavior pattern learning

#### Files & Documents (6 modules)
- `file_operations.py` -- File search, create, move, delete
- `document_reader.py` -- PDF/DOCX/TXT parsing
- `file_encryption.py` -- Fernet + AES encryption
- `export_manager.py` -- CSV/PDF/DOCX export
- `markdown_renderer.py` -- Response formatting
- `rag_engine.py` -- Retrieval-Augmented Generation

#### Safety & Monitoring (6 modules)
- `safety_controller.py` -- Action validation + undo stack
- `safety_gate.py` -- Confirmation gates for dangerous actions
- `health_monitor.py` -- CPU/RAM/disk monitoring
- `heartbeat_system.py` -- Proactive periodic check-ins
- `error_reporter.py` -- Error logging and reporting

#### Advanced (8 modules)
- `code_sandbox.py` -- RestrictedPython safe execution
- `image_generation.py` -- Stability AI / Gemini Imagen
- `self_modifier.py` -- Self-modifying code engine (AST-based)
- `skill_generator.py` -- AI-generated skills from natural language
- `plugin_system.py` -- Plugin discovery, loading, activation
- `plugin_marketplace.py` -- Plugin marketplace (install/uninstall/update/search, 690 lines)
- `rate_limiter.py` -- Per-provider TokenBucket + CircuitBreaker (273 lines)
- `api_server.py` -- FastAPI REST backend + WebSocket gateway

#### Specialized Agents (`modules/agents/`, 7 modules)
- `flight_agent.py`, `hotel_agent.py`, `product_agent.py`
- `email_agent.py`, `calendar_agent.py`, `restaurant_agent.py`
- `agent_memory.py` -- Shared agent context

#### Messaging Connectors (`modules/messaging/`, 11 modules)
- `base_connector.py` -- ABC for platform connectors
- `telegram_connector.py`, `discord_connector.py`
- `whatsapp_connector.py`, `slack_connector.py`
- `mattermost_connector.py` -- Mattermost bot (155 lines)
- `teams_connector.py` -- Microsoft Teams bot (113 lines)
- `line_connector.py` -- LINE Messaging (135 lines)
- `signal_connector.py` -- Signal via signal-cli REST (139 lines)
- `matrix_connector.py` -- Matrix / Element (140 lines)
- `message_router.py` -- Routes incoming messages to command processor

---

## Data Flows

### Flow 1: User Message (GUI)

```
1. User types in QTextEdit, presses Enter/Send
2. LadaApp._send() captures text
3. _check_system_command() -> JarvisCommandProcessor
4. VoiceNLU checks 50+ patterns
5. If match: execute SystemController method, return response
6. If no match: create StreamingAIWorker(QThread)
7. Worker calls HybridAIRouter.stream_query()
   a. Check cache -> return if hit
   b. Check if knowledge query -> run web search
   c. ProviderManager tries tier-matched models
   d. If Provider Manager fails, try legacy backends in priority order
   e. Yield response chunks
8. Chunks arrive via chunk_ready signal -> append to chat bubble
9. finished signal -> save to conversation history + memory
```

### Flow 2: Voice Command

```
1. ContinuousListener runs background thread
2. speech_recognition captures audio
3. Google STT converts to text (Whisper offline fallback)
4. wake_triggered Qt signal fires with text
5. LadaApp._on_wake_command() checks wake/stop phrases
6. If active: strip wake prefix
7. Route to _check_system_command() or AI
8. Response spoken via FreeNaturalVoice.speak()
9. Listener paused during speech, resumes after
```

### Flow 3: File Attachment

```
1. User clicks [+] button -> QFileDialog
2. Selected file checked against 50MB size guard
3. Content extracted based on extension:
   - .pdf -> pdfplumber/PyMuPDF (first 12KB)
   - .docx -> python-docx (first 12KB)
   - .py/.js/.ts/etc -> text read (first 12KB)
   - .png/.jpg/etc -> stored as image type
4. File info stored in self.attached_files list
5. On send: files prepended to prompt as [File: name]\ncontent
6. Images noted as [Attached image: name]
7. StreamingAIWorker processes enriched prompt
```

### Flow 4: Autonomous Agent (Comet)

```
1. User types "go to amazon.com and search for headphones"
   or uses trigger phrases like "control my screen", "do it for me"
2. _is_agent_task() detects agent trigger patterns
3. CometAgent.execute(task) begins See-Think-Act loop
4. THINK: Screenshot captured -> sent to AI router
   (web search and caching disabled for internal THINK queries)
   AI returns next action as structured output
5. ACT: pyautogui executes action (click, type, scroll)
6. VERIFY: New screenshot compared to expected state
7. If failed: retry with alternative strategy (up to 3 retries)
8. Repeat up to 50 steps
9. Progress shown on CometOverlay (transparent overlay)
10. User can click Stop button to abort
```

Comet capabilities are logged at startup:
`[LADA Core] Comet Autonomous Agent loaded (capabilities: browser, gui, vision, screenshot, pyautogui)`

### Flow 5: Backend Failover (Legacy)

```
1. Query arrives at HybridAIRouter.query()
2. Try Local Ollama -> timeout 1.5s health check
   - Success: query local, return
   - Fail: mark unavailable, continue
3. Try Gemini -> gemini-2.0-flash via google-genai
   - Success: return
   - Fail: continue
4. Try Kaggle T4 -> ngrok tunnel
   - Success: return
   - Fail: continue
5. Try Ollama Cloud -> model selected by complexity
   - Success: return
   - Fail: continue
6. Try Groq -> llama-3.3-70b-versatile
   - Success: return
   - Fail: return error message
```

### Flow 6: WebSocket Message (Web Dashboard)

```
1. Client opens WebSocket connection to /ws
2. Server assigns session via SessionManager
3. Client sends JSON: { "type": "chat", "content": "..." }
4. Server routes through Command Processor
5. If system command: return { "type": "system", "content": "..." }
6. If AI query: stream response as chat.chunk messages
   a. { "type": "chat.chunk", "content": "partial..." }
   b. { "type": "chat.chunk", "content": "more..." }
   c. { "type": "chat.done", "content": "full response" }
7. Client renders chunks incrementally with markdown
8. Keepalive via ping/pong messages
```

### Flow 7: Provider Manager Query

```
1. Query arrives with complexity tier (e.g., "reasoning")
2. ProviderManager looks up models matching the tier
3. For each candidate model (sorted by provider priority):
   a. Check provider health status
   b. ContextManager verifies message fits context window
   c. TokenCounter estimates input token count
   d. Protocol adapter sends request (OpenAI/Anthropic/Google/Ollama)
   e. On success: CostTracker records cost, return ProviderResponse
   f. On failure: ErrorTracker records error, try next model
4. If no model in tier succeeds, fall through tier chain:
   reasoning -> smart -> balanced -> fast
5. If entire chain exhausted, return None (caller falls to legacy)
```

---

## Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| Strategy | HybridAIRouter backends | Swap AI providers transparently |
| Chain of Responsibility | Backend failover, tier fallback chains | Try backends/tiers in sequence |
| Observer | Qt signals, event_hooks.py, WebSocket messages | Decouple event producers/consumers |
| Factory | `create_*()` module functions, error factory functions | Centralize object creation |
| Composite | JarvisCommandProcessor | Uniform interface over 20+ modules |
| Lazy Initialization | Backend health checks, provider auto-config | Defer work until first query |
| Graceful Degradation | All module imports | Missing deps disable features, not crash |
| Registry | model_registry (models.json), tool_registry | Central catalog with lookup/query interface |
| Adapter | Protocol adapters (OpenAI, Anthropic, Google, Ollama) | Uniform BaseProvider interface over different APIs |
| Singleton | CostTracker, ErrorTracker | Single shared instance for cross-cutting concerns |

---

## Threading Model

| Thread | Purpose | Lifecycle |
|--------|---------|-----------|
| Main (Qt) | GUI event loop, signal dispatch | App lifetime |
| StreamingAIWorker | AI query + streaming response | Per-query, auto-terminates |
| ContinuousListener | Microphone capture + STT | Toggle on/off via voice button |
| MemorySystem autosave | Periodic disk persistence | App lifetime, daemon thread |
| Backend health check | Parallel availability probes | Runs once on first query |
| CometAgent | Autonomous task execution | Per-task, stoppable |
| HeartbeatSystem | Periodic proactive check-ins | Optional, app lifetime |
| TaskScheduler | APScheduler background jobs | Optional, app lifetime |
| WebSocket connection | Per-client bidirectional messaging | Per-connection, server-managed |

All worker threads are daemon threads or use Qt's `QThread` with proper signal-based communication. No shared mutable state between threads -- communication is via Qt signals, thread-safe queues, or `threading.Event`.

---

## Configuration

All configuration is via environment variables loaded from `.env` by `python-dotenv`. See `.env.example` for the full reference.

Key configuration groups:
- **AI Backends**: URLs, API keys, model names, timeouts for 12 providers
- **Provider System**: API keys for 12 providers (auto-detected), model tier preferences
- **Rate Limiting**: Per-provider RPM/RPD limits (e.g., `GROQ_RPM=30`, `GROQ_RPD=14400`)
- **Voice**: Engine, rate, volume, wake words, language settings
- **Paths**: Data, logs, screenshots, cache directories
- **Safety**: Protected paths, command blacklist, privacy mode
- **Features**: Enable/disable flags for every module
- **Performance**: Cache size/TTL, thread counts, queue sizes
- **Messaging**: Bot tokens for Telegram, Discord, Slack, WhatsApp, Mattermost, Teams, LINE, Signal, Matrix
- **Plugins**: Marketplace index URL, local index file path
- **DM Pairing**: Pairing policy, approved senders file, away messages

---

## Security Model

### Protected Operations
- **Protected paths**: `C:\Windows`, `C:\Program Files`, `C:\Windows\System32` -- blocked from modification
- **Command blacklist**: `format disk`, `delete system32`, `rm -rf /` -- blocked from execution
- **Confirmation gates**: Shutdown, restart, file deletion require user confirmation
- **Undo system**: Last 50 actions stored for rollback

### Privacy Modes
| Mode | Behavior |
|------|----------|
| PUBLIC | Normal operation, full logging |
| PRIVATE | Reduced logging, no telemetry |
| SECURE | Minimal logging, auto-redaction of sensitive data |

### API Key Storage
API keys are stored in `.env` (not committed to version control). The `.env.example` template contains placeholder values only.

---

## Testing

Test files are in `tests/` (73 files). Run the full suite:

```powershell
python test_e2e_complete.py     # End-to-end validation
pytest tests/                    # Unit tests (including 67+ Phase 2 provider/routing tests)
```

The E2E test validates:
- All module imports succeed
- AI routing to each backend
- Voice NLU pattern matching
- System command execution
- Memory persistence
- File attachment processing

The Phase 2 pytest suite covers:
- Provider adapter initialization and configuration
- Model registry loading and tier queries
- ProviderManager auto-configuration from environment
- Tier-based routing and fallback chain traversal
- Token counting and cost tracking
- Context budget calculation and message fitting
- Session lifecycle management
- Error categorization and tracking
- Health monitoring and provider status transitions
