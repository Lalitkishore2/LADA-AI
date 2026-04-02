# LADA Validation Playbook

Last updated: 2026-04-02
Status: Active validation reference

This playbook defines repeatable verification tiers after cleanup, refactor, or feature wiring changes.

## 1. Preconditions

1. Activate project environment.
2. Ensure at least one AI provider key is configured for AI-path checks.
3. Run from repository root.

## 2. Fast validation (2-5 minutes)

Use after small code edits.

### 2.1 Syntax compile checks
```powershell
python -m py_compile core/services.py
python -m py_compile lada_desktop_app.py
python -m py_compile lada_jarvis_core.py
python -m py_compile lada_ai_router.py
python -m py_compile modules/api_server.py
python -m py_compile modules/api/routers/websocket.py
```

### 2.2 Targeted smoke tests
```powershell
pytest tests/test_router.py -q -o "addopts=" --tb=short
pytest tests/test_api_server.py -q -o "addopts=" --tb=short
```

### 2.3 Remote security + API contract gate
```powershell
pytest tests/test_remote_app_router.py tests/test_api_contract_auth_chat_ws.py -q -o "addopts="
```

### 2.4 Observability and compatibility contract matrix
```powershell
pytest tests/test_api_contract_auth_chat_ws.py tests/test_remote_app_router.py tests/test_marketplace_router_sanitization.py tests/test_openai_compat_models.py tests/test_openclaw_compat_router.py tests/test_openclaw_compat_fallback.py tests/test_orchestrator_subscription_api.py tests/test_tool_contract_versioning.py tests/test_tool_registry_native_openclaw_tools.py -q -o "addopts="
```

### 2.5 Next.js remote parity check
```powershell
npm --prefix frontend run lint
npm --prefix frontend run build
```

## 3. Medium validation (10-20 minutes)

Use before merging larger cleanup batches.

### 3.1 Core tests
```powershell
pytest tests/test_router.py tests/test_api_server.py tests/test_memory.py -q -o "addopts=" --tb=short
```

### 3.2 Registry probe
```powershell
python -c "from core.services import build_default_registry; s=build_default_registry(); r=s.probe_all(); print('available', sum(1 for v in r.values() if v), 'total', len(r))"
```

### 3.3 Desktop startup import path smoke
```powershell
python -c "import lada_desktop_app; print('desktop import ok')"
```

### 3.4 API startup smoke
```powershell
python -c "import modules.api_server; print('api server import ok')"
```

## 4. Full validation (30-60+ minutes)

Use before release or large architecture cleanups.

### 4.1 Broad tests
```powershell
pytest tests/ -v --tb=short
```

### 4.2 Focused e2e scripts
```powershell
python tests/test_e2e_complete.py
python tests/test_e2e_verification.py
```

### 4.3 API runtime health check
1. Start API server.
2. Verify auth endpoints.
3. Verify chat endpoint.
4. Verify `/v1/models` and `/v1/chat/completions` as configured.

### 4.4 WebSocket runtime check
1. Authenticate and obtain token.
2. Connect to `/ws?token=...`.
3. Send a chat message frame.
4. Verify chunked response then completion frame.

## 5. Cleanup-specific verification

Run after archive/removal actions.

### 5.1 Confirm archived files exist
```powershell
Get-ChildItem archived/integrations
```

### 5.2 Confirm active integrations package surface
```powershell
python -c "import integrations; print('integrations import ok')"
```

### 5.3 Confirm no stale runtime imports to archived modules
```powershell
rg "integrations\.(openclaw_gateway|openclaw_skills|alexa_hybrid|moltbot_controller)" core modules integrations voice -g "*.py"
```
Expected:
- No active runtime usage in `core/`, `modules/`, `integrations/`, or `voice/`.

If `rg` is unavailable on your machine, use:
```powershell
@('core','modules','integrations','voice') | ForEach-Object { if (Test-Path $_) { Get-ChildItem $_ -Recurse -Filter *.py } } | Select-String -Pattern "integrations\.(openclaw_gateway|openclaw_skills|alexa_hybrid|moltbot_controller)"
```

## 6. Expected outcomes checklist

Fast tier should pass:
- Compile checks pass.
- Router/API unit tests pass.

Medium tier should pass:
- Core route/memory tests pass.
- Registry probe completes without crash.
- Desktop/API module imports are healthy.

Full tier should pass:
- Broad tests run with known optional-dependency skips only.
- API/WebSocket runtime interactions are functional.

## 7. Failure triage rules

1. Compile failure: fix immediately before running further tests.
2. Import failure in core/runtime files: block merge.
3. Optional dependency failure: mark as skip if behavior is expected and graceful.
4. API/WebSocket auth/rate-limit regression: block merge.

## 8. Known optional dependency caveats

Depending on local machine setup, some tests may skip or fail for missing optional packages (for example browser automation or audio/system-control libraries). These do not automatically block merge unless the changed feature depends on them.

## 9. Reporting template

Use this short template in cleanup reports:

- Validation tier run: Fast/Medium/Full
- Commands executed:
- Pass count:
- Fail count:
- Skip count:
- Notable regressions:
- Final decision: pass / needs fixes
