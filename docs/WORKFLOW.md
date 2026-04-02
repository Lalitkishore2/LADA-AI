# LADA Complete Workflow

Last updated: 2026-04-02
Status: Active reference

This document is the canonical end-to-end workflow reference for how LADA executes work across desktop, CLI, API, web, and messaging channels.

## 1. Runtime entry points

### Desktop GUI mode
- Entry: `lada_desktop_app.py`
- Primary path:
  1. User input (typed chat, attached files, voice trigger)
  2. `_check_system_command()` decides command vs AI route
  3. System commands go to `JarvisCommandProcessor.process()`
  4. AI queries go to `HybridAIRouter.query()` or stream path
  5. Response saved to memory and rendered in UI

### CLI mode
- Entry: `main.py`
- Path:
  1. Listen for text/voice command
  2. Route system commands through command processor
  3. Route knowledge queries through AI router
  4. Speak or print response
  5. Save interaction in memory

### API mode
- Entry: `modules/api_server.py`
- Path:
  1. FastAPI app bootstraps router set under `modules/api/routers/`
  2. Auth/session checks happen in router dependencies
  3. `chat` and `openai_compat` routes call AI router/provider manager
  4. `app`, `marketplace`, `orchestration` routes invoke domain modules

### WebUI mode
- Entry: `lada_webui.py` (launch helper), frontend under `frontend/`
- Path:
  1. Launch API server
  2. Load web app
  3. Authenticate session token
  4. Communicate via REST + WebSocket

### Messaging connectors
- Entry set: `modules/messaging/*_connector.py`
- Path:
  1. Connector receives platform event
  2. Message normalized by router
  3. Routed into command processor / AI router
  4. Response sent back through platform SDK

## 2. Core command execution workflow

## 2.1 Router split
The key split is command execution vs model reasoning.

- Command path: local actions, automation, integrations
- AI path: analysis, generation, open-domain reasoning

Decision gate:
- `lada_desktop_app.py` `_check_system_command()`
- `lada_jarvis_core.py` `process()`

## 2.2 Executor dispatch order
`JarvisCommandProcessor` dispatches in this order:
1. WorkflowExecutor
2. ProductivityExecutor
3. BrowserExecutor
4. DesktopExecutor
5. SystemExecutor
6. AppExecutor
7. WebMediaExecutor
8. AgentExecutor

Contract:
- Each executor returns `(handled: bool, response: str)`.
- First `handled=True` short-circuits dispatch.

## 2.3 Service registry behavior
- Registry file: `core/services.py`
- Build path: `build_default_registry()`
- Load policy: lazy import + probe status
- Rule: optional module failures should degrade gracefully without crashing startup.

## 3. AI routing workflow

### 3.1 Router structure
- File: `lada_ai_router.py`
- Provider orchestration: `modules/providers/provider_manager.py`

### 3.2 Model selection
- Source of truth: `models.json`
- Tier classes: `fast`, `balanced`, `smart`, `reasoning`, `coding`
- Fallback principle: degrade down tier chain when needed

### 3.3 Provider protocol adapters
- OpenAI-compatible adapter
- Anthropic adapter
- Google adapter
- Ollama adapter

### 3.4 Request lifecycle
1. Receive prompt and metadata
2. Analyze complexity / route intent
3. Select provider + model
4. Apply rate-limit and health checks
5. Send request (stream or non-stream)
6. Track usage and estimated cost
7. Persist memory and session state

## 4. Memory and context workflow

### 4.1 Durable memory
- File: `lada_memory.py`
- Core class: `MemorySystem`
- Conversation format: per-day JSON + preference/history stores

### 4.2 Retrieval context
- Vector memory: `modules/vector_memory.py`
- Document retrieval: `modules/rag_engine.py`
- Router injects compact relevant context into model prompt

### 4.3 Cache behavior
- Cache is only used in constrained early-session conditions
- Internal agent calls disable cache/web search to avoid loop contamination

