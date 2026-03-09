# LADA Refactor Plan — From Prototype to Production

Audited: 2026-03-08 | Baseline: commit b8d3b31

---

## Current State Summary

| Metric | Value |
|--------|-------|
| `lada_jarvis_core.py` | 4,933 lines, 1 god class, 58 try/except imports, 57 subsystems in `__init__` |
| `lada_desktop_app.py` | 6,192 lines, 17 classes, PyQt5 |
| `lada_ai_router.py` | 1,856 lines, ~1,000 lines legacy code, dual routing active |
| `modules/api_server.py` | 2,240 lines, 1 class, 8 route groups |
| Duplicate module groups | 24 files, 15,950 lines across 6 groups |
| Dependency injection | None (80+ try/except blocks, no ServiceContainer) |

---

## Phase 1: Kill Dual Routing (lada_ai_router.py)

**Goal**: Remove ~1,000 lines of legacy routing. Make ProviderManager the only AI path.

**Why first**: Every AI query flows through this file. Dual routing causes dual conversation histories, dual complexity analysis, untraceable response sources, and double memory.

### What to delete

| Code | Lines | Description |
|------|-------|-------------|
| `AIBackend` enum | 131-136 | 4 hardcoded backends |
| `BackendStatus` dataclass | 139-146 | Legacy status tracking |
| Legacy config in `__init__` | 170-197 | `local_ollama_url`, `gemini_api_key`, `ollama_cloud_*`, `groq_*` |
| `backend_status` dict + `gemini_client` init | 243-259 | Legacy state |
| `_analyze_query_complexity()` | 342-372 | Duplicate of `ProviderManager._analyze_complexity()` |
| `_get_best_cloud_model()` | 411-414 | Cloud model selector |
| `_check_all_backends()` | 416-437 | Legacy health checks |
| `_ensure_backends_checked()` | 439-450 | Lazy init for legacy checks |
| `_sync_ollama_cloud_models()` | 452-549 | Queries localhost for cloud stubs |
| `_check_ollama_local()` | 551-573 | Legacy health check |
| `_check_gemini()` | 575-601 | Legacy health check |
| `_check_ollama_cloud()` | 603-634 | Legacy health check |
| `_check_groq()` | 636-685 | Legacy health check |
| Legacy fallback in `query()` | 751-809 | Backend loop after Phase 2 fails |
| `get_backend_from_name()` legacy part | 823-848 | String-to-enum mapping |
| `_get_backend_priority()` | 850-875 | Priority ordering |
| `_is_backend_available()` | 877-894 | Availability check |
| `_query_ollama_local()` | 896-934 | Non-streaming query |
| `_query_gemini()` | 936-965 | Non-streaming query |
| `_query_ollama_cloud()` | 967-1025 | Non-streaming query |
| `_query_groq()` | 1027-1078 | Non-streaming query |
| `_build_context()` | 1080-1093 | Context builder for legacy |
| `get_status()` | 1095-1107 | Legacy status report |
| `force_backend()` | 1117-1123 | Force legacy backend |
| `get_available_backends()` | 1125-1137 | Legacy backend listing |
| `get_forced_backend()` | 1139-1141 | Getter |
| Legacy fallback in `stream_query()` | 1580-1618 | Streaming backend loop |
| `_stream_ollama_local()` | 1620-1684 | Streaming query |
| `_stream_gemini()` | 1686-1716 | Streaming query |
| `_stream_ollama_cloud()` | 1718-1773 | Streaming query |
| `_stream_groq()` | 1775-1836 | Streaming query |

### What to keep/modify

- `_use_phase2` flag — remove (always True now)
- `self.conversation_history` — remove; use only `ProviderManager.conversation_history`
- `query()` — simplify to only call `_query_via_provider_manager()`
- `stream_query()` — simplify to only call `_stream_via_provider_manager()`
- `get_backend_from_name()` — rewrite to map model names to Phase 2 model IDs only
- `get_status()` — rewrite to use `ProviderManager.check_all_health()`
- `get_available_backends()` — rewrite to use `ProviderManager.get_available_providers()`

