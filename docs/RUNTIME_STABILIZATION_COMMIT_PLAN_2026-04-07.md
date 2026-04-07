# Runtime Stabilization Commit Plan (2026-04-07)

## Purpose
This guide provides a safe, non-interactive commit sequence for the runtime stabilization work completed in this session while avoiding unrelated dirty working-tree changes.

The repository currently contains many unrelated modified/generated files (data, exports, config, archived integrations, etc.). This plan commits only the stabilization scope.

## Preconditions
1. Ensure you are on the intended branch.
2. Do not run broad `git add .` in this repository state.
3. Use path-scoped `git add` commands exactly as listed.

## Commit 1 - Runtime hardening code paths
### Files
- `modules/console_encoding.py`
- `main.py`
- `lada_desktop_app.py`
- `modules/api/routers/app.py`
- `modules/providers/provider_manager.py`
- `modules/system_control.py`
- `modules/vector_memory.py`
- `modules/google_calendar.py`
- `lada_ai_router.py`
- `modules/api/routers/chat.py`
- `modules/api/routers/websocket.py`

### Command
```powershell
git add modules/console_encoding.py main.py lada_desktop_app.py modules/api/routers/app.py modules/providers/provider_manager.py modules/system_control.py modules/vector_memory.py modules/google_calendar.py lada_ai_router.py modules/api/routers/chat.py modules/api/routers/websocket.py
```

### Commit message
```powershell
git commit -m "harden runtime startup, fallback logging, and stream diagnostics"
```

## Commit 2 - Regression and matrix test expansion
### Files
- `tests/test_console_encoding.py`
- `tests/test_remote_app_router.py`
- `tests/test_provider_manager_vault_logging.py`
- `tests/test_system_control_logging.py`
- `tests/test_vector_memory_logging.py`
- `tests/test_provider_manager.py`
- `tests/test_rate_limiter_resilience.py`
- `tests/test_rate_limiter_limits.py`
- `tests/test_api_contract_auth_chat_ws.py`
- `tests/test_google_calendar.py`

### Command
```powershell
git add tests/test_console_encoding.py tests/test_remote_app_router.py tests/test_provider_manager_vault_logging.py tests/test_system_control_logging.py tests/test_vector_memory_logging.py tests/test_provider_manager.py tests/test_rate_limiter_resilience.py tests/test_rate_limiter_limits.py tests/test_api_contract_auth_chat_ws.py tests/test_google_calendar.py
```

### Commit message
```powershell
git commit -m "add regression coverage for fallback policies, streaming metadata, and rate limiter matrix"
```

## Commit 3 - Docs and runbooks
### Files
- `README.md`
- `docs/RUNTIME_STABILIZATION_CLOSEOUT_2026-04-07.md`
- `docs/RUNTIME_HARDENING_BACKLOG_2026-04-07.md`
- `docs/RUNTIME_FALLBACK_SEVERITY_RUNBOOK_2026-04-07.md`
- `docs/STARTUP_DIAGNOSTICS_TRIAGE_RUNBOOK_2026-04-07.md`
- `docs/RUNTIME_STABILIZATION_COMMIT_PLAN_2026-04-07.md`

### Command
```powershell
git add README.md docs/RUNTIME_STABILIZATION_CLOSEOUT_2026-04-07.md docs/RUNTIME_HARDENING_BACKLOG_2026-04-07.md docs/RUNTIME_FALLBACK_SEVERITY_RUNBOOK_2026-04-07.md docs/STARTUP_DIAGNOSTICS_TRIAGE_RUNBOOK_2026-04-07.md docs/RUNTIME_STABILIZATION_COMMIT_PLAN_2026-04-07.md
```

### Commit message
```powershell
git commit -m "document runtime stabilization closeout, backlog completion, and operator runbooks"
```

## Recommended validation before push
```powershell
& "c:/lada ai/jarvis_env/Scripts/python.exe" -m pytest tests/test_api_contract_auth_chat_ws.py tests/test_system_control_logging.py tests/test_vector_memory_logging.py tests/test_provider_manager_vault_logging.py tests/test_provider_manager.py tests/test_rate_limiter_resilience.py tests/test_rate_limiter_limits.py tests/test_console_encoding.py tests/test_google_calendar.py tests/test_remote_app_router.py -q
```

Expected result in this session:
- 111 passed

## Safety notes
1. Avoid committing generated/runtime files such as:
- `.coverage`
- `data/*`
- `config/weather_cache.json`
- `exports/*`
2. If needed, inspect staged contents before each commit:
```powershell
git diff --staged --name-only
```
3. Push only after all three commits are verified.
