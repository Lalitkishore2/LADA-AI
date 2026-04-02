# LADA Baseline and Targets

Captured: 2026-04-02
Status: Active implementation checkpoint

## 1. Baseline snapshot (start of cycle)

- Python source files (excluding virtualenv/cache/archived): 277
- Test files (`tests/test_*.py`): 91
- API router modules (`modules/api/routers/*.py`): 9
- Archived integration artifacts: 5 code files
- Archived cache artifacts present at baseline: `archived/integrations/__pycache__/` (transient, not desired)
- Stale runtime imports to archived integrations at baseline: 1 (`modules/agents/robot_agent.py`)

## 2. Targets for this implementation cycle

1. Remove transient cache artifacts from archived integration area.
2. Eliminate hard runtime imports to archived integrations.
3. Keep optional integration degradation behavior explicit and safe.
4. Ensure docs align with current runtime contracts:
   - workflow + cleanup references
   - API/WebSocket request correlation behavior
   - validation commands for contract matrix and stale-import checks
5. Run contract regression gate after updates.

## 3. Completion criteria

- `archived/integrations/__pycache__/` removed.
- No active runtime imports of archived integration modules under `core/`, `modules/`, `integrations/`, `voice/`.
- Updated docs: `docs/CLEANUP_PLAN.md`, `docs/WORKFLOW.md`, `docs/API_WEBSOCKET_REFERENCE.md`, `docs/VALIDATION_PLAYBOOK.md`.
- Regression matrix passes:
  - auth/chat/ws contracts
  - remote router contracts
  - marketplace/openai/openclaw/orchestration contracts
  - tool contract/versioning checks