### Callers to update

| File | What calls legacy | Fix |
|------|-------------------|-----|
| `lada_desktop_app.py` | `get_available_backends()`, `get_backend_from_name()`, `force_backend()` | Use new Phase 2 equivalents |
| `modules/api_server.py` | `get_status()`, `get_available_backends()` | Use new Phase 2 equivalents |
| `lada_jarvis_core.py` | `_ensure_backends_checked()` | Remove call |

### Unify conversation history

- Delete `self.conversation_history` from `HybridAIRouter`
- Add `get_history()` and `clear_history()` that delegate to `ProviderManager`
- Fix streaming path (line 1362, 1386) to write to `ProviderManager.conversation_history` instead of `self.conversation_history`

**Expected result**: `lada_ai_router.py` drops from 1,856 → ~850 lines.

---

## Phase 2: Split JarvisCommandProcessor (lada_jarvis_core.py)

**Goal**: Break the 4,933-line god class into domain-specific executors.

### Current `__init__` subsystems (57 total, grouped by domain)

**System/Hardware** (5): `system`, `advanced_system`, `window_manager`, `gui_automator`, `desktop_ctrl`/`win_ctrl`/`file_finder`/`smart_browser`
**Browser** (4): `browser`, `browser_tabs`, `multi_tab`, `page_summarizer`/`youtube_summarizer`
**Voice** (1): `realtime_voice`
**AI/Memory** (7): `_ai_router`, `vector_memory`, `rag_engine`, `mcp_client`, `prompt_builder`, `token_optimizer`, `context_compactor`
**Agents** (9): `agent`, `comet_agent`, `flight_agent`, `hotel_agent`, `product_agent`, `restaurant_agent`, `email_agent`, `calendar_agent`, `collab_hub`
**Productivity** (6): `gmail`, `calendar`, `spotify`, `smart_home`, `productivity`, `quick_actions`
**Task execution** (3): `tasks`, `task_orchestrator`, `pipeline_runner`
**Safety** (2): `safety`, `permission_system`
**Learning/Proactive** (4): `pattern_learner`, `proactive_agent`, `self_modifier`, `skill_generator`
**Infrastructure** (5): `memory`, `daily_memory`, `nlu`, `heartbeat`, `hook_manager`, `failover_chain`
**Workflows** (2): `workflow_engine`, `routine_manager`
**Other** (2): `vision`, `webhook_manager`, `computer_use`, `advanced_planner`

### Proposed split

```
lada_jarvis_core.py (facade, ~300 lines)
  └── process(command) dispatches to:

core/executors/
  ├── system_executor.py      ← system, advanced_system, window_manager, gui_automator, desktop_ctrl
  ├── browser_executor.py     ← browser, browser_tabs, multi_tab, page_summarizer, youtube_summarizer
  ├── media_executor.py       ← spotify
  ├── productivity_executor.py ← gmail, calendar, smart_home, productivity, quick_actions
  ├── agent_executor.py       ← all 6 agents + comet_agent + collab_hub
  ├── file_executor.py        ← file ops (search, create, delete)
  └── workflow_executor.py    ← tasks, task_orchestrator, workflows, routines, pipelines

core/
  ├── intent_router.py        ← NLU + regex pattern matching (extracted from process())
  ├── ai_bridge.py            ← _ai_router interactions, vector_memory, rag, mcp, prompt_builder
  └── safety_gate.py          ← safety, permission_system
```

### Migration strategy

1. Create `core/executors/` directory
2. Extract one executor at a time (start with `system_executor.py` — most self-contained)
3. Each executor gets the relevant subsystem `__init__` + methods
4. `JarvisCommandProcessor` becomes a thin facade: init creates executors, `process()` routes to them
5. No behavior change — same inputs, same outputs

### External API contract (preserve these)

