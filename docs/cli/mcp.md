---
summary: "Expose LADA channel conversations over MCP and manage saved MCP server definitions"
read_when:
  - Connecting Codex, LADA, or another MCP client to LADA-backed channels
  - Running `lada mcp serve`
  - Managing LADA-saved MCP server definitions
title: "mcp"
---

# mcp

`lada mcp` has two jobs:

- run LADA as an MCP server with `lada mcp serve`
- manage LADA-owned outbound MCP server definitions with `list`, `show`,
  `set`, and `unset`

In other words:

- `serve` is LADA acting as an MCP server
- `list` / `show` / `set` / `unset` is LADA acting as an MCP client-side
  registry for other MCP servers its runtimes may consume later

Use [`lada acp`](/cli/acp) when LADA should host a coding harness
session itself and route that runtime through ACP.

## LADA as an MCP server

This is the `lada mcp serve` path.

## When to use `serve`

Use `lada mcp serve` when:

- Codex, LADA, or another MCP client should talk directly to
  LADA-backed channel conversations
- you already have a local or remote LADA Gateway with routed sessions
- you want one MCP server that works across LADA's channel backends instead
  of running separate per-channel bridges

Use [`lada acp`](/cli/acp) instead when LADA should host the coding
runtime itself and keep the agent session inside LADA.

## How it works

`lada mcp serve` starts a stdio MCP server. The MCP client owns that
process. While the client keeps the stdio session open, the bridge connects to a
local or remote LADA Gateway over WebSocket and exposes routed channel
conversations over MCP.

Lifecycle:

1. the MCP client spawns `lada mcp serve`
2. the bridge connects to Gateway
3. routed sessions become MCP conversations and transcript/history tools
4. live events are queued in memory while the bridge is connected
5. if LADA channel mode is enabled, the same session can also receive
   LADA-specific push notifications

Important behavior:

- live queue state starts when the bridge connects
- older transcript history is read with `messages_read`
- LADA push notifications only exist while the MCP session is alive
- when the client disconnects, the bridge exits and the live queue is gone

## Choose a client mode

Use the same bridge in two different ways:

- Generic MCP clients: standard MCP tools only. Use `conversations_list`,
  `messages_read`, `events_poll`, `events_wait`, `messages_send`, and the
  approval tools.
- LADA: standard MCP tools plus the LADA-specific channel adapter.
  Enable `--lada-channel-mode on` or leave the default `auto`.

Today, `auto` behaves the same as `on`. There is no client capability detection
yet.

## What `serve` exposes

The bridge uses existing Gateway session route metadata to expose channel-backed
conversations. A conversation appears when LADA already has session state
with a known route such as:

- `channel`
- recipient or destination metadata
- optional `accountId`
- optional `threadId`

This gives MCP clients one place to:

- list recent routed conversations
- read recent transcript history
- wait for new inbound events
- send a reply back through the same route
- see approval requests that arrive while the bridge is connected

## Usage

```bash
# Local Gateway
lada mcp serve

# Remote Gateway
lada mcp serve --url wss://gateway-host:18789 --token-file ~/.lada/gateway.token

# Remote Gateway with password auth
lada mcp serve --url wss://gateway-host:18789 --password-file ~/.lada/gateway.password

# Enable verbose bridge logs
lada mcp serve --verbose

# Disable LADA-specific push notifications
lada mcp serve --lada-channel-mode off
```

## Bridge tools

The current bridge exposes these MCP tools:

- `conversations_list`
- `conversation_get`
- `messages_read`
- `attachments_fetch`
- `events_poll`
- `events_wait`
- `messages_send`
- `permissions_list_open`
- `permissions_respond`

### `conversations_list`

Lists recent session-backed conversations that already have route metadata in
Gateway session state.

Useful filters:

- `limit`
- `search`
- `channel`
- `includeDerivedTitles`
- `includeLastMessage`

### `conversation_get`

Returns one conversation by `session_key`.

### `messages_read`

Reads recent transcript messages for one session-backed conversation.

### `attachments_fetch`

Extracts non-text message content blocks from one transcript message. This is a
metadata view over transcript content, not a standalone durable attachment blob
store.

### `events_poll`

Reads queued live events since a numeric cursor.

### `events_wait`

Long-polls until the next matching queued event arrives or a timeout expires.

Use this when a generic MCP client needs near-real-time delivery without a
LADA-specific push protocol.