## 5. Voice workflow

### 5.1 Speech stack
- Main voice runtime: `voice_tamil_free.py`
- Wake/continuous listening: `modules/continuous_listener.py`

### 5.2 Voice control gate
- Desktop-level voice enable flag controls listening + speaking flow.

### 5.3 Alexa bridge workflow
- Active integration: `integrations/alexa_server.py`
- Startup helper path from desktop app launches Alexa bridge on port `5001`
- Bridge forwards Alexa command intents to local LADA API

## 6. API and WebSocket workflow (high-level)

### 6.1 REST routes
- `auth`: token/session lifecycle
- `chat`: user chat and streaming chat endpoints
- `app`: dashboard/session metadata
- `marketplace`: plugin catalog and operations
- `orchestration`: plans/workflows/tasks
- `openai_compat`: OpenAI-style `/v1` endpoints

### 6.2 WebSocket
- Endpoint: `/ws`
- Features:
  - token-authenticated session
  - streaming response chunks
  - per-session rate and size safeguards

(Endpoint-level protocol details are documented in `docs/API_WEBSOCKET_REFERENCE.md`.)

## 7. Plugin and tool workflow

### 7.1 Plugin lifecycle
- Discovery and management modules:
  - `modules/plugin_system.py`
  - `modules/plugin_marketplace.py`
- Marketplace seed index: `plugins/marketplace_index.json`

### 7.2 AI tool invocation
- Registry: `modules/tool_registry.py`
- Handlers: `modules/tool_handlers.py`
- Agent loop: `modules/ai_command_agent.py`

Tool loop pattern:
1. AI proposes tool call
2. Handler validates and executes
3. Result returns to model loop
4. Loop ends on final answer or round limit

## 8. Failure and safety workflow

### 8.1 Safety controls
- Primary module: `modules/safety_controller.py`
- Optional gate: `modules/safety_gate.py`

### 8.2 Rate limiting and recovery
- Module: `modules/rate_limiter.py`
- Controls:
  - per-provider RPM/RPD token bucket
  - circuit-break behavior for unstable providers

### 8.3 Graceful degradation policy
LADA should continue functioning when optional dependencies are missing, disabling only the specific feature path.

## 9. Operational workflows by user intent

### 9.1 Local command intent
Examples: open app, change brightness, set timer
- Preferred path: executor-based local action
- Fallback: AI explanation if action not executable

### 9.2 Knowledge intent
Examples: explain concept, compare tools, summarize topic
- Preferred path: AI router with optional research augmentation

### 9.3 Hybrid intent
Examples: research and then perform action
- Path: AI command agent chooses tool calls + reasoning turns

## 10. Architecture invariants (must not break)

1. Executor contract remains `(bool, str)`.
2. Provider manager remains the only model orchestration authority.
3. Service registry remains lazy and non-fatal for optional modules.
4. Memory persistence remains append-safe and backward-compatible.
5. WebSocket auth/rate controls remain enabled.
6. Tier fallback remains available for provider resilience.

## 11. Current archived optional integrations

Archived under `archived/integrations/`:
- `openclaw_gateway.py`
- `openclaw_skills.py`
- `alexa_hybrid.py`
- `moltbot_controller.py`
- `moltbot_firmware.ino`

Reason:
- Not currently wired into active runtime for this deployment profile.
- Preserved for future reactivation with explicit re-wiring.

Runtime note:
- `modules/agents/robot_agent.py` attempts optional MoltBot loading dynamically and degrades cleanly when archived integrations are unavailable.

## 12. Recommended reading order

1. `docs/WORKFLOW.md` (this file)
2. `docs/API_WEBSOCKET_REFERENCE.md`
3. `docs/CLEANUP_PLAN.md`
4. `docs/VALIDATION_PLAYBOOK.md`
5. `docs/ARCHITECTURE.md` (legacy deep background)