```python
class JarvisCommandProcessor:
    def process(self, command: str) -> str           # Main entry — desktop + api_server + main.py
    def set_privacy_mode(self, enabled: bool)        # Desktop app
    def get_proactive_alerts(self) -> list            # Desktop app
```

---

## Phase 3: Consolidate Duplicate Modules

### 3a. Memory group (3 files → 1)

| Current | Lines | Status |
|---------|-------|--------|
| `lada_memory.py` | 764 | **KEEP** — modern v7.0, JSON, named sessions |
| `modules/memory_system.py` | 274 | **DELETE** — legacy v5.0, pickle-based |
| `modules/chat_manager.py` | 533 | **KEEP** — separate concern (UI message objects) |

**Action**: Migrate any unique features from `memory_system.py` (preference learning, pattern storage) into `lada_memory.py`. Update `lada_jarvis_core.py` import (line ~100) from `modules.memory_system` to `lada_memory`.

### 3b. Safety group (3 files → 1)

| Current | Lines | Used in production? |
|---------|-------|---------------------|
| `modules/safety_controller.py` | 601 | Yes — `modules/__init__.py`, core |
| `modules/safety_gate.py` | 395 | Yes — flight/hotel/product agents |
| `modules/permission_system.py` | 1,135 | **No** — only tests |

**Action**: Keep `safety_controller.py` as primary. Add browser-specific gating from `safety_gate.py` as a method/subclass. Delete `permission_system.py` (unused, 1,135 lines). Wire the consolidated safety into agents.

### 3c. Browser group (4 files → 3)

| Current | Lines | Status |
|---------|-------|--------|
| `modules/browser_control.py` | 282 | **DELETE** — v5.0, superseded by browser_automation |
| `modules/browser_automation.py` | 511 | **KEEP** — Playwright/Selenium |
| `modules/browser_tab_controller.py` | 801 | **KEEP** — Chrome DevTools Protocol |
| `modules/multi_tab_orchestrator.py` | 681 | **KEEP** — depends on tab_controller |

**Action**: Delete `browser_control.py`. Update `lada_jarvis_core.py` to use `browser_automation.py` instead.

### 3d. System control group (5 files → 3)

| Current | Lines | Overlap |
|---------|-------|---------|
| `modules/system_control.py` | 1,554 | **KEEP** — hardware (volume, brightness, WiFi, power) |
| `modules/advanced_system_control.py` | 915 | **KEEP** — file management |
| `modules/desktop_control.py` | 730 | **DELETE** — overlaps window_manager + advanced_system_control |
| `modules/window_manager.py` | 1,021 | **KEEP** — window/app control |
| `modules/gui_automator.py` | 972 | **KEEP** — GUI automation (Comet needs this) |

**Action**: Merge `desktop_control.py`'s unique features (file content search, smart browser) into `advanced_system_control.py` and `window_manager.py`. Delete `desktop_control.py`. Update imports in `lada_jarvis_core.py`.

### 3e. Task group (4 files → 2)

| Current | Lines | Used? |
|---------|-------|-------|
| `modules/task_automation.py` | 632 | Yes — core |
| `modules/task_orchestrator.py` | 1,055 | Yes — core |
| `modules/task_planner.py` | 324 | Yes — flight agent |
| `modules/task_scheduler.py` | 427 | **No** — zero production imports |

**Action**: Delete `task_scheduler.py` (unused). Keep the other three (they serve distinct roles: sequential, parallel, decomposition).

### 3f. Voice group (5 files → 3)

| Current | Lines | Used? |
|---------|-------|-------|
| `voice_tamil_free.py` | 839 | Yes — primary voice, desktop + main |
| `modules/hybrid_stt.py` | 195 | Yes — used by voice_tamil_free |
| `modules/advanced_voice.py` | 623 | Yes — api_server wake word |
| `modules/realtime_voice.py` | 471 | Yes — core realtime |
| `modules/elevenlabs_voice.py` | 215 | **No** — zero production imports |

