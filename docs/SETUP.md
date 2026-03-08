# LADA Setup Guide

Complete setup instructions for **LADA** (Language Agnostic Digital Assistant).

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11+ | 3.12 |
| OS | Windows 10 | Windows 11 |
| RAM | 8 GB | 16 GB (for local AI models) |
| Disk | 2 GB | 10 GB (with Ollama models) |
| GPU | None | NVIDIA (for local inference) |
| Internet | Required for cloud AI | Optional with Ollama |

---

## One-Click Install

```powershell
# 1. Open PowerShell in the LADA directory
cd C:\JarvisAI

# 2. Run the installer
python setup_lada.py
```

The installer will:
1. Check Python version (3.11+ required)
2. Create a virtual environment (`jarvis_env/`)
3. Install all 131 dependencies
4. Create `.env` from `.env.example`
5. Prompt for your Gemini API key (free)
6. Create data directories
7. Download NLP models
8. Verify all core modules
9. Optionally pull Ollama models

### Minimal Install (no GUI, no voice)

```powershell
python setup_lada.py --minimal
```

Installs only 6 core packages for text/API mode.

### Verify Existing Install

```powershell
python setup_lada.py --verify
```

Checks all modules without installing anything.

---

## Manual Install

If you prefer to set up manually:

```powershell
# 1. Create virtual environment
python -m venv jarvis_env
.\jarvis_env\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download NLP model
python -m spacy download en_core_web_sm

# 4. Create configuration
copy .env.example .env
# Edit .env with your API keys

# 5. Create data directories
mkdir data\conversations, data\sessions, data\rag_knowledge, logs, plugins
```

---

## Configuration (.env)

Copy `.env.example` to `.env` and configure at least one AI provider.

### Minimum Setup (Free)

```env
# Google Gemini - free tier, fast, reliable
# Get key: https://aistudio.google.com/apikey
GEMINI_API_KEY=your_key_here
```

### Recommended Setup

```env
# Primary: Gemini (free)
GEMINI_API_KEY=your_key

# Fast fallback: Groq (free tier)
# Get key: https://console.groq.com/keys
GROQ_API_KEY=your_key

# Local offline: Ollama (no key needed)
LOCAL_OLLAMA_URL=http://localhost:11434
LOCAL_FAST_MODEL=qwen2.5:7b-instruct-q4_K_M
LOCAL_SMART_MODEL=llama3.1:8b-instruct-q4_K_M
```

### Full Setup (All Providers)

See `.env.example` for all ~400 configuration options including:
- 12 AI providers (OpenAI, Anthropic, Mistral, xAI, DeepSeek, Together, Fireworks, Cerebras)
- Per-provider rate limits (RPM, RPD)
- Voice settings (language, speed, engine)
- Messaging connectors (Telegram, Discord, Slack, WhatsApp, etc.)
- Plugin marketplace settings
- Docker deployment options

---

## Running LADA

### Web UI (Recommended)

```powershell
python main.py webui
```

Opens your browser at `http://localhost:5000/app` with the full chat interface. Password-protected — enter your password (default: `lada1434`) to access. Accessible from any device on your local network via the Network URL shown at startup. Features: streaming chat, model selector, voice, sessions, cost tracking, plans, workflows.

### Desktop GUI

```powershell
python main.py gui
```

Or double-click `LADA-GUI.bat`.

PyQt5 desktop app with voice control, system integration, and all features.

### Text Mode

```powershell
python main.py text
```

Terminal-based chat. No GUI dependencies needed.

### Voice Mode

```powershell
python main.py voice
```

Always-on voice with "Hey LADA" wake word. Supports Tamil + English.

### Docker (Full Stack)

```powershell
docker-compose up -d
```

Starts: LADA API (8080), Ollama (11434), ChromaDB (8000), Next.js (3000).

### Batch Launchers (Windows)

- `LADA-WebUI.bat` - Browser interface
- `LADA-GUI.bat` - Desktop app

---

## Verify Installation

```powershell
python main.py verify
```

Tests all 100+ module imports, API endpoints, and provider connections. Reports status of every component.

---

## Local AI with Ollama

For offline, private AI without API keys:

```powershell
# 1. Install Ollama
# Download from: https://ollama.com/download

# 2. Pull recommended models
ollama pull qwen2.5:7b-instruct-q4_K_M     # Fast tier (~4 GB)
ollama pull llama3.1:8b-instruct-q4_K_M     # Smart tier (~5 GB)

# 3. Set in .env
# LOCAL_OLLAMA_URL=http://localhost:11434
# LOCAL_FAST_MODEL=qwen2.5:7b-instruct-q4_K_M
# LOCAL_SMART_MODEL=llama3.1:8b-instruct-q4_K_M
```

LADA auto-detects Ollama at startup and uses local models as the primary backend.

---

## Troubleshooting

### "No AI provider configured"

Add at least one API key to `.env`. Fastest: get a free Gemini key from https://aistudio.google.com/apikey

### PyQt5 import error

```powershell
pip install PyQt5
```

On some systems, you may need the Visual C++ Redistributable.

### Voice not working

- Windows: voice uses SAPI5 (built-in), should work out of the box
- Check `VOICE_ENGINE=sapi5` in `.env`
- For Tamil, set `TAMIL_MODE=true`

### Port 5000 in use

```env
LADA_API_PORT=5001
```

### Module import errors

Run the verifier to identify which modules are failing:

```powershell
python setup_lada.py --verify
```

### Ollama connection refused

Make sure Ollama is running:

```powershell
ollama serve
```

### WebSocket connection failed

Check that the API server is running and the port matches what the web UI expects. Default: `ws://localhost:5000/ws`.

### Web UI password

The web UI is password-protected. Default password: `lada1434`. Change it in `.env`:

```env
LADA_WEB_PASSWORD=your_password_here
LADA_SESSION_TTL=86400
```

### Remote access from other devices

The web UI binds to `0.0.0.0` so it's accessible from any device on your local network. When you run `python main.py webui`, it prints both local and network URLs. Open the network URL on your phone or other computer and enter your password.

### Public internet access

Access LADA from anywhere on the internet — free, no port forwarding, automatic HTTPS.

#### Tailscale Funnel (free permanent URL)

100% free, permanent URL, no domain purchase needed. You get a URL like `https://your-pc.tailnet1234.ts.net/app` that never changes.

1. **Install Tailscale** (one time):
   ```powershell
   winget install tailscale.tailscale
   ```

2. **Create a free Tailscale account** and log in:
   ```powershell
   tailscale login
   ```
   This opens your browser. Sign in with Google, GitHub, or Microsoft — completely free.

3. **Enable Funnel** on your account:
   The first time you run `tailscale funnel`, it will give you a URL to enable Funnel. Open it, click "Enable", done. This is a one-time step.

4. **Enable in LADA** — in `.env`:
   ```env
   LADA_TAILSCALE_FUNNEL=true
   ```

5. **Start LADA WebUI**:
   ```powershell
   python main.py webui
   ```

6. LADA prints your permanent URL:
   ```
   Public:  https://lalit.tailnet1234.ts.net/app
   ```

This URL is permanent — it never changes. Open it from your phone, tablet, any device. Password-protected via `LADA_WEB_PASSWORD`.

---

## Project Structure

```
C:\JarvisAI\
  main.py                  # Entry point (5 modes)
  lada_desktop_app.py      # PyQt5 GUI
  lada_webui.py            # Web UI launcher
  lada_ai_router.py        # AI routing engine
  lada_jarvis_core.py      # Command processor
  lada_memory.py           # Conversation memory
  models.json              # 36 AI models, 12 providers
  .env                     # Your configuration
  requirements.txt         # Python dependencies

  modules/                 # 100+ feature modules
    api_server.py          # FastAPI + WebSocket
    providers/             # AI provider adapters
    messaging/             # 12 communication channels
    advanced_planner.py    # Multi-step task planning
    workflow_engine.py     # Action orchestration
    task_automation.py     # Task choreography
    skill_generator.py     # AI-powered plugin creation
    ...

  web/
    lada_app.html          # Browser-based UI

  frontend/                # Next.js web frontend
  plugins/                 # Plugin directory
  data/                    # Conversations, sessions, memory
```

---

## Getting Help

- Check `ARCHITECTURE.md` for system design details
- Check `CLAUDE.md` for development context
- Check `OPENCLAW_ANALYSIS.md` for feature comparison
- Run `python main.py verify` to diagnose issues
