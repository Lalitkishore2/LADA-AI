# LADA Parity Master Plan (Claude + Perplexity + Copilot + OpenClaw + OpenJarvis + Jarvis)

Date: 2026-04-07

## 1) Scope and sources reviewed

This plan is based on:

- Public product/docs/repo references provided by user:
  - OpenClaw core repo and docs links
  - Awesome OpenClaw Agents
  - OpenJarvis
  - Jarvis project site + repo
  - Antigravity Awesome Skills
  - Perplexity Comet / Computer / Deep Research / security posts
  - GitHub Copilot feature + docs pages
  - Claude Code docs overview
- Local LADA architecture snapshot and codebase map
- Local `claude code source code` folder structure and key architecture files

Important note:

- The requested leaked reference (`ccleaks.com`) is intentionally excluded from implementation guidance. This plan uses public/authorized references and local code that exists in the workspace.

## 2) Current LADA baseline (already strong)

LADA already has significant overlap with requested platforms:

- Multi-provider model routing + fallbacks + rate limits
- Desktop + web app + API + WebSocket gateway
- Voice control and wake workflows
- Comet-like screen agent foundations (visual grounding + automation)
- Plugin marketplace, tool registry, hot reload
- Deep research, RAG, vector memory, proactive behavior
- Multi-channel messaging connectors

Key baseline files:

- [CLAUDE.md](./CLAUDE.md)
- [core/services.py](../core/services.py)
- [modules/comet_agent.py](../modules/comet_agent.py)
- [modules/visual_grounding.py](../modules/visual_grounding.py)
- [modules/ai_command_agent.py](../modules/ai_command_agent.py)
- [modules/plugin_marketplace.py](../modules/plugin_marketplace.py)
- [modules/tool_registry.py](../modules/tool_registry.py)
- [modules/tool_handlers.py](../modules/tool_handlers.py)
- [modules/rate_limiter.py](../modules/rate_limiter.py)
- [modules/api/routers/chat.py](../modules/api/routers/chat.py)
- [modules/api/routers/websocket.py](../modules/api/routers/websocket.py)

## 3) What is missing to reach "all features" parity

Below are the highest-impact missing capabilities across all references.

### P0 (must-have foundation)

1. Multi-machine sidecar architecture
- Add authenticated sidecars (laptop/server/mobile nodes) with capability advertisement.
- Required for true Copilot/OpenClaw/Jarvis-style "one brain, many machines" operation.

2. First-class authority engine
- Central approvals and policy gates for sensitive actions.
- Approval queue, reasoned policy decisions, audit history, emergency kill switch.

3. Computer-use security stack
- Prompt-injection detection pipeline for browser/screen automation.
- Sensitive action confirmations and transparent action notifications.

4. Deterministic workflow runtime
- Durable workflow engine (cron/webhook/file/screen triggers, retries, fallback, compensation).
- Execution graph persistence and resumable runs.

5. Unified task runtime (long-running agents)
- Background task manager with status, logs, cancellation, priorities, and checkpointing.

### P1 (major product differentiators)

6. Skills platform v2
- Installable skill packs, bundles, workflows, selective activation (by risk/category/tags).
- Skill validation, indexing, and dependency metadata.

7. Plugin security + governance
- Plugin signature verification, allow/block policy, capability permissions, sandbox profile.
- Marketplace trust levels and provenance metadata.

8. Advanced research pipeline
- Multi-hop planner + source reliability scoring + citation grading + report export templates.
- "Deep Research mode" with explicit stage timeline and confidence.

9. Multi-agent orchestrator
- Role-based specialist agents with dependency graph and parallel execution.
- Parent/child authority boundaries and bounded autonomy.

10. Session memory hierarchy
- Fast short-term memory, episodic memory, semantic memory, and explicit user memory contracts.

### P2 (enterprise and scale)

11. Enterprise controls
- SSO/OAuth enterprise auth, RBAC, project/org policies, audit exports, retention controls.

12. MCP governance controls
- Allowlisted MCP registry, per-project server policy, runtime consent scopes, usage analytics.

13. Channel expansion parity
- Add missing channels and richer integrations (beyond current connectors) with consistent policy gates.

