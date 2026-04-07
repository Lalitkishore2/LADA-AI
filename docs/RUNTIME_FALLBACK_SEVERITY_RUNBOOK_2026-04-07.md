# Runtime Fallback Severity Runbook (2026-04-07)

## Purpose
This runbook defines how fallback-related logs should be interpreted and configured in LADA.

The core policy is simple:
- Expected optional or unconfigured states: INFO.
- Unexpected service or dependency failures: WARNING or ERROR.
- Repeated optional fallback logs: deduplicated once per process where implemented.

## Scope
This runbook covers these fallback paths:
- Secure vault fallback to environment variables.
- Vector-memory dependency fallback (sentence-transformers and ChromaDB).
- Optional system-control dependency behavior.

## Default Severity Policy
1. Secure vault missing master key
- Classification: expected-unconfigured (in development or env-only deployments).
- Severity: INFO.
- Typical message:
  - Secure vault unavailable (... master key not found ...); falling back to environment variables.

2. Secure vault unexpected backend failure
- Classification: potentially actionable runtime issue.
- Severity: WARNING.
- Typical examples:
  - vault backend unreachable
  - unexpected exceptions during vault access

3. Missing sentence-transformers
- Classification: optional capability unavailable.
- Severity: INFO.
- Behavior: fallback to ChromaDB default embeddings.

4. Missing ChromaDB
- Classification: optional capability unavailable in default mode.
- Severity:
  - INFO by default
  - WARNING in strict mode
- Behavior: fallback to in-memory store.

5. Missing optional system-control dependencies (for example pycaw)
- Classification: optional capability unavailable.
- Severity:
  - first occurrence: WARNING
  - repeated occurrences: DEBUG
- Behavior: operation-specific graceful fallback where available.

## Strict Mode Controls
Use these environment settings when you want stronger visibility for missing optional components.

### ChromaDB strict requirement
PowerShell example:

```powershell
$env:LADA_REQUIRE_CHROMADB = "1"
```

Expected effect:
- Missing ChromaDB fallback message elevates from INFO to WARNING.

### Secure vault with master key enabled
PowerShell example:

```powershell
$env:LADA_MASTER_KEY = "<base64-fernet-key>"
```

Expected effect:
- Vault should initialize and fallback log should disappear when keys are available.
- If fallback still occurs, treat as actionable and investigate vault path/permissions/runtime errors.

## Operational Modes
1. Local development mode
- Recommended:
  - allow INFO fallback logs for optional dependencies
  - keep strict mode off unless specifically testing strict behavior

2. Pre-production validation mode
- Recommended:
  - enable strict mode for components you consider required
  - fail fast on missing dependencies in CI checks where practical

3. Production mode
- Recommended:
  - decide required vs optional components explicitly
  - enable strict mode only for required components
  - monitor WARNING/ERROR rates and investigate sustained spikes

## Troubleshooting Checklist
1. Secure vault fallback appears at INFO
- Confirm whether deployment is env-only by design.
- If yes, no action required.
- If no, set LADA_MASTER_KEY and verify vault can initialize.

2. Secure vault fallback appears at WARNING
- Treat as actionable.
- Check vault backend availability, permissions, and runtime exceptions.
- Confirm no credential or path misconfiguration.

3. ChromaDB fallback appears at INFO
- Confirm whether in-memory mode is acceptable for the current environment.
- If persistent storage is required, install and configure ChromaDB.

4. ChromaDB fallback appears at WARNING
- Strict mode is active or policy expects ChromaDB.
- Ensure ChromaDB dependency/runtime is available.

5. Repeated fallback logs unexpectedly appear
- Confirm process-level dedup flags are not reset by process restarts.
- Check for non-deduped paths in newly introduced modules.

## Validation Commands
Use these commands to verify policy behavior.

1. Default startup classification

```powershell
& "c:/lada ai/jarvis_env/Scripts/python.exe" main.py status
```

2. Strict-mode ChromaDB classification

```powershell
$env:LADA_REQUIRE_CHROMADB = "1"
& "c:/lada ai/jarvis_env/Scripts/python.exe" main.py status
```

3. Reset strict-mode variable

```powershell
Remove-Item Env:LADA_REQUIRE_CHROMADB
```

## Ownership
- Runtime severity policy: core runtime maintainers.
- Deployment mode requirements: platform/ops owners.
- Dependency installation and environment setup: deployment owners.
