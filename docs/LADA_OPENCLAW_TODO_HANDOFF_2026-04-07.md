# LADA OpenClaw Parity TODO Handoff

Date: 2026-04-07
Audience: New chat / new engineer handoff

## 0. Mission

Implement OpenClaw-level runtime architecture in LADA using the verified plan in:
- docs/LADA_OPENCLAW_VERIFIED_PLAN_2026-04-07.md

Do not start from scratch. Refactor and converge existing LADA modules.

## 1. Read First (Required)

1. docs/LADA_OPENCLAW_VERIFIED_PLAN_2026-04-07.md
2. openclaw code base/docs/concepts/architecture.md
3. openclaw code base/docs/gateway/protocol.md
4. openclaw code base/docs/concepts/multi-agent.md
5. openclaw code base/docs/automation/tasks.md
6. openclaw code base/docs/automation/taskflow.md
7. openclaw code base/docs/tools/exec-approvals.md
8. modules/api/routers/websocket.py
9. modules/standalone/contracts.py
10. modules/task_orchestrator.py
11. modules/task_automation.py
12. modules/workflow_pipelines.py
13. modules/safety_gate.py
14. modules/safety_controller.py
15. modules/plugin_system.py
16. modules/plugin_marketplace.py

## 2. Execution Rules

1. Keep backward compatibility for existing API/WS routes while migrating.
2. Every new runtime subsystem must include:
- persistent state
- startup reconciliation
- structured logs/audit events
- tests
3. Prefer additive rollouts behind flags.
4. No large unrelated refactors.

## 3. Phase Checklist

## Phase 0: Gateway Protocol Contract

- [ ] Create modules/gateway_protocol/schema.py
- [ ] Define protocol version, connect handshake, roles, scopes
- [ ] Add idempotency key requirement for side-effect operations
- [ ] Add validator integration into modules/api/routers/websocket.py
- [ ] Add contract tests for valid/invalid frames

Done when:
- [ ] Invalid frames are rejected deterministically
- [ ] Version mismatch is explicit and test-covered

## Phase 1: Agent Isolation and Routing

- [ ] Create modules/agent_runtime/agent_registry.py
- [ ] Add agent config model: agent_id, workspace_root, state_dir
- [ ] Add channel/peer -> agent binding resolution
- [ ] Namespace sessions by agent
- [ ] Add per-agent skill visibility controls

Done when:
- [ ] Two agents can run in same process with no context leakage
- [ ] Routing tests prove deterministic selection

## Phase 2: Unified Task Registry + Task Flow

- [ ] Create modules/tasks/task_registry.py
- [ ] Create modules/tasks/task_flow_registry.py
- [ ] Integrate existing modules/task_orchestrator.py
- [ ] Integrate existing modules/task_automation.py
- [ ] Integrate existing modules/workflow_pipelines.py
- [ ] Add task maintenance/reconciliation module
- [ ] Expose consistent /tasks and /flows API responses

Done when:
- [ ] Task state survives restart
- [ ] Flow cancel blocks future child task starts

## Phase 3: Approval Engine

- [ ] Create modules/security/action_policy.py
- [ ] Create modules/security/approvals.py
- [ ] Migrate checks from safety_gate/safety_controller into central engine
- [ ] Replace ad-hoc pending confirmations in lada_jarvis_core.py callsites
- [ ] Add approval audit log query endpoint

Done when:
- [ ] Dangerous actions are centrally policy-gated
- [ ] Approval decisions are replay-safe and auditable

## Phase 4: Doctor + Security Audit

- [ ] Create modules/doctor/runtime.py
- [ ] Create modules/security/audit.py
- [ ] Create modules/security/fix.py
- [ ] Add main.py CLI commands: doctor, security-audit
- [ ] Add checks for auth exposure, policy drift, permission drift

Done when:
- [ ] Audit returns machine-readable findings with severity/remediation
- [ ] Doctor can auto-fix safe issues

## Phase 5: Plugin and Skill Governance

- [ ] Add plugin trust metadata model (source/hash/risk)
- [ ] Add allow/deny policy in plugin loader
- [ ] Add install-time security scan before activation
- [ ] Add skill source precedence and per-agent allowlist enforcement
- [ ] Expose plugin trust status in API/UI

Done when:
- [ ] Untrusted plugins can be blocked by policy
- [ ] Skill visibility follows agent policy

## Phase 6: Subagents + ACP Bridge

- [ ] Create modules/subagents/runtime.py
- [ ] Implement sessions_spawn-like API with lifecycle tracking
- [ ] Implement nested depth and concurrency limits
- [ ] Create modules/acp_bridge/server.py
- [ ] Add ACP session mapping and reconnect behavior

Done when:
- [ ] Subagent completion reliably returns to requester
- [ ] ACP client can hold stable LADA session mapping

## Phase 7: Full Multi-Source Parity Extensions (After Phase 0-6)

- [ ] Build Deep Research v2 pipeline (multi-hop planner, source reliability scoring, citation confidence)
- [ ] Add structured research export templates and traceability metadata
- [ ] Add enterprise control layer (SSO, RBAC, org policy center)
- [ ] Add MCP governance registry (allowlist, policy, usage audit)
- [ ] Add background coding agent workflow
- [ ] Add code-review agent workflow with artifact output
- [ ] Add repository memory workflow for coding/review loops
- [ ] Add cross-surface continuation state sync (desktop/web/CLI/mobile-node)
- [ ] Add computer-use prompt-injection classifier
- [ ] Add action transparency stream for high-risk automation

Done when:
- [ ] Deferred parity items from the verified plan are fully implemented
- [ ] End-to-end continuity works across at least two user surfaces

## 4. Test Plan (Minimum)

- [ ] Protocol validation tests (handshake/version/role/scope)
- [ ] Agent isolation tests (workspace/session/auth boundaries)
- [ ] Task registry persistence + reconciliation tests
- [ ] Approval engine tests (ask modes, allowlist, fallback)
- [ ] Doctor/audit tests (finding generation + fix application)
- [ ] Plugin trust policy tests (allow/deny/scan block)
- [ ] Subagent lifecycle and depth-limit tests
- [ ] ACP bridge session mapping tests
- [ ] Deep Research v2 confidence/citation tests
- [ ] Enterprise auth/policy enforcement tests
- [ ] Coding/review agent artifact tests
- [ ] Cross-surface state handoff tests

## 5. Risk Controls

- [ ] Add feature flags for each major subsystem
- [ ] Add migration adapters for old API payloads
- [ ] Keep old code path until new path is verified by tests
- [ ] Add rollback plan per phase

## 6. Suggested Commit Sequence

1. Protocol schema and WS validator
2. Agent runtime boundaries
3. Task registry + flow
4. Approval engine
5. Doctor/audit
6. Plugin/skill governance
7. Subagents + ACP bridge

## 7. Handoff Completion Criteria

Mark this handoff complete only when:
- [ ] All phase checkboxes are done
- [ ] Regression suite passes
- [ ] Existing LADA UX remains functional (GUI, Web, API, messaging)
- [ ] New runtime architecture is documented in docs/ARCHITECTURE.md

## 8. New Chat Starter Prompt

Use this exact prompt in a new chat to continue execution:

Continue implementing docs/LADA_OPENCLAW_VERIFIED_PLAN_2026-04-07.md using docs/LADA_OPENCLAW_TODO_HANDOFF_2026-04-07.md as the checklist. Start from Phase 0 and complete items in order. Keep backward compatibility, add tests for each phase, and report progress by checkbox updates in the TODO file.
