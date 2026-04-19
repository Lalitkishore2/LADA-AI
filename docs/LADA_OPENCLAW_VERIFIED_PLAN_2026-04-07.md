# LADA x OpenClaw Verified Implementation Plan

> **Historical snapshot:** This document is preserved for traceability.
> **Canonical active parity status now lives in:** `docs/LADA_PARITY_MASTER_PLAN_2026-04-07.md`
>  
> Use the parity master matrix for current implementation state and remaining work sequencing.

Date: 2026-04-07
Status: Verified from local codebases

## 1. Goal

Build LADA into a production-grade personal agent platform with OpenClaw-level runtime architecture while preserving LADA strengths (desktop control, voice, system automation, local-first model routing).

This plan is based on direct inspection of:
- OpenClaw local repo: openclaw code base/
- LADA local repo: current workspace

## 2. What Was Verified (Not Assumed)

### OpenClaw capabilities verified from local files

1. Gateway as single typed control plane
- docs/concepts/architecture.md
- docs/gateway/protocol.md
- src/gateway/protocol/index.ts

2. Role-based connect + node/operator model + pairing/auth scopes
- docs/gateway/protocol.md
- docs/gateway/security/index.md

3. Multi-agent routing with per-agent workspace/state/session isolation
- docs/concepts/multi-agent.md

4. ACP bridge for IDE agent protocol
- docs.acp.md
- src/acp/server.ts

5. Background task ledger + durable Task Flow orchestration
- docs/automation/tasks.md
- docs/automation/taskflow.md
- src/tasks/task-registry.ts
- src/tasks/task-flow-registry.ts

6. Durable cron + webhook trigger runtime
- docs/automation/cron-jobs.md
- docs/automation/taskflow.md
- src/cron/isolated-agent.ts

7. Exec approval model with allowlist/ask modes and host policy merge
- docs/tools/exec-approvals.md

8. Security posture + audit/doctor operational tooling
- docs/gateway/security/index.md
- docs/gateway/doctor.md
- src/security/audit.ts

9. Plugin and skill governance (precedence, slots, allow/deny, install security scanning)
- docs/tools/plugin.md
- docs/tools/skills.md
- src/plugins/marketplace.ts

10. Subagent runtime with nested orchestration limits and announce delivery
- docs/tools/subagents.md

### LADA capabilities verified from local files

1. Existing WS gateway and API orchestration are real
- modules/api/routers/websocket.py
- modules/api/routers/orchestration.py

2. Existing command bus/orchestrator contracts exist (good base)
- modules/standalone/contracts.py
- modules/standalone/orchestrator.py

3. Existing task/workflow modules exist but are fragmented
- modules/task_orchestrator.py
- modules/task_automation.py
- modules/workflow_pipelines.py

4. Existing safety modules exist but not unified as a central approval engine
- modules/safety_gate.py
- modules/safety_controller.py
- lada_jarvis_core.py

5. Existing plugin/skill modules exist but without strong trust/provenance/security policy
- modules/plugin_system.py
- modules/plugin_marketplace.py

6. Existing webhook and heartbeat systems exist
- modules/webhook_manager.py
- modules/heartbeat_system.py

7. Existing session and multi-agent helper modules exist but not integrated into a strict runtime model
- modules/session_manager.py
- modules/agent_collaboration.py
- modules/agents/specialist_pool.py

8. Existing messaging pairing exists
- modules/messaging/base_connector.py

## 3. Gap Summary (OpenClaw baseline -> LADA current)

### G1. Protocol maturity gap
- LADA WS is message-type dispatch JSON, not a versioned typed protocol contract.
- Missing explicit role/scope/cap negotiation and protocol-version handshake model.

### G2. Agent isolation gap
- LADA has sessions and collaboration primitives, but not strict per-agent workspace/auth/session boundary model equivalent to OpenClaw multi-agent routing.

### G3. Subagent/task-flow gap
- LADA has task engines and workflow pipelines, but no unified durable task ledger + flow runtime with lifecycle invariants and consistent CLI/API control semantics.

### G4. Approval-policy gap
- LADA has safety checks and pending confirmation, but no central approval service with host policy merge, ask modes, allowlist governance, and audit-grade decision state.

### G5. Security-ops gap
- LADA lacks an operator-grade doctor/audit command surface covering config drift, policy drift, filesystem perms, and exposure checks in one place.

### G6. Plugin/skill trust gap
- LADA supports plugin loading/marketplace and SKILL parsing, but lacks provenance, strict allow/deny policy, plugin slots, and install-time security scanning model.

### G7. ACP / IDE bridge gap
- LADA has no ACP-compatible bridge for IDE-native agent workflows.

