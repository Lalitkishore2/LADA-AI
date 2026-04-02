# LADA Unified Integration Plan

Last updated: 2026-03-31
Status: Implementation blueprint

## 1. Goal

Make LADA run a unified architecture that combines:
- OpenClaw-style skills and gateway integrations
- Comet autonomous screen agent
- Copilot-style laptop assistant behavior (intent -> tools -> execution)
- Anti-gravity browser control (stealth + human-like automation)

This plan prioritizes safe rollout, backward compatibility, and measurable milestones.

## 2. Verified Current State

### 2.1 OpenClaw Components
- OpenClaw gateway and SKILL.md loader are archived under archived/integrations and not active in runtime imports.
- OpenClaw-inspired patterns exist in active modules (context/session/pipeline/tool architecture), but direct OpenClaw bridge runtime is disabled.

### 2.2 Comet Components
- Comet agent is active and integrated in browser command handling.
- Visual grounding with Set-of-Mark (SoM) is active in Comet flow.
- Desktop overlay for autonomous task progress is present and wired.

### 2.3 Copilot-Style Laptop Assistant Components
- AI Command Agent is active in desktop command flow.
- Tool registry and tool handlers are active and wired in AI router.
- Specialist delegation exists, but uses basic keyword matching and returns delegation status rather than full merged completion flow.

### 2.4 Anti-Gravity Browser Components
- Stealth browser module exists with anti-detection and human-like interaction primitives.
- It is not wired into service registry, browser executor, or tool registry/handlers.

### 2.5 Plugin System Components
- Plugin registry and marketplace are active and API-exposed.
- Plugin capability execution path exists in plugin_system, but command pipeline integration is minimal.

## 3. Architectural Target

Create a unified execution stack:

1. Intent Layer
- Single classifier for command types: system, browser, plugin-skill, specialist, AI reasoning.

2. Action Layer
- Unified tool/action runtime for:
  - system tools
  - Comet actions
  - stealth browser actions
  - plugin/skill handlers
  - specialist agent tasks

3. Compatibility Layer
- OpenClaw SKILL.md compatibility adapter -> native LADA plugin manifest/capability mapping.

4. Transport Layer
- API and WebSocket support for desktop/web/messaging and optional OpenClaw gateway bridge mode.

5. Safety Layer
- Safety gate + permission level + bounded retries + rate limits + audit logs.

## 4. Implementation Phases

## Phase 0 - Baseline and Guardrails (1 day)

Deliverables:
- Create feature branch and freeze baseline behavior.
- Capture current metrics: startup time, command success rate, tool-call success rate, Comet task success rate.
- Confirm test baseline.

Tasks:
- Run medium validation suite.
- Add baseline metric capture script for command and tool telemetry.

Exit criteria:
- Baseline test and telemetry snapshots stored under logs or docs.

## Phase 1 - Reactivate OpenClaw Compatibility (2-3 days)

Deliverables:
- OpenClaw gateway and SKILL loader restored as optional integrations.
- No regressions when OpenClaw mode is disabled.

Tasks:
1. Move these back to active integrations:
- integrations/openclaw_gateway.py
- integrations/openclaw_skills.py

2. Update exports:
- integrations/__init__.py TYPE_CHECKING and __all__.

3. Register optional services:
- core/services.py
  - openclaw_gateway
  - openclaw_skills

4. Add env-gated initialization:
- LADA_OPENCLAW_MODE=true|false
- LADA_OPENCLAW_GATEWAY_URL

Exit criteria:
- Services probe cleanly.
- OpenClaw mode off by default.
- OpenClaw mode on initializes without crashing core app.

## Phase 2 - Unify OpenClaw Skills with Plugin System (3-4 days)

Deliverables:
- SKILL.md and plugin.json both supported by one registry path.

Tasks:
1. Add compatibility adapter module:
- modules/openclaw_skill_adapter.py
- Parse SKILL.md frontmatter and actions.
- Map into PluginManifest-compatible structure.

2. Extend discovery in plugin system:
- modules/plugin_system.py
- Discover SKILL.md and .skill.md in plugin directories.
- Convert to synthetic capability handlers.

3. Activate execution path:
- Integrate plugin execute_handler into command flow after tool/system checks.
- Return plugin execution response directly when matched.

4. Hot-reload compatibility:
- Ensure watcher reloads SKILL.md updates with debounce.

Exit criteria:
- Example SKILL.md runs end-to-end through command input.
- Existing plugin.json plugins continue working unchanged.

## Phase 3 - Copilot + Comet Orchestration Hardening (3-5 days)

