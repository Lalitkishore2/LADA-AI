# LADA Cleanup and Removal Plan

Last updated: 2026-04-02
Status: Active maintenance plan

This document tracks what was removed, archived, and retained during cleanup work, including risk notes and validation requirements.

## 1. Objectives

1. Remove references to modules already retired from runtime.
2. Reduce dead optional integration noise in active code paths.
3. Preserve recoverability by archiving disconnected integrations.
4. Keep current deployment-critical integrations functional.

## 2. Decision model

Cleanup strictness selected: Balanced.

Rules:
- Remove high-confidence dead references.
- Archive disconnected optional modules instead of hard delete.
- Keep active integrations and make them operationally correct.

## 3. Completed actions (this cycle)

### 3.1 Runtime cleanup
- Fixed Alexa startup path in desktop app to use `integrations/alexa_server.py`.
- Registered `alexa_server` in `core/services.py` for availability probing.
- Removed stale `permission_system` optional import reference from startup optimizer.
- Removed stale `permission_system` priority entry from lazy loader.

### 3.2 Integration cleanup
Archived to `archived/integrations/`:
- `openclaw_gateway.py`
- `openclaw_skills.py`
- `alexa_hybrid.py`
- `moltbot_controller.py`
- `moltbot_firmware.ino`

### 3.3 Export and packaging cleanup
- Updated `integrations/__init__.py` exports to active integration surface only.
- Updated `voice/__init__.py` to remove stale Alexa hybrid export.

### 3.4 Test cleanup
- Replaced stale `PermissionSystem` import check in `tests/test_e2e_verification.py` with active `SafetyGate` check.

### 3.5 Baseline hygiene cleanup (2026-04-02)
- Removed transient bytecode artifacts from `archived/integrations/__pycache__/`.
- Replaced hard optional import in `modules/agents/robot_agent.py` with dynamic optional loading so archived integrations are not referenced as active runtime imports.
- Preserved graceful degradation semantics: robot agent stays operationally safe when MoltBot integration is unavailable.

## 4. Why archive instead of delete

Archived modules are intentionally preserved because:
- They may be useful for future feature reactivation.
- They are not currently wired into active runtime paths.
- Archiving avoids hard loss while reducing current maintenance burden.

## 5. Keep list and rationale

### Keep and maintain
- `integrations/alexa_server.py`
  - Reason: active desktop startup path and valid Echo bridge use case.

### Keep but optional/fallback
- `modules/agents/robot_agent.py`
  - Reason: still valid optional agent class; now cleanly handles missing archived MoltBot backend.

## 6. Residual known legacy references

Some historical documents may still mention retired modules as past implementation context. These should be treated as historical, not active runtime specification.

Recommended standard:
- Current operational truth: `docs/WORKFLOW.md`
- Historical implementation context: older architecture and implementation chronicles

## 7. Candidate matrix for future cycles

### High confidence archive/delete candidates
- Additional disconnected files under `integrations/` when not wired into runtime.
- Any tests asserting behavior for already retired modules.

### Medium confidence candidates
- Legacy optimization maps that reference removed modules but do not execute by default.
- Historical docs that duplicate current docs with conflicting guidance.

## 8. Reactivation checklist for archived integrations

If any archived integration is needed again:
1. Move file(s) back under `integrations/`.
2. Restore exports in `integrations/__init__.py` if required.
3. Register required classes/factories in `core/services.py`.
4. Re-wire tool registry/handlers or executor hooks as needed.
5. Add focused tests.
6. Run `docs/VALIDATION_PLAYBOOK.md` medium/full checks.

## 9. Safety rules for cleanup work

1. Never remove active runtime entry points without replacement.
2. Preserve API compatibility where public paths are used.
3. Prefer archive over delete for medium-confidence optional modules.
4. Verify syntax and targeted tests after each cleanup cycle.

## 10. Validation summary format (for each cleanup PR)

Use this block in future cleanup reports:

- Scope:
- Files archived:
- Files edited:
- Runtime behavior changes:
- Verification commands run:
- Test outcomes:
- Rollback notes:

## 11. Related references

- `docs/WORKFLOW.md`
- `docs/API_WEBSOCKET_REFERENCE.md`
- `docs/VALIDATION_PLAYBOOK.md`