## 4. Implementation Program (Phased)

## Phase 0 (Week 1): Contract and Runtime Baseline

Deliverables:
1. LADA Gateway Protocol v1 spec (JSON schema) with version and handshake.
2. Connect roles: operator and node; scoped permissions map.
3. Idempotency contract for side-effecting calls.
4. Protocol compatibility test fixtures.

Implementation targets:
- New: modules/gateway_protocol/schema.py
- New: modules/gateway_protocol/validator.py
- Extend: modules/api/routers/websocket.py
- Extend: modules/standalone/contracts.py

Acceptance criteria:
- All WS requests validated against schema.
- Handshake rejects unknown/mismatched protocol versions.
- Side-effect methods require idempotency keys.

## Phase 1 (Weeks 2-3): Agent Boundary and Session Architecture

Deliverables:
1. Agent profile model with explicit agent_id, workspace_root, agent_state_dir.
2. Per-agent auth/profile stores and session namespace.
3. Routing/binding table for channel+peer -> agent.
4. Per-agent skill allowlist.

Implementation targets:
- New: modules/agent_runtime/agent_registry.py
- New: modules/agent_runtime/bindings.py
- Extend: modules/session_manager.py
- Extend: modules/messaging/base_connector.py

Acceptance criteria:
- Two agents can run concurrently with isolated memory/history/auth.
- Channel message routes deterministically to correct agent.
- Cross-agent leakage tests pass.

## Phase 2 (Weeks 3-5): Unified Tasks + Task Flow

Deliverables:
1. Unified Task Registry (queued/running/succeeded/failed/timed_out/cancelled/lost).
2. Task Flow layer above tasks with managed and mirrored sync modes.
3. Task maintenance/audit operations.
4. Consistent API and WS task endpoints.

Implementation targets:
- New: modules/tasks/task_registry.py
- New: modules/tasks/task_flow_registry.py
- New: modules/tasks/task_maintenance.py
- Integrate existing: modules/task_orchestrator.py, modules/task_automation.py, modules/workflow_pipelines.py
- Extend: modules/api/routers/orchestration.py

Acceptance criteria:
- Task state persists across restart.
- Long-running tasks reconcile correctly after crash/restart.
- Flow cancel is sticky and stops child task creation.

## Phase 3 (Weeks 5-6): Approval Engine + Action Safety

Deliverables:
1. Central ActionPolicyEngine and ApprovalQueue service.
2. Ask modes: off/on-miss/always + fallback policy.
3. Command allowlist with exact-match normalization.
4. Decision logging with searchable audit history.

Implementation targets:
- New: modules/security/approvals.py
- New: modules/security/action_policy.py
- Refactor from: modules/safety_gate.py, modules/safety_controller.py
- Extend: lada_jarvis_core.py and executor callsites

Acceptance criteria:
- Dangerous actions never execute without policy resolution.
- Approval decisions are replay-safe and auditable.
- Web/desktop/API all share same approval backend.

## Phase 4 (Weeks 6-7): Security Audit + Doctor

Deliverables:
1. lada doctor command for migration/repair/status.
2. lada security audit command (quick + deep).
3. Hardening checks: auth exposure, file permissions, policy drift, dangerous tools.

Implementation targets:
- New: modules/security/audit.py
- New: modules/security/fix.py
- New: modules/doctor/runtime.py
- New CLI entrypoints in main.py

Acceptance criteria:
- audit returns structured finding objects with severity and remediation.
- doctor can apply safe remediations automatically.
- CI gate for security regressions on core config paths.

## Phase 5 (Weeks 7-8): Plugin and Skill Governance

Deliverables:
1. Plugin trust metadata (source, hash/signature, installed_at, risk level).
2. Allow/deny and optional slot model for critical plugin classes.
3. Install-time security scanning and policy block capability.
4. Skill source precedence and per-agent visibility enforcement.

Implementation targets:
- Extend: modules/plugin_system.py
- Extend: modules/plugin_marketplace.py
- New: modules/plugins/install_scanner.py
- New: modules/plugins/policy.py

Acceptance criteria:
- Untrusted plugin blocked by policy unless explicit override.
- Plugin inventory endpoint returns trust and provenance info.
- Skill visibility respects per-agent allowlist.

## Phase 6 (Weeks 8-9): Subagents and ACP Bridge

Deliverables:
1. sessions_spawn equivalent with subagent lifecycle and announce callback.
2. Optional nested depth limits and child concurrency caps.
3. ACP bridge MVP (stdio adapter -> LADA gateway session).

Implementation targets:
- New: modules/subagents/runtime.py
- New: modules/subagents/policy.py
- New: modules/acp_bridge/server.py
- Extend: modules/api/routers/websocket.py

