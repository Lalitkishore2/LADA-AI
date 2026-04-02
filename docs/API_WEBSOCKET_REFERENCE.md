# LADA API and WebSocket Reference

Last updated: 2026-04-02
Status: Operational reference

This file documents the active API surface and WebSocket protocol used by LADA clients.

## 1. Server runtime

- API launcher: `modules/api_server.py`
- Router package: `modules/api/routers/`
- Default local port: `5000`

## 2. Authentication model

Two auth contexts exist:

1. Web app session auth
- Login endpoint issues session token.
- Token used as Bearer auth for protected routes.
- WebSocket token passed in query string.

2. OpenAI-compatible API key auth (`/v1/*`)
- Controlled by `LADA_API_KEY`.
- Intended for external API-style clients.

## 3. Router groups and key endpoints

## 3.1 Auth router
Typical endpoints:
- `POST /auth/login`
- `GET /auth/check`
- `POST /auth/logout`

Purpose:
- Authenticate web clients and validate active sessions.

## 3.2 Chat router
Typical endpoints:
- `POST /chat`
- `POST /chat/stream`
- Conversation retrieval endpoints under `/conversations/*`

Purpose:
- Primary chat interaction over REST.

## 3.3 App router
Typical endpoints:
- app/session/cost/dashboard helpers
- `GET /rollout/status`
- `GET /remote/status`
- `POST /remote/command`
- `GET /remote/files`
- `GET /remote/download`

Purpose:
- UI-facing metadata and application status endpoints.

`GET /rollout/status` key behavior:
- Returns rollout stage, readiness blockers, and remote/funnel status.
- Optional query: `deep_check=true` to perform deeper funnel state checks.

## 3.4 Marketplace router
Typical endpoints:
- marketplace listing and plugin operation routes

Purpose:
- Plugin lifecycle APIs (list/install/update/remove).

## 3.5 Orchestration router
Typical endpoints:
- plan/workflow/task/skill endpoints
- `POST /orchestrator/dispatch`
- `GET /orchestrator/subscriptions`

Purpose:
- Higher-level task orchestration and planning operations.

`GET /orchestrator/subscriptions` returns event-stream observability fields:
- `enabled`
- `orchestrator_available`
- `stream_active`
- `subscriber_count`
- optional `sessions` (controlled by `include_sessions` query param)

## 3.6 OpenAI compatibility router
Typical endpoints:
- `GET /v1/models`
- `POST /v1/chat/completions`

Purpose:
- Compatibility with OpenAI-style client tooling.

## 3.7 WebSocket router
Endpoint:
- `GET /ws` (WebSocket upgrade)

Purpose:
- Low-latency bidirectional chat/events.

## 4. Request and response patterns

## 4.1 REST (chat)
Typical request fields:
- `message`
- `model` (optional)
- `session_id`/conversation metadata (optional)

Typical response fields:
- `response`
- `model`
- `timestamp`
- optional usage/cost metadata

## 4.2 OpenAI-compatible chat
Request pattern follows OpenAI-style shape:
- `model`
- `messages`
- `stream` (optional)

Response pattern:
- non-stream JSON completion payload
- stream mode SSE chunks until completion marker

## 4.3 Request correlation and traceability
- REST routers expose correlation via `X-Request-ID` response header.
- If a client sends `X-Request-ID`, LADA normalizes and echoes that ID.
- Chat stream payloads include `request_id` on terminal (`done`) and error frames.
- Use this value to correlate UI logs, API logs, and audit events.

`POST /remote/command` idempotency:
- Optional request header: `Idempotency-Key`.
- Repeating the same key with the same command replays the cached success response.
- Reusing the same key with a different command returns `409` conflict.

## 5. WebSocket protocol

## 5.1 Connection
- URI: `ws://<host>:<port>/ws?token=<session_token>`
- Connection is rejected if token validation fails.

## 5.2 Session controls
- Per-IP connection limit enforcement
- Idle timeout enforcement
- Message-size guards
- Rate-limit window counters