**Action**: Delete `elevenlabs_voice.py` (unused). Keep the other four.

### Summary of deletions

| File to delete | Lines removed | Reason |
|----------------|---------------|--------|
| `modules/memory_system.py` | 274 | Superseded by `lada_memory.py` |
| `modules/permission_system.py` | 1,135 | Unused in production |
| `modules/browser_control.py` | 282 | Superseded by `browser_automation.py` |
| `modules/desktop_control.py` | 730 | Overlaps window_manager + advanced_system_control |
| `modules/task_scheduler.py` | 427 | Zero production imports |
| `modules/elevenlabs_voice.py` | 215 | Zero production imports |
| **Total** | **3,063** | |

---

## Phase 4: Split api_server.py into Routers

**Goal**: Break 2,240-line single class into FastAPI router modules.

### Current structure (all in `LADAAPIServer`)

| Route Group | Method | Lines | Endpoints |
|-------------|--------|-------|-----------|
| Auth | `_register_auth_routes()` | 246-330 | `/auth/*` |
| Core | `_register_routes()` | 332-898 | `/health`, `/chat`, `/chat/stream`, `/agent`, `/models`, `/conversations/*`, `/voice/*` |
| Marketplace | `_register_marketplace_routes()` | 899-982 | `/marketplace/*`, `/plugins` |
| WebSocket | `_register_websocket_gateway()` | 983-1461 | `/ws` (479 lines!) |
| Dashboard | `_register_dashboard()` | 1462-1481 | `/dashboard` |
| LADA App | `_register_lada_app_routes()` | 1482-1618 | `/app`, `/sessions/*`, `/cost`, `/providers` |
| Orchestration | `_register_orchestration_routes()` | 1619-1887 | `/plans/*`, `/workflows/*`, `/tasks/*`, `/skills/*` |
| OpenAI compat | `_register_openai_compat_routes()` | 1888-2198 | `/v1/models`, `/v1/chat/completions` |

### Proposed split

```
modules/api/
  ├── __init__.py              ← create_app(), LADAAPIServer (slim ~150 lines)
  ├── middleware.py             ← Auth middleware, CORS, session validation
  ├── models.py                ← Pydantic request/response models
  ├── routers/
  │   ├── auth.py              ← /auth/* (85 lines)
  │   ├── chat.py              ← /chat, /chat/stream, /conversations/* (~300 lines)
  │   ├── models.py            ← /models, /providers (~100 lines)
  │   ├── voice.py             ← /voice/* (~80 lines)
  │   ├── agents.py            ← /agent, /agents (~200 lines)
  │   ├── marketplace.py       ← /marketplace/*, /plugins (~85 lines)
  │   ├── orchestration.py     ← /plans/*, /workflows/*, /tasks/*, /skills/* (~270 lines)
  │   ├── openai_compat.py     ← /v1/models, /v1/chat/completions (~310 lines)
  │   ├── app.py               ← /app, /sessions/*, /cost, /dashboard (~160 lines)
  │   └── websocket.py         ← /ws gateway (~480 lines)
  └── deps.py                  ← Shared dependencies (get_router, get_jarvis, etc.)
```

### Migration strategy

1. Create `modules/api/` directory
2. Extract Pydantic models first (lines 44-109) → `modules/api/models.py`
3. Extract auth middleware → `modules/api/middleware.py`
4. Extract one router at a time, starting with self-contained ones (auth, marketplace)
5. Use FastAPI dependency injection (`Depends()`) for shared state
6. Keep `modules/api_server.py` as a thin import redirect for backwards compatibility

---

## Phase 5: Desktop App Improvements (lada_desktop_app.py)

**Note**: Full Tauri+Vue rewrite is a separate project. These are incremental fixes to the existing PyQt5 app.

### 5a. Model dropdown fix (already planned)

- Filter offline models (only show `available: True`)
- Group by provider with non-selectable headers
- Set `setMaxVisibleItems(15)` — no more full-screen dropdown
- Widen max width to 280px

