# LADA — Language Agnostic Digital Assistant

LADA is a unified AI assistant platform with desktop control, API/WebSocket services, voice, tasks/workflows, and multi-provider model routing in one codebase.

## Project status

- **Unified repo layout** (Python runtime + imported upstream TS ecosystem organized in-place)
- **LADA-first runtime naming** across active paths
- **Core regression coverage active** for tasks, gateway protocol, agent runtime, subagents, and browser compatibility

## Quick start (Python runtime)

```powershell
cd C:\lada ai
python -m venv jarvis_env
.\jarvis_env\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python lada_desktop_app.py
```

Optional launchers:

```powershell
.\LADA-GUI.bat
.\LADA-WebUI.bat
.\LADA-Full.bat
.\LADA-RemoteBridge.bat
```

## Main entrypoints

- `lada_desktop_app.py` — Desktop app (PyQt)
- `lada_webui.py` — Web UI runtime
- `main.py` — CLI/runtime bootstrap
- `modules/api_server.py` — FastAPI + WebSocket service
- `modules/remote_bridge_client.py` — Local bridge for Render web remote-control

## Render remote-control bridge (website -> your laptop)

Render cannot directly control your physical laptop session. Use the built-in bridge:

1. Deploy Web UI/API on Render with `LADA_REMOTE_CONTROL_ENABLED=true`.
2. Set a stable web password (`LADA_WEB_PASSWORD`) on Render.
3. On your laptop, set:
   - `LADA_REMOTE_BRIDGE_SERVER_URL=https://your-render-url.onrender.com`
   - `LADA_REMOTE_BRIDGE_PASSWORD=<same LADA_WEB_PASSWORD>`
   - Optional (only if your API is mounted under a path): `LADA_REMOTE_BRIDGE_API_PREFIX=/api`
4. Start bridge locally:

```powershell
python main.py bridge
```

or double-click `LADA-RemoteBridge.bat`.

Remote commands can now be sent with `device_id` via `/remote/command`, and your laptop executes them through local Jarvis.

### On-demand mode (recommended for laptop performance)

Keep Render online, but only run the bridge when you want laptop control:

1. Do **not** auto-start bridge on boot/login.
2. Start bridge manually when needed (`LADA-RemoteBridge.bat` or `python main.py bridge`).
3. Stop bridge with `Ctrl+C` when done.

Optional low-overhead bridge tuning in `.env`:

```powershell
LADA_REMOTE_BRIDGE_IDLE_POLL_INTERVAL_SEC=8
LADA_REMOTE_BRIDGE_ACTIVE_POLL_INTERVAL_SEC=1
LADA_REMOTE_BRIDGE_HEARTBEAT_SEC=20
LADA_REMOTE_BRIDGE_RECONNECT_SEC=3
```

### Desktop app auto-bridge mode

If you want bridge to start when the desktop app opens, set:

```powershell
LADA_REMOTE_BRIDGE_AUTO_START_APP=true
```

Then open `lada_desktop_app.py`: the top header shows a **Bridge ON/OFF** toggle so you can stop/start it anytime.

## Repository layout (organized)

### Runtime core (Python)

- `core/` — executors and runtime services
- `modules/` — feature modules (AI routing, tasks, gateway protocol, plugins, subagents, approvals, etc.)
- `integrations/` — adapter integrations used by runtime
- `voice/` — voice pipeline and speech components
- `web/` — dashboard/web assets
- `tests/` — Python and integration tests

### Product/platform source (TS/JS and apps)

- `src/` — main TypeScript source tree
- `apps/` — platform apps (android/ios/macos/shared)
- `packages/` — package modules
- `extensions/` — extension code
- `frontend/` — Next.js frontend
- `ui/` — UI package/assets

### Project support

- `docs/` — architecture, operations, and implementation docs
- `scripts/` — build/release/dev scripts
- `skills/` — skill definitions
- `plugins/` — plugin data and marketplace content
- `config/`, `data/`, `assets/` — runtime/config assets

## Architecture summary

See [Codebase Stabilization Audit Summary (April 2026)](docs/AUDIT_SUMMARY_2026_04.md) for details on the latest structural and modular improvements.

1. Input comes from desktop UI, voice, API, connectors, or WebSocket.
2. Command routing determines system action vs AI query.
3. AI path goes through model/provider routing with failover and policy checks.
4. Task/workflow engine executes actions with status tracking and notifications.
5. Output is streamed to UI/API and persisted to memory/state stores.

## Development checks

```powershell
python -m compileall -q modules core integrations main.py lada_jarvis_core.py lada_desktop_app.py lada_webui.py
python -m pytest -c NUL tests/test_task_registry.py tests/test_agent_runtime.py tests/test_gateway_protocol.py tests/test_subagents_acp.py tests/test_lada_browser_executor.py -q
```

## Notes

- This repository intentionally contains both runtime Python modules and broader platform source trees.
- Active runtime behavior should be implemented under `core/`, `modules/`, `integrations/`, and related entrypoints.
