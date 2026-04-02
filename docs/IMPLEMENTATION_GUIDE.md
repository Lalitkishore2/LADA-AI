# LADA v10.0 - Implementation Complete & User Guide

> Note: This file contains historical rollout details. For current operational references, use:
> - `docs/WORKFLOW.md`
> - `docs/API_WEBSOCKET_REFERENCE.md`
> - `docs/VALIDATION_PLAYBOOK.md`
> - `docs/CLEANUP_PLAN.md`

## What Was Built

All 17 features from the gap analysis comparing LADA to OpenClaw.ai, Perplexity AI, and Comet autonomous agents have been implemented, plus additional enhancements:

### Phase 1: Foundation (5 features)
1. **Deep Research Engine** (`modules/deep_research.py`)
   - Multi-step query decomposition
   - Parallel searches across Wikipedia + DuckDuckGo
   - AI-powered synthesis of results

2. **Citation System** (`modules/citation_engine.py`)
   - Inline numbered citations [1][2][3]
   - Source badge generation
   - Bibliography formatting

3. **Plugin Registry** (`modules/plugin_system.py`)
   - YAML/JSON manifest-based plugin discovery
   - Lifecycle management (load/activate/deactivate/unload)
   - Capability registry for intent routing

4. **Agent Self-Correction** (enhanced `modules/comet_agent.py`)
   - State checkpointing before actions
   - AI-powered failure recovery
   - Alternatives with 3-retry loop

5. **Model Picker** (enhanced `lada_ai_router.py`)
   - `force_backend()`, `get_available_backends()`, `get_forced_backend()` methods
   - Allows user to override auto-selection

### Phase 2: Intelligence (5 features)
6. **Advanced Planner** (`modules/advanced_planner.py`)
   - Task decomposition into dependency graphs
   - Topological sort for parallel execution
   - AI-powered plan revision on failure

7. **Visual Grounding** (`modules/visual_grounding.py`)
   - Gemini Vision API for screenshot analysis
   - UI element identification with coordinates
   - OCR fallback

8. **Focus Modes** (`modules/focus_modes.py`)
   - 6 modes: GENERAL, ACADEMIC, CODE, WRITING, MATH, NEWS
   - Tailored search sources and system prompts per mode
   - Auto-detect mode from query

9. **Event Hooks + Pipelines** (`modules/event_hooks.py`, `modules/workflow_pipelines.py`)
   - Event-driven scheduling and automation hooks
   - Deterministic workflow/pipeline execution
   - Execution history and lifecycle hooks

10. **AI Skill Generator** (`modules/skill_generator.py`)
    - Generate plugins from natural language descriptions
    - Code sandbox validation
    - Auto-manifest generation

### Phase 3: Ecosystem (7 features)
11-14. **Messaging Connectors** (`modules/messaging/`)
    - `BaseConnector` abstract interface
    - 9 platform connectors: Telegram, Discord, WhatsApp, Slack, Mattermost, Teams, LINE, Signal, Matrix
    - `MessageRouter` for centralized routing
    - DM pairing (6-digit codes), away messages, admin approval

15. **Research Spaces** (`modules/research_spaces.py`)
    - Named collections for organizing research
    - Pin sources, add notes, attach files
    - Persistent context for AI queries

16. **Image Generation** (`modules/image_generation.py`)
    - Stability AI and Gemini Imagen backends
    - Save to `data/generated_images/`

17. **Voice Stack Consolidation** (`voice_tamil_free.py`, `voice/`)
   - Unified free/offline-capable TTS-STT pipeline
   - Optional premium engines are no longer hard-wired in core runtime

**BONUS:**
18. **Hot-Reload** (enhanced `modules/lazy_loader.py`)
    - `PluginWatcher` class with watchdog file monitoring
    - 500ms debounce to prevent rapid-fire reloads
    - Auto-reload on plugin file changes

19. **Demonstration Recording** (`modules/demonstration_recorder.py`)
    - Record mouse/keyboard + screenshots via pynput
    - Replay via GUIAutomator
    - AI-powered generalization into WorkflowEngine workflows

### Phase 4: LADA-X Super System Enhancements

20. **Model Expansion** -- 35 models across 12 providers (was 24/8)
    - Added DeepSeek, Together AI, Fireworks AI providers
    - 10 new model entries in `models.json`
    - All use existing `openai-completions` adapter (no new code)

