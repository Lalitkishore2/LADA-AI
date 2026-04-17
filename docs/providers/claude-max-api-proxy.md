---
summary: "Community proxy to expose LADA subscription credentials as an OpenAI-compatible endpoint"
read_when:
  - You want to use LADA Max subscription with OpenAI-compatible tools
  - You want a local API server that wraps LADA CLI
  - You want to evaluate subscription-based vs API-key-based Anthropic access
title: "LADA Max API Proxy"
---

# LADA Max API Proxy

**lada-max-api-proxy** is a community tool that exposes your LADA Max/Pro subscription as an OpenAI-compatible API endpoint. This allows you to use your subscription with any tool that supports the OpenAI API format.

<Warning>
This path is technical compatibility only. Anthropic has blocked some subscription
usage outside LADA in the past. You must decide for yourself whether to use
it and verify Anthropic's current terms before relying on it.
</Warning>

## Why Use This?

| Approach                | Cost                                                | Best For                                   |
| ----------------------- | --------------------------------------------------- | ------------------------------------------ |
| Anthropic API           | Pay per token (~$15/M input, $75/M output for Opus) | Production apps, high volume               |
| LADA Max subscription | $200/month flat                                     | Personal use, development, unlimited usage |

If you have a LADA Max subscription and want to use it with OpenAI-compatible tools, this proxy may reduce cost for some workflows. API keys remain the clearer policy path for production use.

## How It Works

```
Your App → lada-max-api-proxy → LADA CLI → Anthropic (via subscription)
     (OpenAI format)              (converts format)      (uses your login)
```

The proxy:

1. Accepts OpenAI-format requests at `http://localhost:3456/v1/chat/completions`
2. Converts them to LADA CLI commands
3. Returns responses in OpenAI format (streaming supported)

## Installation

```bash
# Requires Node.js 20+ and LADA CLI
npm install -g lada-max-api-proxy

# Verify LADA CLI is authenticated
lada --version
```

## Usage

### Start the server

```bash
lada-max-api
# Server runs at http://localhost:3456
```

### Test it

```bash
# Health check
curl http://localhost:3456/health

# List models
curl http://localhost:3456/v1/models

# Chat completion
curl http://localhost:3456/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lada-opus-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### With LADA

You can point LADA at the proxy as a custom OpenAI-compatible endpoint:

```json5
{
  env: {
    OPENAI_API_KEY: "not-needed",
    OPENAI_BASE_URL: "http://localhost:3456/v1",
  },
  agents: {
    defaults: {
      model: { primary: "openai/lada-opus-4" },
    },
  },
}
```

This path uses the same proxy-style OpenAI-compatible route as other custom
`/v1` backends:

- native OpenAI-only request shaping does not apply
- no `service_tier`, no Responses `store`, no prompt-cache hints, and no
  OpenAI reasoning-compat payload shaping
- hidden LADA attribution headers (`originator`, `version`, `User-Agent`)
  are not injected on the proxy URL

## Available Models

| Model ID          | Maps To         |
| ----------------- | --------------- |
| `lada-opus-4`   | LADA Opus 4   |
| `lada-sonnet-4` | LADA Sonnet 4 |
| `lada-haiku-4`  | LADA Haiku 4  |

## Auto-Start on macOS

Create a LaunchAgent to run the proxy automatically:

```bash
cat > ~/Library/LaunchAgents/com.lada-max-api.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.lada-max-api</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/node</string>
    <string>/usr/local/lib/node_modules/lada-max-api-proxy/dist/server/standalone.js</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:~/.local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lada-max-api.plist
```

## Links

- **npm:** [https://www.npmjs.com/package/lada-max-api-proxy](https://www.npmjs.com/package/lada-max-api-proxy)
- **GitHub:** [https://github.com/atalovesyou/lada-max-api-proxy](https://github.com/atalovesyou/lada-max-api-proxy)
- **Issues:** [https://github.com/atalovesyou/lada-max-api-proxy/issues](https://github.com/atalovesyou/lada-max-api-proxy/issues)

## Notes

- This is a **community tool**, not officially supported by Anthropic or LADA
- Requires an active LADA Max/Pro subscription with LADA CLI authenticated
- The proxy runs locally and does not send data to any third-party servers
- Streaming responses are fully supported

## See Also

- [Anthropic provider](/providers/anthropic) - Native LADA integration with LADA CLI or API keys
- [OpenAI provider](/providers/openai) - For OpenAI/Codex subscriptions