Acceptance criteria:
- Subagent completion returns to requester session reliably.
- Nested depth and caps enforced.
- IDE client can maintain ACP session mapping through LADA bridge.

## 5. Technical Rules for This Program

1. Do not rewrite everything. Adapt existing modules and converge them.
2. Keep backward compatibility for existing APIs during migration.
3. Every new runtime service needs:
- schema validation
- persistence model
- reconciliation on startup
- audit events
- integration tests
4. Add feature flags for high-risk runtime changes.

## 6. Suggested Ownership by Workstream

1. Protocol + WS runtime: gateway/core engineer
2. Agent/session isolation: runtime engineer
3. Task/flow registry: orchestration engineer
4. Approval/safety: security engineer
5. Doctor/audit: platform reliability engineer
6. Plugin/skills governance: ecosystem engineer
7. ACP/subagents: developer-experience engineer

## 7. Definition of Done for OpenClaw-level Runtime Parity

LADA is considered parity-ready when:
1. Typed protocol handshake and role/scope model are enforced in production.
2. Per-agent isolation is default and tested.
3. Unified task + flow runtime survives restart with deterministic states.
4. Central approvals gate all dangerous actions.
5. Doctor and security audit commands provide actionable remediation.
6. Plugin/skill installs are governed by trust policy and scanning.
7. Subagents and ACP bridge are functional for advanced workflows.

## 8. Coverage Check Against Your Requested Add-List

Status key:
- Included: explicitly planned with deliverables
- Partial: foundation included, advanced layer still needed
- Deferred: not in Phases 0-6, added to Phase 7 below

1. Multi-machine sidecar runtime with authenticated nodes and capability registry
- Status: Included
- Covered by: Phase 0 and Phase 1 protocol + role/scope + agent boundary work

2. Authority center (approval queue, policy engine, audit timeline, emergency stop)
- Status: Included
- Covered by: Phase 3

3. Computer-use security layers (prompt-injection detection, sensitive-action confirmations, transparency feed)
- Status: Partial
- Covered by: Phase 3 confirmations/policy/audit
- Missing advanced layer: explicit prompt-injection classifier + action transparency stream hardening

4. Durable background task runtime with pause/resume/cancel/retry/checkpoint
- Status: Included
- Covered by: Phase 2

5. Deterministic workflow upgrades (persisted DAG, triggers, fallback, compensation)
- Status: Partial
- Covered by: Phase 2 task+flow foundation
- Missing advanced layer: explicit compensation strategy framework

6. Skills platform v2 (bundles, selective activation by risk/category/tags, validation)
- Status: Partial
- Covered by: Phase 5 trust and allowlist controls
- Missing advanced layer: bundle-level policy/tags/category rollout controls

7. Plugin trust and governance (signing/provenance/capability permissions)
- Status: Included
- Covered by: Phase 5

8. Deep Research v2 (multi-hop planner, source reliability, citation confidence, export)
- Status: Deferred
- Added in: Phase 7

9. Specialist multi-agent orchestration with authority boundaries
- Status: Partial
- Covered by: Phase 1 and Phase 6
- Missing advanced layer: specialist role planner and authority partition policy

10. Enterprise controls (SSO/RBAC/org policies/MCP governance/compliance logs)
- Status: Deferred
- Added in: Phase 7

11. Copilot-style developer flows (background coding agent, code review agent, repo memory)
- Status: Deferred
- Added in: Phase 7

12. Cross-surface continuity (desktop/web/mobile/CLI task continuity)
- Status: Deferred
- Added in: Phase 7

## 9. Phase 7 (Post-Foundation): Full Multi-Source Parity Track

Run this only after Phases 0-6 are stable.

Deliverables:
1. Deep Research v2 runtime (planner, source reliability scoring, citation confidence, export templates).
2. Enterprise controls (SSO, RBAC, org policy engine, MCP governance registry, compliance exports).
3. Dev productivity runtime (background coding agent, review agent, repository memory workflows).
4. Cross-surface continuity state sync (desktop/web/CLI/mobile node handoff state).
5. Advanced computer-use security layer (prompt-injection classifier and action transparency stream).

Acceptance criteria:
- Research output includes confidence and source-quality metadata.
- Enterprise policy blocks and audits are test-covered.
- Coding/review agents can run asynchronously and report deterministic artifacts.
- User can start a task on one surface and resume on another with preserved state.

## 10. Immediate Next Step

Start with Phase 0 and Phase 1 only. Do not begin ACP, nested subagents, plugin slot redesign, or Phase 7 tracks until protocol and agent-boundary fundamentals are stable.