14. Ops and reliability platform
- Doctor command, health checks, auto-repair runbooks, migration tooling, staged rollout channels.

### P3 (ecosystem acceleration)

15. Agent templates marketplace
- SOUL/AGENTS template catalog, one-click deployment presets, quickstart generator.

16. Learning loop and evals
- Continuous eval harness (task success, latency, cost, safety incidents, user corrections).
- Local trace learning and prompt/policy optimization loops.

17. Cross-surface continuity
- Start task on desktop, continue on web/mobile/CLI with synchronized context.

## 4) Capability-by-capability add list

## A) Claude Code parity themes

Add:

- Robust skills lifecycle: discovery, indexing, cache invalidation, dynamic load.
- Agent teams + subagents with scoped tool permissions.
- Scheduled tasks and remote-control continuation pointers.
- Plugin command + plugin skill merge order, fallback-safe load behavior.

Implementation targets in LADA:

- Extend [modules/tool_registry.py](../modules/tool_registry.py) and [modules/tool_handlers.py](../modules/tool_handlers.py) with skill index APIs and capability metadata.
- Add new runtime package: `modules/agent_runtime/` for task/session/subagent orchestration.
- Add scheduler integration in [core/executors/workflow_executor.py](../core/executors/workflow_executor.py).

## B) Perplexity Comet and Computer parity themes

Add:

- Browser assistant transparency panel (show clicks, scrolls, decisions, current stage).
- User-mode toggles: suggest-only, ask-once, auto-browse.
- Sensitive action pauses: purchases, account changes, external sends.
- Prompt-injection defense-in-depth:
  - Real-time classifier
  - Guardrailed structured prompts
  - Confirmation step
  - Block notifications + forensics logs
- Multi-model orchestration per subtask with explicit budget routing.

Implementation targets in LADA:

- Extend [modules/comet_agent.py](../modules/comet_agent.py) with observable action timeline and permission checkpoints.
- Add browser safety middleware in [modules/browser_automation.py](../modules/browser_automation.py).
- Add policy checks in [modules/safety_controller.py](../modules/safety_controller.py).

## C) Copilot parity themes

Add:

- Cloud/background coding agent mode for issues/PR tasks.
- Built-in code review agent with inline remediation suggestions.
- Agentic memory per repository.
- Enterprise controls panel for third-party agents and MCP servers.

Implementation targets in LADA:

- New `modules/code_agent/` service for background code tasks.
- Add PR/code-review mode to API in [modules/api/routers/orchestration.py](../modules/api/routers/orchestration.py).

## D) OpenClaw parity themes

Add:

- Gateway control plane protocol as single control surface.
- Node/sidecar pairing and device capabilities registry.
- Session-to-session communication primitives.
- Non-main session sandbox isolation by default for untrusted channels.
- Channel policy defaults (pairing, allowlists, mention gating).

Implementation targets in LADA:

- New `modules/gateway/` for unified control protocol.
- New `modules/nodes/` for sidecar registration/invoke lifecycle.

## E) OpenJarvis parity themes

Add:

- Local-first execution objective with cloud fallback by explicit policy.
- Hardware-aware model backend auto-selection.
- Built-in presets (morning digest, deep research, code assistant, persistent monitor).
- Efficiency metrics as first-class runtime output (latency, cost, power proxy).

Implementation targets in LADA:

- Extend [modules/providers/provider_manager.py](../modules/providers/provider_manager.py) with policy-driven local-first route mode.
- Add preset loader in [main.py](../main.py) and onboarding flows.

## F) Jarvis parity themes

Add:

- Sidecar with desktop/browser/filesystem/terminal capability bundles.
- Awareness pipeline at fixed cadence with struggle detection.
- Authority dashboard + approval channels.
- Visual workflow builder with 50+ node types and self-heal strategies.
- Goal pursuit system (objective/key-results/daily actions) tied to awareness signals.

Implementation targets in LADA:

- Extend [lada_desktop_app.py](../lada_desktop_app.py) with authority and awareness operator surfaces.
- Add `modules/goal_engine.py` and `modules/awareness_pipeline.py`.

## G) Antigravity skills ecosystem themes

Add:

