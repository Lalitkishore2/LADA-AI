# LADA OpenClaw Parity Master Matrix (Canonical)

Last verified: 2026-04-19

This is the canonical parity tracker for this workstream. Use this file as the single source of truth for status.

Historical snapshots (do not update for active status tracking):
- `docs/LADA_OPENCLAW_VERIFIED_PLAN_2026-04-07.md`
- `docs/LADA_OPENCLAW_TODO_HANDOFF_2026-04-07.md`

Status legend:
- **Implemented**: present and live in primary runtime paths
- **Partial**: foundation exists, but live-path integration is incomplete
- **Missing**: not implemented in the current runtime

## Current parity matrix

| Capability area | Status | Repo evidence | Remaining update |
| --- | --- | --- | --- |
| Gateway protocol schema + validator | Implemented | `modules/gateway_protocol/schema.py`, `modules/gateway_protocol/validator.py`, `modules/api/routers/websocket.py` | Keep compatibility fixtures updated as protocol evolves |
| Agent registry and binding primitives | Partial | `modules/agent_runtime/agent_registry.py`, `modules/agent_runtime/bindings.py` | Wire binding resolution into live WS, messaging, and desktop routing paths |
| Agent-scoped session namespacing | Implemented | `modules/session_manager.py` | Align all entry paths to create/load sessions with explicit `agent_id` |
| Unified task registry + flow runtime | Partial | `modules/tasks/task_registry.py`, `modules/tasks/task_flow_registry.py`, `modules/api/routers/orchestration.py`, `modules/api/routers/websocket.py` | Complete write-path migration from legacy `/tasks` and `/workflows` to `/registry/*`; legacy read/status paths now converge on registry with fallback |
| Web task/workflow UI on registry APIs | Partial | `web/lada_app.html`, `modules/api/routers/orchestration.py`, `modules/api/routers/websocket.py` | Keep compatibility fallback while migrating remaining legacy-only callers and websocket/desktop write paths to registry-native operations |
| Approval queue + policy engine | Implemented | `modules/approval/approval_queue.py`, `modules/approval/policy_engine.py`, `modules/approval/approval_hooks.py`, `modules/api/routers/orchestration.py` | Expand callsite coverage so high-risk executors use the same approval hooks |
| Doctor diagnostics and auto-fix CLI | Implemented | `modules/doctor/diagnostics.py`, `modules/doctor/auto_fix.py`, `main.py` | Add stricter CI coverage for remediation-safe checks |
| Plugin trust/policy/scanner services | Partial | `modules/plugins/trust.py`, `modules/plugins/policy.py`, `modules/plugins/scanner.py`, `modules/api/routers/marketplace.py` | Enforce policy/scanning in `modules/plugin_system.py` load/install paths |
| Subagent runtime and limits | Partial | `modules/subagents/runtime.py`, `modules/subagents/limits.py`, `modules/api/routers/orchestration.py` | Complete broader runtime wiring and surfaced controls across all channels |
| ACP bridge session server | Partial | `modules/acp_bridge/server.py`, `modules/acp_bridge/protocol.py`, `modules/api/routers/websocket.py` | Expand policy and observability coverage for ACP lifecycle in production flows |
| Deep research with parallel search + citations | Partial | `modules/deep_research.py` | Add reliability scoring, confidence metadata, and export templates |
| Desktop voice lifecycle hardening | Partial | `modules/continuous_listener.py`, `modules/advanced_voice.py`, `lada_desktop_app.py` | Converge desktop defaults on shared `voice/voice_pipeline.py` path |
| Browser gateway integration | Partial | `integrations/lada_browser_adapter.py` | Replace archived-shim dependency with first-class maintained gateway integration |
| Cross-surface continuation (desktop/web/CLI/bridge) | Missing | `lada_desktop_app.py`, `web/lada_app.html`, `modules/remote_bridge_client.py` | Add resumable task/session handoff contract and recovery semantics |
| Enterprise policy controls (RBAC/SSO/org policy/MCP governance) | Missing | Current repo has no dedicated enterprise policy center module | Implement policy center and org-scoped governance surfaces |

## Source-of-truth corrections for external planning notes

The following path examples are referenced in external design notes but do not exist in this repo:
- `agents/browseragent.py`
- `tools/browsercontrol.py`
- `core/brain.py`
- `core/agentrouter.py`
- `core/toolexecutor.py`
- `ui/desktopoverlay.py`

Use the module paths in this matrix as authoritative references for current implementation state.

## Execution order (from this matrix)

1. Runtime convergence: agent bindings + registry endpoint migration + plugin policy enforcement
2. Web channel parity: approvals/tasks/subagent views and safer remote-control UX
3. Voice/browser modernization: voice pipeline convergence and maintained browser gateway path
4. Advanced parity tracks: deep-research v2, cross-surface continuity, enterprise governance