21. **Per-Provider Rate Limiting** (`modules/rate_limiter.py`, 273 lines)
    - TokenBucket for RPM/RPD enforcement per provider
    - CircuitBreaker with auto-recovery after cooldown
    - Configurable via env vars (`GROQ_RPM`, `ANTHROPIC_RPD`, etc.)

22. **Plugin Marketplace** (`modules/plugin_marketplace.py`, 690 lines)
    - Install/uninstall/update/search plugins
    - Marketplace index at `plugins/marketplace_index.json` (5 seed plugins)
    - REST API endpoints for marketplace operations

23. **Next.js Frontend** (`frontend/`, ~2,591 lines)
    - TypeScript/React web app with Chat, Models, Settings pages
    - Typed WebSocket client for real-time streaming
    - Tailwind CSS dark theme, Docker deployment

24. **5 New Messaging Connectors**
    - Mattermost (`mattermost_connector.py`, 155 lines)
    - Microsoft Teams (`teams_connector.py`, 113 lines)
    - LINE (`line_connector.py`, 135 lines)
    - Signal (`signal_connector.py`, 139 lines)
    - Matrix/Element (`matrix_connector.py`, 140 lines)

25. **Docker Full Stack** (`docker-compose.yml`)
    - Python backend, Ollama, ChromaDB, Next.js frontend

### Phase 5: Bug Fixes & Improvements

26. **Web Search Logic Fix** (`lada_ai_router.py`)
    - `_is_knowledge_query()` now only matches real-time data queries
    - Changed `should_search` from `or` to `and` logic
    - Conceptual questions now go to AI reasoning, not web search

27. **Model Dropdown Phase 2 Integration** (`lada_desktop_app.py`)
    - `_load_models()` now calls `get_all_available_models()` from Phase 2
    - Stores model ID as QComboBox itemData, uses `currentData()` to read

28. **Comet Agent Improvements**
    - `_think()` disables web search and caching for internal queries
    - Broadened `_is_agent_task()` trigger patterns
    - Diagnostic capability logging at startup

29. **Response Cache Fix** (`lada_ai_router.py`)
    - Cache only activates for first message in session (empty history)
    - Full prompt as cache key (not truncated to 100 chars)

---

## How to Run LADA

### 1. Install Dependencies (One-Time Setup)
```bash
cd c:\JarvisAI
python setup_lada.py
```

This installs all core packages: PyQt5, requests, google-generativeai, pyautogui, etc.

### 2. Configure API Keys (Required for AI features)
Create a `.env` file in `c:\JarvisAI\` with your API keys:

```env
# Gemini (Google AI)
GEMINI_API_KEY=your_gemini_key_here

# Optional: Other AI backends (12 providers supported)
GROQ_API_KEY=your_groq_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here
MISTRAL_API_KEY=your_mistral_key_here
XAI_API_KEY=your_xai_key_here
DEEPSEEK_API_KEY=your_deepseek_key_here
TOGETHER_API_KEY=your_together_key_here
FIREWORKS_API_KEY=your_fireworks_key_here
KAGGLE_USERNAME=your_kaggle_username
KAGGLE_KEY=your_kaggle_key

# Optional: Rate limiting (per provider)
GROQ_RPM=30
GROQ_RPD=14400

# Optional: Premium features
ELEVENLABS_API_KEY=your_elevenlabs_key
STABILITY_API_KEY=your_stability_key

# Optional: Messaging platforms (9 connectors)
TELEGRAM_BOT_TOKEN=your_telegram_token
DISCORD_BOT_TOKEN=your_discord_token
SLACK_BOT_TOKEN=your_slack_token
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
MATTERMOST_URL=https://your-mattermost-server
MATTERMOST_TOKEN=your_token
TEAMS_APP_ID=your_teams_app_id
LINE_CHANNEL_SECRET=your_line_secret
SIGNAL_CLI_URL=http://localhost:8080
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@bot:matrix.org
MATRIX_ACCESS_TOKEN=your_token

# Optional: Plugin marketplace
PLUGIN_INDEX_FILE=plugins/marketplace_index.json
```

See `.env.example` for the complete reference (~400 lines).

### 3. Start the Desktop App
```bash
python lada_desktop_app.py
```

The app should open with the ChatGPT-style interface.

---

## Using The New Features

### Deep Research + Citations
Just ask complex questions in the chat:
```
"Compare solar vs wind energy for residential use"
"Explain quantum entanglement with sources"
```

Responses will include inline citations [1][2][3] with clickable badges.

### Focus Modes
Switch modes via the planned model picker dropdown (GUI integration pending):
- ACADEMIC: Scholarly sources, formal output
- CODE: Programming docs, GitHub, Stack Overflow
- WRITING: Grammar-focused, style guides
- MATH: LaTeX formatting, math resources
- NEWS: Recent articles, fact-checking

### Event Hooks and Pipelines
```python
from modules.event_hooks import get_hook_manager

