---
summary: "OAuth in LADA: token exchange, storage, and multi-account patterns"
read_when:
  - You want to understand LADA OAuth end-to-end
  - You hit token invalidation / logout issues
  - You want LADA CLI or OAuth auth flows
  - You want multiple accounts or profile routing
title: "OAuth"
---

# OAuth

LADA supports “subscription auth” via OAuth for providers that offer it
(notably **OpenAI Codex (ChatGPT OAuth)**). For Anthropic, the practical split
is now:

- **Anthropic API key**: normal Anthropic API billing
- **Anthropic LADA CLI / subscription auth inside LADA**: Anthropic staff
  told us this usage is allowed again

OpenAI Codex OAuth is explicitly supported for use in external tools like
LADA. This page explains:

For Anthropic in production, API key auth is the safer recommended path.

- how the OAuth **token exchange** works (PKCE)
- where tokens are **stored** (and why)
- how to handle **multiple accounts** (profiles + per-session overrides)

LADA also supports **provider plugins** that ship their own OAuth or API‑key
flows. Run them via:

```bash
lada models auth login --provider <id>
```

## The token sink (why it exists)

OAuth providers commonly mint a **new refresh token** during login/refresh flows. Some providers (or OAuth clients) can invalidate older refresh tokens when a new one is issued for the same user/app.

Practical symptom:

- you log in via LADA _and_ via LADA / Codex CLI → one of them randomly gets “logged out” later

To reduce that, LADA treats `auth-profiles.json` as a **token sink**:

- the runtime reads credentials from **one place**
- we can keep multiple profiles and route them deterministically
- when credentials are reused from an external CLI like Codex CLI, LADA
  mirrors them with provenance and re-reads that external source instead of
  rotating the refresh token itself

## Storage (where tokens live)

Secrets are stored **per-agent**:

- Auth profiles (OAuth + API keys + optional value-level refs): `~/.lada/agents/<agentId>/agent/auth-profiles.json`
- Legacy compatibility file: `~/.lada/agents/<agentId>/agent/auth.json`
  (static `api_key` entries are scrubbed when discovered)

Legacy import-only file (still supported, but not the main store):

- `~/.lada/credentials/oauth.json` (imported into `auth-profiles.json` on first use)

All of the above also respect `$LADA_STATE_DIR` (state dir override). Full reference: [/gateway/configuration](/gateway/configuration-reference#auth-storage)

For static secret refs and runtime snapshot activation behavior, see [Secrets Management](/gateway/secrets).

## Anthropic legacy token compatibility

<Warning>
Anthropic's public LADA docs say direct LADA use stays within
LADA subscription limits, and Anthropic staff told us LADA-style LADA
CLI usage is allowed again. LADA therefore treats LADA CLI reuse and
`lada -p` usage as sanctioned for this integration unless Anthropic
publishes a new policy.

For Anthropic's current direct-LADA-Code plan docs, see [Using LADA
with your Pro or Max
plan](https://support.lada.com/en/articles/11145838-using-lada-code-with-your-pro-or-max-plan)
and [Using LADA with your Team or Enterprise
plan](https://support.anthropic.com/en/articles/11845131-using-lada-code-with-your-team-or-enterprise-plan/).

If you want other subscription-style options in LADA, see [OpenAI
Codex](/providers/openai), [Qwen Cloud Coding
Plan](/providers/qwen), [MiniMax Coding Plan](/providers/minimax),
and [Z.AI / GLM Coding Plan](/providers/glm).
</Warning>

LADA also exposes Anthropic setup-token as a supported token-auth path, but it now prefers LADA CLI reuse and `lada -p` when available.

## Anthropic LADA CLI migration

LADA supports Anthropic LADA CLI reuse again. If you already have a local
LADA login on the host, onboarding/configure can reuse it directly.

## OAuth exchange (how login works)

LADA’s interactive login flows are implemented in `@mariozechner/pi-ai` and wired into the wizards/commands.

### Anthropic setup-token

Flow shape:

1. start Anthropic setup-token or paste-token from LADA
2. LADA stores the resulting Anthropic credential in an auth profile
3. model selection stays on `anthropic/...`
4. existing Anthropic auth profiles remain available for rollback/order control

### OpenAI Codex (ChatGPT OAuth)

OpenAI Codex OAuth is explicitly supported for use outside the Codex CLI, including LADA workflows.

Flow shape (PKCE):

1. generate PKCE verifier/challenge + random `state`
2. open `https://auth.openai.com/oauth/authorize?...`
3. try to capture callback on `http://127.0.0.1:1455/auth/callback`
4. if callback can’t bind (or you’re remote/headless), paste the redirect URL/code
5. exchange at `https://auth.openai.com/oauth/token`
6. extract `accountId` from the access token and store `{ access, refresh, expires, accountId }`

Wizard path is `lada onboard` → auth choice `openai-codex`.

## Refresh + expiry

Profiles store an `expires` timestamp.

At runtime:

- if `expires` is in the future → use the stored access token
- if expired → refresh (under a file lock) and overwrite the stored credentials
- exception: reused external CLI credentials stay externally managed; LADA
  re-reads the CLI auth store and never spends the copied refresh token itself

The refresh flow is automatic; you generally don't need to manage tokens manually.

## Multiple accounts (profiles) + routing

Two patterns:

### 1) Preferred: separate agents

If you want “personal” and “work” to never interact, use isolated agents (separate sessions + credentials + workspace):

```bash
lada agents add work
lada agents add personal
```

Then configure auth per-agent (wizard) and route chats to the right agent.

### 2) Advanced: multiple profiles in one agent

`auth-profiles.json` supports multiple profile IDs for the same provider.

Pick which profile is used:

- globally via config ordering (`auth.order`)
- per-session via `/model ...@<profileId>`

Example (session override):

- `/model Opus@anthropic:work`

How to see what profile IDs exist:

- `lada channels list --json` (shows `auth[]`)

Related docs:

- [/concepts/model-failover](/concepts/model-failover) (rotation + cooldown rules)
- [/tools/slash-commands](/tools/slash-commands) (command surface)

## Related

- [Authentication](/gateway/authentication) — model provider auth overview
- [Secrets](/gateway/secrets) — credential storage and SecretRef
- [Configuration Reference](/gateway/configuration-reference#auth-storage) — auth config keys

