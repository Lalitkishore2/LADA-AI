# Startup Diagnostics Triage Runbook (2026-04-07)

## Purpose
This runbook helps operators quickly classify startup logs into:
- expected informational fallbacks,
- actionable warnings,
- actionable errors.

It also defines immediate next actions and ownership per category.

## Fast Triage Flow
1. Run startup status:

```powershell
& "c:/lada ai/jarvis_env/Scripts/python.exe" main.py status
```

2. Classify each notable line:
- INFO fallback line -> expected unless policy says component is required.
- WARNING line -> investigate if persistent or unexpected.
- ERROR line -> treat as actionable immediately.

3. Confirm service readiness:
- provider configuration completed
- router initialized
- memory initialized
- status endpoint output healthy

## Classification Matrix

### Category A: Expected INFO fallback (usually no action)
1. Secure vault unavailable due missing master key
- Example pattern:
  - [ProviderManager] Secure vault unavailable (... master key not found ...); falling back to environment variables
- Action:
  - none if env-only mode is intentional
  - otherwise move to Category B investigation
- Owner:
  - deployment owner (configuration)

2. sentence-transformers missing
- Example pattern:
  - [VectorMemory] sentence-transformers not installed, using ChromaDB default embeddings
- Action:
  - none if default embeddings are acceptable
  - install dependency if high-quality embeddings are required
- Owner:
  - runtime/deployment owner

3. ChromaDB missing in default mode
- Example pattern:
  - [VectorMemory] ChromaDB not installed. Using in-memory fallback.
- Action:
  - none if in-memory fallback is acceptable
  - install/configure ChromaDB if persistence is required
- Owner:
  - runtime/deployment owner

### Category B: WARNING (action depends on context)
1. Secure vault unavailable with unexpected exception
- Example pattern:
  - [ProviderManager] Secure vault unavailable (... unexpected exception ...)
- Action:
  - inspect vault backend and runtime error source
  - verify permissions and key material
- Owner:
  - runtime owner

2. Optional dependency unavailable (first occurrence)
- Example pattern:
  - Getting volume unavailable: optional dependency 'pycaw' is not installed
- Action:
  - install dependency only if feature is required
  - otherwise record as acceptable operational limitation
- Owner:
  - feature owner/deployment owner

### Category C: ERROR (always actionable)
1. Startup blocking errors
- Examples:
  - AI router not available
  - repeated provider initialization failures without fallback
  - uncaught exceptions in startup pipeline
- Action:
  - capture stack and request context
  - rollback recent changes if needed
  - open incident if production
- Owner:
  - runtime maintainer on call

## Known Noise Controls (already implemented)
1. Optional dependency warnings are deduped in key paths.
2. Third-party EDID parse warning source logger is clamped.
3. Fallback/noise one-time flags are lock-guarded in provider, vector memory, and system control modules.
4. Stream failure metadata propagates end-to-end for diagnostics.

## Startup Acceptance Checklist
1. No unexpected WARNING or ERROR lines.
2. Expected INFO fallback lines match deployment policy.
3. Provider configuration completes with expected provider count.
4. Status output confirms backend health and memory initialization.
5. API and websocket smoke tests pass for stream paths.

## Escalation Triggers
Escalate when any of these occur:
1. Repeated WARNING or ERROR lines on every startup after restart.
2. Fallback mode unexpectedly activated in strict-required environments.
3. Stream responses fail without metadata diagnostics.
4. Provider list drops below expected baseline for the environment.

## Suggested Incident Notes Template
Record these fields when triaging:
1. Environment (dev/staging/prod).
2. Startup command used.
3. Timestamp and request ID/correlation ID if available.
4. Full warning/error lines observed.
5. Whether fallback was expected by policy.
6. Immediate remediation taken.
7. Follow-up owner.

## Ownership Map
- Runtime code and log policy: core runtime maintainers.
- Dependency/install and env setup: deployment owner.
- Provider credentials and vault setup: security/platform owner.