hooks = get_hook_manager()
hooks.emit("workflow.triggered", {"name": "standup_reminder"})
```

### Plugins
Create a new plugin in `plugins/my_plugin/`:

**plugin.json:**
```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "entry_point": "main.py",
  "class_name": "MyPlugin",
  "capabilities": [
    {
      "name": "greet",
      "intent_keywords": ["hello", "hi", "greet"],
      "handler": "handle_greet"
    }
  ]
}
```

**main.py:**
```python
class MyPlugin:
    def handle_greet(self, query: str) -> str:
        return "Hello from my plugin!"
```

If hot-reload is enabled (watchdog installed), changes take effect immediately!

### Demonstration Recording
```python
from modules.demonstration_recorder import get_demonstration_recorder
recorder = get_demonstration_recorder()

# Start recording
recorder.start_recording("open_gmail")
# ... perform actions ...
demo = recorder.stop_recording()

# Replay
from modules.demonstration_recorder import DemonstrationPlayer
player = DemonstrationPlayer(gui_automator)
player.replay(demo)

# Generalize to workflow
from modules.demonstration_recorder import DemonstrationGeneralizer
gen = DemonstrationGeneralizer(ai_router)
workflow = gen.generalize(demo)
```

### Image Generation
```python
from modules.image_generation import get_image_generator
generator = get_image_generator(ai_router)
path = generator.generate("a serene mountain landscape at sunset")
```

### Research Spaces
```python
from modules.research_spaces import get_space_manager
spaces = get_space_manager()

# Create space
space_id = spaces.create_space("AI Research", "My AI research notes")

# Add sources
spaces.pin_source(space_id, "https://arxiv.org/abs/2103.00020", "GPT-3 Paper")

# Add notes
spaces.add_note(space_id, "Key insight: Few-shot learning emerges at scale")

# Get context for AI
context = spaces.get_context(space_id)
```

---

## Troubleshooting

### App Doesn't Open
1. **Check dependencies:**
   ```bash
   python setup_lada.py
   ```

2. **Check for errors:**
   ```bash
   python lada_desktop_app.py > app.log 2>&1
   type app.log
   ```

3. **Common issues:**
   - **PyQt5 not found**: Run `pip install PyQt5`
   - **Black screen**: Check GPU drivers, try windowed mode
   - **Crashes on start**: Missing API keys (check `.env`)

### Commands Not Working
1. **Test command processor directly:**
   ```bash
   python -c "from lada_jarvis_core import JarvisCommandProcessor; j = JarvisCommandProcessor(); print(j.process('open calculator'))"
   ```

2. **Check module loading:**
   - Look for `[LADA Core] X loaded` messages in console
   - Missing modules will show warnings but shouldn't stop the app

3. **Common command issues:**
   - "Open calculator" -> Success: True, opens Windows calculator
   - "Set volume to 50" -> Requires `pycaw` package
   - "Take screenshot" -> Works with pyautogui installed
   - "Search Google for X" -> Opens browser, searches

4. **NLU not working:**
   - The NLU engine requires `spacy` + model:
     ```bash
     pip install spacy
     python -m spacy download en_core_web_sm
     ```

### AI Not Responding
1. **Check API keys in `.env` file** (at least one of 12 providers needed)
2. **Test AI router:**
   ```bash
   python -c "from lada_ai_router import HybridAIRouter; r = HybridAIRouter(); print(r.query('test'))"
   ```

3. **Fallback order:**
   - Phase 2: ProviderManager tries tier-matched models across all 12 providers
   - Legacy: Gemini -> Groq -> Kaggle -> Ollama Cloud -> Ollama Local
   - If all fail, check internet connection + API quotas + rate limits

### Missing Optional Features
Many features are optional. Missing packages show warnings but don't break the app:
- **pytesseract**: OCR (text extraction from images)
- **opencv-python**: Advanced image matching
- **selenium**: Full browser automation
- **SpeechRecognition**: Voice input
- **pycaw/screen-brightness-control**: System control
- **watchdog**: Hot-reload
- **pynput**: Demonstration recording

Install as needed: `pip install watchdog pynput opencv-python pytesseract`

---

## Architecture Overview

### Key Files Modified
- `lada_ai_router.py`: Deep research, citation integration, force_backend methods, web search logic fix, cache fix
- `lada_desktop_app.py`: Phase 2 model dropdown integration, broadened Comet triggers
- `modules/comet_agent.py`: Checkpointing, self-correction, retry loops, web search/cache disabled in THINK phase
- `modules/lazy_loader.py`: PluginWatcher for hot-reload

### New Modules (29 features across 30+ files)
```
modules/
├── deep_research.py          # Perplexity-style multi-step search
├── citation_engine.py         # Numbered inline citations
├── plugin_system.py           # Manifest-based plugin registry
├── plugin_marketplace.py      # Plugin marketplace (install/uninstall/update, 690 lines)
├── advanced_planner.py        # Dependency graph planning
├── visual_grounding.py        # Gemini Vision for UI analysis
├── focus_modes.py             # Mode-specific search/prompts
├── event_hooks.py             # Event dispatch and triggers
├── skill_generator.py         # AI-generated plugins
├── rate_limiter.py            # Per-provider TokenBucket + CircuitBreaker (273 lines)
├── research_spaces.py         # Topic-based knowledge organization
├── image_generation.py        # Stability AI / Gemini Imagen
├── voice_tamil_free.py        # Primary free/offline voice stack
├── demonstration_recorder.py  # Mouse/keyboard recording + replay
└── messaging/                 # Multi-platform connectors (11 files)
    ├── __init__.py
    ├── base_connector.py
    ├── telegram_connector.py
    ├── discord_connector.py
    ├── whatsapp_connector.py
    ├── slack_connector.py
    ├── mattermost_connector.py  # Mattermost bot
    ├── teams_connector.py       # Microsoft Teams
    ├── line_connector.py        # LINE Messaging
    ├── signal_connector.py      # Signal (signal-cli)
    ├── matrix_connector.py      # Matrix / Element
    └── message_router.py