Deliverables:
- Reliable cross-routing between AI Command Agent, specialists, plugins, and Comet.

Tasks:
1. Fix Comet import path mismatch in voice NLU fallback.

2. Improve specialist delegation lifecycle:
- AI Command Agent should optionally wait/poll for specialist completion where appropriate.
- Return actionable result, not only delegation acknowledgment.

3. Add shared action planner:
- For multi-step laptop tasks, select between:
  - direct tool calls
  - Comet autonomous loop
  - specialist pool
  - plugin skill handler

4. Add unified telemetry fields:
- intent_type, executor_used, tool_count, fallback_count, final_status.

Exit criteria:
- Multi-step tasks consistently choose best executor.
- Delegated specialist tasks can return usable final output to user.

## Phase 4 - Wire Anti-Gravity Browser Control (2-4 days)

Deliverables:
- Stealth browser available via tools and executor routes.

Tasks:
1. Register stealth browser service:
- core/services.py

2. Add tool definitions and handlers:
- modules/tool_registry.py
  - stealth_navigate
  - stealth_click
  - stealth_type
  - stealth_scroll
  - stealth_extract
- modules/tool_handlers.py
  - map handlers to modules/stealth_browser.py

3. Add browser executor routing for explicit stealth commands:
- Examples: use stealth browser, undetected mode, anti bot mode.

4. Add safety bounds:
- domain allowlist option
- max navigation depth
- per-command timeout

Exit criteria:
- Stealth flow can complete scripted browse/search/fill tasks.
- Normal browser flow remains default unless explicitly requested.

## Phase 5 - API and Gateway Unification (3-5 days)

Deliverables:
- Optional OpenClaw bridge mode exposed over API/WebSocket.
- Unified protocol envelope for desktop/web/connectors.

Tasks:
1. Add optional API router for compatibility mode:
- modules/api/routers/openclaw_compat.py

2. Add WS event schema mapping:
- map OpenClaw-style events to LADA internal event types.

3. Add auth and rate-limit guardrails for compatibility endpoints.

Exit criteria:
- Gateway mode can proxy key actions safely.
- Existing API and WS behavior remains backward compatible.

## Phase 6 - Validation and Rollout (2-3 days)

Deliverables:
- Production-ready rollout with staged flags.

Tasks:
1. Add tests:
- SKILL.md parser and execution
- stealth browser tool handlers
- Comet + plugin + specialist routing integration
- OpenClaw compatibility endpoint tests

2. Add rollout flags:
- LADA_OPENCLAW_MODE
- LADA_STEALTH_BROWSER_ENABLED
- LADA_SKILL_MD_ENABLED

3. Staged deployment:
- desktop internal testing
- API/WebSocket testing
- messaging connector testing

Exit criteria:
- Regression suite passes.
- Feature flags allow safe rollback.

## 5. High-Risk Areas and Mitigations

1. Integration complexity across command paths
- Mitigation: strict routing precedence and telemetry-based tracing.

2. Optional dependency churn (watchdog, playwright, undetected_chromedriver)
- Mitigation: graceful degradation and explicit feature flags.

3. Security risk in plugin/skill execution
- Mitigation: keep safety gate, permission levels, and restrictive handler allowlists.

4. Runtime instability in autonomous loops
- Mitigation: max-step and retry caps, pause/stop controls, timeout hard limits.

## 6. Suggested Routing Precedence

1. Hard system/safety commands
2. AI Command Agent tool execution
3. Specialist delegation
4. Plugin/SKILL handler execution
5. Comet autonomous execution for multi-step UI tasks
6. AI reasoning fallback

This order avoids plugin collisions with safety/system controls while preserving autonomous capability.

## 7. Acceptance Criteria

Functional:
- OpenClaw skills can run through LADA plugin path.
- Comet and AI agent coexist without command routing conflicts.
- Stealth browser is callable through tools/executor.

Quality:
- No startup crashes when optional modules are absent.
- Existing router/API/memory tests remain green.
- New integration tests cover all added routes.

Operational:
- Feature flags can disable each new subsystem independently.
- Observability shows executor path and failures clearly.

## 8. Immediate Next 5 Tasks

1. Restore openclaw_gateway.py and openclaw_skills.py to integrations with env-gated startup only.
2. Add openclaw service registrations in core/services.py.
3. Implement SKILL.md to PluginManifest adapter and wire it into plugin discovery.
4. Wire plugin execute_handler into command pipeline with safe precedence.
5. Register and expose stealth browser via tool registry and tool handlers.