## 5.3 Message envelope
Generic inbound/outbound shape:
- `type`: message category
- `data`: payload object

Correlation fields:
- Client may send `request_id` or `correlation_id` in inbound frames.
- Server normalizes to a stable `request_id` value.
- Success and error frames propagate `request_id` for traceability.

Common `type` values:
- `chat`
- `chat.chunk`
- `chat.done`
- `error`
- `system` events
- `orchestrator` (dispatch + stream control)
- `orchestrator.response`
- `orchestrator.subscribed`
- `orchestrator.unsubscribed`
- `orchestrator.event`

Notable success frames with `request_id` propagation:
- `system.status`, `system.models`, `system.ack`
- `plan.created`, `plan.done`, `plan.list`, `plan.cancelled`
- `workflow.list`, `workflow.created`, `workflow.done`
- `task.list`, `task.created`, `task.status`, `task.paused`, `task.resumed`, `task.cancelled`

## 5.4 Streaming behavior
- Server sends incremental chunk events while model output is streaming.
- Terminal completion event signals end of stream.

## 5.5 Error behavior
- Invalid auth: connection closed with auth reason code.
- Rate limit: error payload and/or throttling behavior.
- Invalid payload: structured error message.

## 5.6 Orchestrator over WebSocket

Inbound message (`type=orchestrator`) supports two modes:

1. Dispatch mode (default)
- Submit a command envelope to the standalone orchestrator.
- Returns `orchestrator.response` with accepted status and optional terminal result event.

2. Event stream control mode
- Set `orchestrator_action` in `data` to:
  - `subscribe`: begin receiving lifecycle events for all orchestrator commands.
  - `unsubscribe`: stop receiving lifecycle events.
  - `status`: check current subscription status.

Optional on `subscribe`:
- `filters` object to limit delivered `orchestrator.event` frames per session.
- Supported fields (string or list):
  - `event_type` / `event_types`
  - `target` / `targets`
  - `correlation_id` / `correlation_ids`
  - `command_id` / `command_ids`
  - `status` / `statuses`

`orchestrator.subscribed` and `orchestrator.status` responses include normalized `filters`.

When subscribed, server pushes:
- `orchestrator.event` with the event envelope in `data.event`.

Example subscribe payload:
```json
{
  "type": "orchestrator",
  "id": "msg-1",
  "data": {
    "orchestrator_action": "subscribe",
    "filters": {
      "event_type": ["command.completed", "command.failed"],
      "target": "system",
      "correlation_id": "corr_1234"
    }
  }
}
```

Example dispatch payload:
```json
{
  "type": "orchestrator",
  "id": "msg-2",
  "data": {
    "source": "ws",
    "target": "system",
    "action": "execute",
    "payload": {
      "command": "set volume to 40"
    },
    "wait": true,
    "timeout_ms": 60000
  }
}
```

## 6. Operational safeguards

1. Token/session validation before privileged operations.
2. Rate-limits to protect backend and provider quotas.
3. Size and idle guards for WebSocket stability.
4. Sanitized error output to clients.

## 7. Environment variables (high impact)

- `LADA_WEB_PASSWORD`
- `LADA_SESSION_TTL`
- `LADA_API_KEY`
- Provider API keys (`GEMINI_API_KEY`, `GROQ_API_KEY`, etc.)
- Optional CORS controls

## 8. Minimal usage examples

## 8.1 REST chat
```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
```

## 8.2 OpenAI models
```bash
curl http://localhost:5000/v1/models \
  -H "Authorization: Bearer <LADA_API_KEY>"
```

## 8.3 OpenAI chat completions
```bash
curl -X POST http://localhost:5000/v1/chat/completions \
  -H "Authorization: Bearer <LADA_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role":"user","content":"Summarize LADA architecture."}],
    "stream": false
  }'
```

## 8.4 WebSocket
```text
ws://localhost:5000/ws?token=<session_token>
```

## 9. Verification pointer

For runnable validation command sets, use:
- `docs/VALIDATION_PLAYBOOK.md`