- Skill pack installer with selective install flags: category, tags, risk.
- Bundle recommendations by persona (developer, security, devops, research, etc.).
- Workflow templates that chain skill invocations.
- Skill validation checks before activation.

Implementation targets in LADA:

- Extend [modules/plugin_marketplace.py](../modules/plugin_marketplace.py) to support "skill-pack" type packages.
- Add skill metadata index in `skills/` with registry JSON.

## 5) Phased implementation roadmap

## Phase 0 (1-2 weeks): Safety + control baseline

Deliver:

- Authority engine MVP (approve/deny queue + audit log + kill switch)
- Sensitive action policy hooks in browser/screen tooling
- Basic action transparency stream in UI

Exit criteria:

- Every high-risk action requires explicit policy decision path.
- Full audit trail queryable by session.

## Phase 1 (2-4 weeks): Sidecar and gateway foundation

Deliver:

- JWT-authenticated sidecar protocol (desktop + terminal + filesystem)
- Capability registry and node heartbeat
- Gateway control plane APIs (sessions, nodes, tasks)

Exit criteria:

- LADA orchestrates at least two remote nodes in one workflow.

## Phase 2 (2-3 weeks): Task runtime + workflow durability

Deliver:

- Durable task manager (queued/running/completed/failed/canceled)
- Workflow execution DAG with retries/fallback and persisted state
- Scheduled tasks with recovery after restart

Exit criteria:

- Long-running workflows resume correctly after process restart.

## Phase 3 (2-3 weeks): Skills and plugin platform v2

Deliver:

- Skill pack installer + selective activation
- Plugin trust model (signing/provenance/capability policy)
- Bundle/workflow presets

Exit criteria:

- Skills and plugins can be governed and rolled out safely per workspace.

## Phase 4 (2-4 weeks): Computer-use and deep research v2

Deliver:

- Prompt-injection defense layers
- Multi-tab/multi-step browser assistant execution timeline
- Deep research planner with citation confidence and export modes

Exit criteria:

- Research reports include confidence/citation structure and reproducible trace.

## Phase 5 (2-3 weeks): Multi-agent and developer productivity parity

Deliver:

- Specialist agent roles and dependency orchestration
- Background coding agent + code review mode
- Repository memory and cross-session continuity

Exit criteria:

- Agent teams can complete complex coding/research tasks with bounded autonomy.

## Phase 6 (ongoing): Enterprise and ecosystem scale

Deliver:

- RBAC/SSO/policy center
- MCP governance and analytics
- Expanded connectors and template marketplace

Exit criteria:

- Enterprise-grade control and observability across all surfaces.

## 6) Recommended implementation order for maximum value

Do these first:

1. Authority engine + safety controls (prevents unsafe autonomy)
2. Sidecar/gateway foundation (enables true multi-machine assistant)
3. Durable tasks/workflows (turns LADA into reliable autonomous runtime)
4. Skills/plugin governance (safe ecosystem growth)
5. Computer-use defense + deep research v2 (major user-visible differentiation)

## 7) Concrete first sprint backlog (ready to execute)

Sprint 1 stories:

1. Add `ActionPolicyEngine` with policy decision API
2. Add `ApprovalQueue` data model + UI panel
3. Instrument `comet_agent` actions with explainable step log
4. Add high-risk action classifiers (purchase/send/delete/external auth)
5. Add `task_runtime` table/schema and background worker
6. Add initial node registration protocol (`node.register`, `node.heartbeat`)
7. Add integration tests for policy-gated browser actions

Definition of done for Sprint 1:

- High-risk actions are blocked without explicit policy.
- Operator can inspect, approve, deny, and audit actions.
- System can execute and track at least one persistent background task.

## 8) Final takeaway

LADA already has the right building blocks. The main gap is not basic capability count, but runtime architecture maturity:

- multi-machine execution model
- strict authority and safety governance
- durable autonomous workflow/task runtime
- scalable skills/plugin ecosystem with trust controls

If you execute the phases above in order, LADA will move from "feature-rich assistant" to "full autonomous agent operating layer" comparable to the strongest patterns across Claude/Copilot/Comet/OpenClaw/OpenJarvis/Jarvis.
