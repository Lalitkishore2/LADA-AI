# Safe Cleanup / Stash Plan (2026-04-07)

## Goal
Clean the current dirty working tree without losing local work.

This plan is non-destructive and uses path-scoped stashes so you can restore only what you need.

## Current uncommitted scope (post-push)
### Modified tracked files
- `.coverage`
- `.env.example`
- `.gitignore`
- `archived/integrations/alexa_hybrid.py`
- `archived/integrations/moltbot_controller.py`
- `archived/integrations/openclaw_skills.py`
- `config/last_briefing.txt`
- `config/weather_cache.json`
- `data/audit/remote_actions.jsonl`
- `data/secure_vault.enc`
- `data/workflows/evening_routine.json`
- `data/workflows/morning_routine.json`
- `data/workflows/research_workflow.json`
- `docs/SETUP.md`
- `exports/test_export.md`
- `frontend/src/app/remote/page.tsx`
- `frontend/src/app/settings/page.tsx`
- `frontend/src/lib/lada-api.ts`
- `frontend/src/lib/remote-api.ts`
- `modules/health_monitor.py`
- `modules/productivity_tools.py`
- `modules/providers/ollama_provider.py`
- `modules/secure_vault.py`
- `modules/shutdown_manager.py`
- `modules/task_orchestrator.py`
- `tests/test_auto_updater.py`
- `tests/test_history.json`

### Untracked files
- `data/email_drafts/draft_20260403_082551.txt`
- `data/email_drafts/draft_20260403_082902.txt`
- `data/email_drafts/draft_20260403_083337.txt`
- `data/email_drafts/draft_20260403_083616.txt`
- `data/email_drafts/draft_20260403_084416.txt`
- `data/email_drafts/draft_20260403_084700.txt`
- `data/email_drafts/draft_20260403_084835.txt`
- `data/email_drafts/draft_20260404_113227.txt`
- `data/secure_vault.invalid-1775185128.enc`
- `data/secure_vault.invalid-1775185168.enc`
- `data/secure_vault.invalid-1775185437.enc`
- `data/secure_vault.invalid-1775185598.enc`
- `data/secure_vault.invalid-1775186078.enc`
- `data/secure_vault.invalid-1775186237.enc`
- `data/secure_vault.invalid-1775186332.enc`
- `data/secure_vault.invalid-1775282565.enc`
- `data/secure_vault.invalid-1775562913.enc`

---

## Step 1 - Stash generated/runtime artifacts
This captures machine-generated runtime files, logs, caches, and drafts.

```powershell
git stash push -u -m "wip/runtime-artifacts-2026-04-07" -- .coverage config/last_briefing.txt config/weather_cache.json data/audit/remote_actions.jsonl data/workflows/evening_routine.json data/workflows/morning_routine.json data/workflows/research_workflow.json exports/test_export.md tests/test_history.json data/email_drafts data/secure_vault.invalid-*.enc
```

## Step 2 - Stash unrelated code/product work
This captures unrelated source/docs/frontend changes that are not part of the runtime stabilization commits.

```powershell
git stash push -m "wip/unrelated-code-and-frontend-2026-04-07" -- .env.example .gitignore archived/integrations/alexa_hybrid.py archived/integrations/moltbot_controller.py archived/integrations/openclaw_skills.py docs/SETUP.md frontend/src/app/remote/page.tsx frontend/src/app/settings/page.tsx frontend/src/lib/lada-api.ts frontend/src/lib/remote-api.ts modules/health_monitor.py modules/productivity_tools.py modules/providers/ollama_provider.py modules/secure_vault.py modules/shutdown_manager.py modules/task_orchestrator.py tests/test_auto_updater.py
```

## Step 3 - Stash local secure vault binary separately (optional but recommended)
Keep this isolated because it may contain machine/local sensitive state.

```powershell
git stash push -m "wip/local-secure-vault-state-2026-04-07" -- data/secure_vault.enc
```

---

## Verification
After steps 1-3:

```powershell
git status --short
git stash list
```

Expected: clean or significantly cleaner tree, with 2-3 named stash entries.

## Restore guidance
List stashes:

```powershell
git stash list
```

Inspect a stash before applying:

```powershell
git stash show --name-only stash@{0}
```

Apply (keep stash):

```powershell
git stash apply stash@{0}
```

Pop (apply and remove stash):

```powershell
git stash pop stash@{0}
```

Drop a stash after confirming no longer needed:

```powershell
git stash drop stash@{0}
```

## Notes
1. This plan avoids destructive resets and keeps recovery straightforward.
2. If `data/secure_vault.enc` should never be versioned, handle that in a separate policy discussion before altering tracking behavior.