### 5b. Streaming typing indicator

- Add animated dots or "thinking..." state while waiting for first token
- Clear indicator when streaming starts

### 5c. Separate styles from logic

- Extract the inline `setStyleSheet()` calls into a `styles.py` or `theme.py` module
- Single source of truth for colors, fonts, spacing

### 5d. Chat sidebar improvements

- Show dates on conversation entries
- Don't truncate titles excessively

---

## Phase 6: Replace try/except Imports with Explicit Dependencies

**Goal**: Replace 58+ try/except ImportError blocks with clear dependency declarations.

### Approach: Lightweight service registry (not full DI framework)

```python
# core/services.py
class Services:
    """Lazy-loading service registry with clear error messages."""

    def __init__(self):
        self._instances = {}
        self._available = {}

    def register(self, name: str, factory, required: bool = False):
        """Register a service factory. If required=True, fail at startup if import fails."""
        try:
            self._available[name] = True
            self._instances[name] = None  # lazy
            self._factories[name] = factory
        except ImportError as e:
            if required:
                raise RuntimeError(f"Required service '{name}' missing: {e}")
            self._available[name] = False
            logger.warning(f"Optional service '{name}' unavailable: {e}")

    def get(self, name: str):
        if not self._available.get(name):
            return None
        if self._instances[name] is None:
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def is_available(self, name: str) -> bool:
        return self._available.get(name, False)
```

### Migration strategy

1. Create `core/services.py` with `Services` class
2. Start with `lada_jarvis_core.py` — replace the 58 try/except blocks with `services.register()` calls
3. Replace `if SOME_OK:` checks with `if services.is_available('some'):`
4. Then do `lada_ai_router.py` (12 blocks) and `lada_desktop_app.py` (5 blocks)
5. Each service declares whether it's `required=True` (crash if missing) or optional (graceful skip)

---

## Execution Order & Dependencies

```
Phase 1: Kill dual routing ─────────────┐
                                         ├──→ Phase 5: Desktop fixes
Phase 3: Delete unused modules ──────────┤
                                         ├──→ Phase 2: Split god object
Phase 4: Split api_server.py ────────────┘
                                              Phase 6: Service registry
```

**Recommended order**:
1. **Phase 3** first — delete 3,063 lines of dead/superseded code (lowest risk, immediate cleanup)
2. **Phase 1** — kill dual routing (high impact, self-contained in one file)
3. **Phase 5a** — fix model dropdown (user-facing, quick win)
4. **Phase 4** — split api_server.py (mechanical refactor)
5. **Phase 2** — split god object (highest risk, most complex)
6. **Phase 6** — service registry (can be done incrementally alongside Phase 2)

---

## Verification Plan

After each phase:

1. `python -m py_compile <modified_files>` — syntax check
2. `pytest tests/ -v` — run existing tests
3. Manual smoke test:
   - `python lada_desktop_app.py` — desktop app launches, can chat
   - `python lada_webui.py` — web UI launches, can chat
   - Model selection works (auto and manual)
   - Streaming works
   - Voice works (if configured)
4. Deploy to Render — verify cloud deployment works

---

## Lines of Code Impact

| Phase | Lines Removed | Lines Added | Net Change |
|-------|---------------|-------------|------------|
| Phase 1: Kill dual routing | ~1,000 | ~50 (wrappers) | **-950** |
| Phase 2: Split god object | ~4,500 (from core) | ~4,800 (into modules) | +300 (boilerplate) |
| Phase 3: Delete unused modules | ~3,063 | 0 | **-3,063** |
| Phase 4: Split api_server | ~2,100 (from server) | ~2,200 (into routers) | +100 (boilerplate) |
| Phase 5: Desktop fixes | ~50 | ~100 | +50 |
| Phase 6: Service registry | ~200 (try/except blocks) | ~150 (registry) | **-50** |
| **Total** | | | **~-3,600 net** |
