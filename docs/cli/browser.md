---
summary: "CLI reference for `lada browser` (lifecycle, profiles, tabs, actions, state, and debugging)"
read_when:
  - You use `lada browser` and want examples for common tasks
  - You want to control a browser running on another machine via a node host
  - You want to attach to your local signed-in Chrome via Chrome MCP
title: "browser"
---

# `lada browser`

Manage LADA's browser control surface and run browser actions (lifecycle, profiles, tabs, snapshots, screenshots, navigation, input, state emulation, and debugging).

Related:

- Browser tool + API: [Browser tool](/tools/browser)

## Common flags

- `--url <gatewayWsUrl>`: Gateway WebSocket URL (defaults to config).
- `--token <token>`: Gateway token (if required).
- `--timeout <ms>`: request timeout (ms).
- `--expect-final`: wait for a final Gateway response.
- `--browser-profile <name>`: choose a browser profile (default from config).
- `--json`: machine-readable output (where supported).

## Quick start (local)

```bash
lada browser profiles
lada browser --browser-profile lada start
lada browser --browser-profile lada open https://example.com
lada browser --browser-profile lada snapshot
```

## Lifecycle

```bash
lada browser status
lada browser start
lada browser stop
lada browser --browser-profile lada reset-profile
```

Notes:

- For `attachOnly` and remote CDP profiles, `lada browser stop` closes the
  active control session and clears temporary emulation overrides even when
  LADA did not launch the browser process itself.
- For local managed profiles, `lada browser stop` stops the spawned browser
  process.

## If the command is missing

If `lada browser` is an unknown command, check `plugins.allow` in
`~/.lada/lada.json`.

When `plugins.allow` is present, the bundled browser plugin must be listed
explicitly:

```json5
{
  plugins: {
    allow: ["telegram", "browser"],
  },
}
```

`browser.enabled=true` does not restore the CLI subcommand when the plugin
allowlist excludes `browser`.

Related: [Browser tool](/tools/browser#missing-browser-command-or-tool)

## Profiles

Profiles are named browser routing configs. In practice:

- `lada`: launches or attaches to a dedicated LADA-managed Chrome instance (isolated user data dir).
- `user`: controls your existing signed-in Chrome session via Chrome DevTools MCP.
- custom CDP profiles: point at a local or remote CDP endpoint.

```bash
lada browser profiles
lada browser create-profile --name work --color "#FF5A36"
lada browser create-profile --name chrome-live --driver existing-session
lada browser create-profile --name remote --cdp-url https://browser-host.example.com
lada browser delete-profile --name work
```

Use a specific profile:

```bash
lada browser --browser-profile work tabs
```

## Tabs

```bash
lada browser tabs
lada browser tab new
lada browser tab select 2
lada browser tab close 2
lada browser open https://docs.lada.ai
lada browser focus <targetId>
lada browser close <targetId>
```

## Snapshot / screenshot / actions

Snapshot:

```bash
lada browser snapshot
```

Screenshot:

```bash
lada browser screenshot
lada browser screenshot --full-page
lada browser screenshot --ref e12
```

Notes:

- `--full-page` is for page captures only; it cannot be combined with `--ref`
  or `--element`.
- `existing-session` / `user` profiles support page screenshots and `--ref`
  screenshots from snapshot output, but not CSS `--element` screenshots.

Navigate/click/type (ref-based UI automation):

```bash
lada browser navigate https://example.com
lada browser click <ref>
lada browser type <ref> "hello"
lada browser press Enter
lada browser hover <ref>
lada browser scrollintoview <ref>
lada browser drag <startRef> <endRef>
lada browser select <ref> OptionA OptionB
lada browser fill --fields '[{"ref":"1","value":"Ada"}]'
lada browser wait --text "Done"
lada browser evaluate --fn '(el) => el.textContent' --ref <ref>
```

File + dialog helpers:

```bash
lada browser upload /tmp/lada/uploads/file.pdf --ref <ref>
lada browser waitfordownload
lada browser download <ref> report.pdf
lada browser dialog --accept
```

## State and storage

Viewport + emulation:

```bash
lada browser resize 1280 720
lada browser set viewport 1280 720
lada browser set offline on
lada browser set media dark
lada browser set timezone Europe/London
lada browser set locale en-GB
lada browser set geo 51.5074 -0.1278 --accuracy 25
lada browser set device "iPhone 14"
lada browser set headers '{"x-test":"1"}'
lada browser set credentials myuser mypass
```

Cookies + storage:

```bash
lada browser cookies
lada browser cookies set session abc123 --url https://example.com
lada browser cookies clear
lada browser storage local get
lada browser storage local set token abc123
lada browser storage session clear
```

## Debugging

```bash
lada browser console --level error
lada browser pdf
lada browser responsebody "**/api"
lada browser highlight <ref>
lada browser errors --clear
lada browser requests --filter api
lada browser trace start
lada browser trace stop --out trace.zip
```

## Existing Chrome via MCP

Use the built-in `user` profile, or create your own `existing-session` profile:

```bash
lada browser --browser-profile user tabs
lada browser create-profile --name chrome-live --driver existing-session
lada browser create-profile --name brave-live --driver existing-session --user-data-dir "~/Library/Application Support/BraveSoftware/Brave-Browser"
lada browser --browser-profile chrome-live tabs
```

This path is host-only. For Docker, headless servers, Browserless, or other remote setups, use a CDP profile instead.

Current existing-session limits:

- snapshot-driven actions use refs, not CSS selectors
- `click` is left-click only
- `type` does not support `slowly=true`
- `press` does not support `delayMs`
- `hover`, `scrollintoview`, `drag`, `select`, `fill`, and `evaluate` reject
  per-call timeout overrides
- `select` supports one value only
- `wait --load networkidle` is not supported
- file uploads require `--ref` / `--input-ref`, do not support CSS
  `--element`, and currently support one file at a time
- dialog hooks do not support `--timeout`
- screenshots support page captures and `--ref`, but not CSS `--element`
- `responsebody`, download interception, PDF export, and batch actions still
  require a managed browser or raw CDP profile

## Remote browser control (node host proxy)

If the Gateway runs on a different machine than the browser, run a **node host** on the machine that has Chrome/Brave/Edge/Chromium. The Gateway will proxy browser actions to that node (no separate browser control server required).

Use `gateway.nodes.browser.mode` to control auto-routing and `gateway.nodes.browser.node` to pin a specific node if multiple are connected.

Security + remote setup: [Browser tool](/tools/browser), [Remote access](/gateway/remote), [Tailscale](/gateway/tailscale), [Security](/gateway/security)