### `messages_send`

Sends text back through the same route already recorded on the session.

Current behavior:

- requires an existing conversation route
- uses the session's channel, recipient, account id, and thread id
- sends text only

### `permissions_list_open`

Lists pending exec/plugin approval requests the bridge has observed since it
connected to the Gateway.

### `permissions_respond`

Resolves one pending exec/plugin approval request with:

- `allow-once`
- `allow-always`
- `deny`

## Event model

The bridge keeps an in-memory event queue while it is connected.

Current event types:

- `message`
- `exec_approval_requested`
- `exec_approval_resolved`
- `plugin_approval_requested`
- `plugin_approval_resolved`
- `lada_permission_request`

Important limits:

- the queue is live-only; it starts when the MCP bridge starts
- `events_poll` and `events_wait` do not replay older Gateway history by
  themselves
- durable backlog should be read with `messages_read`

## LADA channel notifications

The bridge can also expose LADA-specific channel notifications. This is the
LADA equivalent of a LADA channel adapter: standard MCP tools remain
available, but live inbound messages can also arrive as LADA-specific MCP
notifications.

Flags:

- `--lada-channel-mode off`: standard MCP tools only
- `--lada-channel-mode on`: enable LADA channel notifications
- `--lada-channel-mode auto`: current default; same bridge behavior as `on`

When LADA channel mode is enabled, the server advertises LADA experimental
capabilities and can emit:

- `notifications/lada/channel`
- `notifications/lada/channel/permission`

Current bridge behavior:

- inbound `user` transcript messages are forwarded as
  `notifications/lada/channel`
- LADA permission requests received over MCP are tracked in-memory
- if the linked conversation later sends `yes abcde` or `no abcde`, the bridge
  converts that to `notifications/lada/channel/permission`
- these notifications are live-session only; if the MCP client disconnects,
  there is no push target

This is intentionally client-specific. Generic MCP clients should rely on the
standard polling tools.

## MCP client config

Example stdio client config:

```json
{
  "mcpServers": {
    "lada": {
      "command": "lada",
      "args": [
        "mcp",
        "serve",
        "--url",
        "wss://gateway-host:18789",
        "--token-file",
        "/path/to/gateway.token"
      ]
    }
  }
}
```

For most generic MCP clients, start with the standard tool surface and ignore
LADA mode. Turn LADA mode on only for clients that actually understand the
LADA-specific notification methods.

## Options

`lada mcp serve` supports:

- `--url <url>`: Gateway WebSocket URL
- `--token <token>`: Gateway token
- `--token-file <path>`: read token from file
- `--password <password>`: Gateway password
- `--password-file <path>`: read password from file
- `--lada-channel-mode <auto|on|off>`: LADA notification mode
- `-v`, `--verbose`: verbose logs on stderr

Prefer `--token-file` or `--password-file` over inline secrets when possible.

## Security and trust boundary

The bridge does not invent routing. It only exposes conversations that Gateway
already knows how to route.

That means:

- sender allowlists, pairing, and channel-level trust still belong to the
  underlying LADA channel configuration
- `messages_send` can only reply through an existing stored route
- approval state is live/in-memory only for the current bridge session
- bridge auth should use the same Gateway token or password controls you would
  trust for any other remote Gateway client

If a conversation is missing from `conversations_list`, the usual cause is not
MCP configuration. It is missing or incomplete route metadata in the underlying
Gateway session.

## Testing

LADA ships a deterministic Docker smoke for this bridge:

```bash
pnpm test:docker:mcp-channels
```

That smoke:

- starts a seeded Gateway container
- starts a second container that spawns `lada mcp serve`
- verifies conversation discovery, transcript reads, attachment metadata reads,
  live event queue behavior, and outbound send routing
- validates LADA-style channel and permission notifications over the real
  stdio MCP bridge

This is the fastest way to prove the bridge works without wiring a real
Telegram, Discord, or iMessage account into the test run.

For broader testing context, see [Testing](/help/testing).

## Troubleshooting

### No conversations returned

Usually means the Gateway session is not already routable. Confirm that the
underlying session has stored channel/provider, recipient, and optional
account/thread route metadata.

### `events_poll` or `events_wait` misses older messages

Expected. The live queue starts when the bridge connects. Read older transcript
history with `messages_read`.

### LADA notifications do not show up

Check all of these:

- the client kept the stdio MCP session open
- `--lada-channel-mode` is `on` or `auto`
- the client actually understands the LADA-specific notification methods
- the inbound message happened after the bridge connected

### Approvals are missing

`permissions_list_open` only shows approval requests observed while the bridge
was connected. It is not a durable approval history API.

## LADA as an MCP client registry

This is the `lada mcp list`, `show`, `set`, and `unset` path.

These commands do not expose LADA over MCP. They manage LADA-owned MCP
server definitions under `mcp.servers` in LADA config.

Those saved definitions are for runtimes that LADA launches or configures
later, such as embedded Pi and other runtime adapters. LADA stores the
definitions centrally so those runtimes do not need to keep their own duplicate
MCP server lists.

Important behavior:

- these commands only read or write LADA config
- they do not connect to the target MCP server
- they do not validate whether the command, URL, or remote transport is
  reachable right now
- runtime adapters decide which transport shapes they actually support at
  execution time

## Saved MCP server definitions

LADA also stores a lightweight MCP server registry in config for surfaces
that want LADA-managed MCP definitions.

Commands:

- `lada mcp list`
- `lada mcp show [name]`
- `lada mcp set <name> <json>`
- `lada mcp unset <name>`

Notes:

- `list` sorts server names.
- `show` without a name prints the full configured MCP server object.
- `set` expects one JSON object value on the command line.
- `unset` fails if the named server does not exist.

Examples:

```bash
lada mcp list
lada mcp show context7 --json
lada mcp set context7 '{"command":"uvx","args":["context7-mcp"]}'
lada mcp set docs '{"url":"https://mcp.example.com"}'
lada mcp unset context7
```

Example config shape:

```json
{
  "mcp": {
    "servers": {
      "context7": {
        "command": "uvx",
        "args": ["context7-mcp"]
      },
      "docs": {
        "url": "https://mcp.example.com"
      }
    }
  }
}
```

### Stdio transport

Launches a local child process and communicates over stdin/stdout.

| Field                      | Description                       |
| -------------------------- | --------------------------------- |
| `command`                  | Executable to spawn (required)    |
| `args`                     | Array of command-line arguments   |
| `env`                      | Extra environment variables       |
| `cwd` / `workingDirectory` | Working directory for the process |

### SSE / HTTP transport

Connects to a remote MCP server over HTTP Server-Sent Events.

| Field                 | Description                                                      |
| --------------------- | ---------------------------------------------------------------- |
| `url`                 | HTTP or HTTPS URL of the remote server (required)                |
| `headers`             | Optional key-value map of HTTP headers (for example auth tokens) |
| `connectionTimeoutMs` | Per-server connection timeout in ms (optional)                   |

Example:

```json
{
  "mcp": {
    "servers": {
      "remote-tools": {
        "url": "https://mcp.example.com",
        "headers": {
          "Authorization": "Bearer <token>"
        }
      }
    }
  }
}
```

Sensitive values in `url` (userinfo) and `headers` are redacted in logs and
status output.

### Streamable HTTP transport

`streamable-http` is an additional transport option alongside `sse` and `stdio`. It uses HTTP streaming for bidirectional communication with remote MCP servers.

| Field                 | Description                                                                            |
| --------------------- | -------------------------------------------------------------------------------------- |
| `url`                 | HTTP or HTTPS URL of the remote server (required)                                      |
| `transport`           | Set to `"streamable-http"` to select this transport; when omitted, LADA uses `sse` |
| `headers`             | Optional key-value map of HTTP headers (for example auth tokens)                       |
| `connectionTimeoutMs` | Per-server connection timeout in ms (optional)                                         |

Example:

```json
{
  "mcp": {
    "servers": {
      "streaming-tools": {
        "url": "https://mcp.example.com/stream",
        "transport": "streamable-http",
        "connectionTimeoutMs": 10000,
        "headers": {
          "Authorization": "Bearer <token>"
        }
      }
    }
  }
}
```

These commands manage saved config only. They do not start the channel bridge,
open a live MCP client session, or prove the target server is reachable.

## Current limits

This page documents the bridge as shipped today.

Current limits:

- conversation discovery depends on existing Gateway session route metadata
- no generic push protocol beyond the LADA-specific adapter
- no message edit or react tools yet
- HTTP/SSE/streamable-http transport connects to a single remote server; no multiplexed upstream yet
- `permissions_list_open` only includes approvals observed while the bridge is
  connected

