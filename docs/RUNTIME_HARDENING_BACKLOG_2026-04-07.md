# Runtime Hardening Backlog (Post-Closeout)

## Purpose
This file tracks recommended follow-up work after completion of the runtime stabilization closeout.

These items are not blockers for the completed scope, but they are valuable for production hardening and future scale.

## Priority Roadmap

## P1 - Concurrency Hardening and Observability

### 1) Lock and dedup audit for once-only log patterns
- Status:
  - Completed in this implementation pass.
- Goal:
  - Verify all once-only warning/info paths in hot startup modules are lock-safe.
- Why:
  - Prevent duplicate first-failure logs under concurrent startup paths.
- Candidate modules:
  - `modules/providers/provider_manager.py`
  - `modules/system_control.py`
  - `modules/vector_memory.py`
- Acceptance criteria:
  - No duplicate once-only log emissions under synthetic multithreaded startup test.

### 2) Streaming failure telemetry contract check
- Status:
  - Completed in this implementation pass.
- Goal:
  - Ensure consumers (UI/API adapters) handle enriched stream failure metadata.
- Why:
  - New metadata fields improve diagnosis only if surfaced downstream.
- Acceptance criteria:
  - Integration tests confirm metadata propagation and no UI/API regressions.

## P2 - Rate-Limiter Functional Matrix Expansion

### 3) Add matrix tests for token and circuit interaction
- Status:
  - Completed in this implementation pass.
- Goal:
  - Extend beyond resilience and boundary cases into combined scenarios.
- Suggested matrix:
  - Open circuit + token deny interplay
  - Half-open probe success/failure transitions with realistic timing
  - RPD-only saturation with minute-window still open
  - Cross-provider isolation in shared limiter instance
- Files:
  - `tests/test_rate_limiter_resilience.py`
  - `tests/test_rate_limiter_limits.py`
- Acceptance criteria:
  - Deterministic tests with synthetic monotonic time controls.

### 4) Retry-after contract test coverage
- Status:
  - Completed in this implementation pass.
- Goal:
  - Assert retry-after correctness for representative minute/day limits.
- Why:
  - Improves confidence in external retry behavior.
- Acceptance criteria:
  - Retry-after values stay within tight bounded ranges in all tested conditions.

## P3 - Operational Documentation and Runbook

### 5) Production runbook for fallback severity modes
- Status:
  - Completed in this implementation pass.
- Goal:
  - Document exactly when to use strict vs default fallback severities.
- Include:
  - `LADA_REQUIRE_CHROMADB`
  - Secure vault expected-unconfigured vs unexpected failure examples
- Acceptance criteria:
  - One operator-facing checklist in docs with copy/paste env examples.

### 6) Startup diagnostics quick triage guide
- Status:
  - Completed in this implementation pass.
- Goal:
  - Classify startup log lines into expected optional fallback vs actionable error.
- Acceptance criteria:
  - New guide maps each line category to next action and owner.

## Suggested Execution Order
1. Completed

## Recommended Validation Gate for Backlog Completion
1. Run targeted tests for modified modules.
2. Run consolidated hardened-module suite.
3. Run `python main.py status` and verify startup log classification.
4. Execute one simulated provider outage/rate-limit scenario and confirm fallback diagnostics.

## Ownership Notes
- Code hardening: core runtime maintainers
- Test matrix expansion: core runtime + QA
- Operational runbook: maintainer + ops owner