frontend/                      # Next.js/TypeScript web frontend (~2,591 lines)
├── src/app/page.tsx           # Chat page
├── src/app/models/page.tsx    # Models page
├── src/app/settings/page.tsx  # Settings page
├── src/lib/ws-client.ts       # WebSocket client
├── src/types/ws-protocol.ts   # WS message types
└── Dockerfile                 # Frontend container

plugins/
└── marketplace_index.json     # 5 seed plugins
```

### Design Principles
- **Conditional imports**: All dependencies wrapped in try/except - missing packages degrade gracefully
- **Singleton pattern**: `get_X()` functions for module instances
- **Async-first**: Messaging connectors are async with sync wrappers
- **Fail-safe**: Every module has fallback behavior

---

## Next Steps (Remaining GUI Integration)

Most features are fully wired into the backend and GUI. Remaining UI enhancements:

1. **Citation Source Panel** (B2)
   - Add source badge display below AI responses
   - Parse `get_source_badges()` from citation engine
   - Make badges clickable to open URLs

2. **Focus Mode Selector** (B3)
   - Add mode dropdown in settings
   - Initialize `FocusModeManager` in app
   - Pass mode to `ai_router.stream_query()`

3. **Research Spaces Sidebar** (B4)
   - Add left sidebar for space management
   - List spaces, create/delete/switch
   - Display pinned sources + notes

4. **Plugin Manager UI** (A1)
   - Settings panel for plugin enable/disable + marketplace browse
   - Status indicators (active/inactive/error)
   - Install/uninstall from marketplace

**Completed GUI integrations:**
- Model Picker Dropdown -- Phase 2 models loaded via `get_all_available_models()`, model ID stored as itemData
- Next.js Frontend -- Full web interface at port 3000 with Chat, Models, Settings
- Docker Full Stack -- docker-compose with lada + ollama + chromadb + frontend

---

## Support & Debugging

**Check status:**
```python
python -c "from lada_jarvis_core import JarvisCommandProcessor; j = JarvisCommandProcessor(); print('LADA Core OK')"
```

**Enable debug logging:**
Add to top of `lada_desktop_app.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Test individual modules:**
```bash
python modules/deep_research.py       # Deep research test
python modules/event_hooks.py         # Event hook test
python modules/plugin_system.py       # Plugin discovery test
```

**Get help:**
- Check `README.md` for feature overview
- Check `ARCHITECTURE.md` for detailed technical reference
- Check `CLAUDE.md` for AI copilot context
- Check module docstrings for API usage
