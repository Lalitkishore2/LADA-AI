# Phase 0 Baseline - 2026-04-20

## Scope

Baseline capture for the Phase 0 stabilization gate:

- Startup time baseline
- Command success rate baseline
- Tool-call success rate baseline
- Comet task success baseline
- Medium validation gate results

## Environment

- OS: Windows
- Python: 3.11.9 (`c:/lada ai/jarvis_env/Scripts/python.exe`)
- Workspace: `c:/lada ai`

## Commands Run

### Medium validation (playbook)

1. `pytest tests/test_router.py tests/test_api_server.py tests/test_memory.py -q -o "addopts=" --tb=short`
2. `python -c "from core.services import build_default_registry; s=build_default_registry(); r=s.probe_all(); print('available', sum(1 for v in r.values() if v), 'total', len(r))"`
3. `python -c "import time; t=time.perf_counter(); import lada_desktop_app; print('desktop import ok', round(time.perf_counter()-t, 3))"`
4. `python -c "import time; t=time.perf_counter(); import modules.api_server; print('api server import ok', round(time.perf_counter()-t, 3))"`

### Phase 0 reliability metrics

1. `pytest tests/test_system_executor.py tests/test_app_executor.py tests/test_voice_nlu.py tests/test_voice.py -q -o "addopts=" --tb=short`
2. `pytest tests/test_tool_handlers.py tests/test_tool_registry_native_lada_tools.py tests/test_tool_contract_versioning.py -q -o "addopts=" --tb=short`
3. `pytest tests/test_comet_agent.py -q -o "addopts=" --tb=short`

## Raw Results

- Medium core tests: `38 passed in 2.15s`
- Registry probe: `available 72 total 72`
- Desktop import smoke: `desktop import ok 13.085`
- API import smoke: `api server import ok 3.369`
- Command suite: `47 passed in 11.70s`
- Tool suite: `7 passed in 0.66s`
- Comet suite: `35 passed in 2.29s`

## Baseline Metrics

| Metric                              |       Baseline |
| ----------------------------------- | -------------: |
| Startup time (desktop import smoke) |       13.085 s |
| Startup time (API import smoke)     |        3.369 s |
| Command success rate                | 100.0% (47/47) |
| Tool-call success rate              |   100.0% (7/7) |
| Comet task success rate             | 100.0% (35/35) |

## Phase 0 Decision

- Medium validation gate: PASS
- Baseline metrics captured: PASS
- Phase 0 status: COMPLETE

## Notes

- Baseline values are from this workspace state and are intended as the Phase 1 comparison reference.
- Desktop import prints a pygame banner during import; this is expected in current baseline.
