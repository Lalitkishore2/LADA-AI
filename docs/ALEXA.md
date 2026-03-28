# LADA + Alexa / Echo Dot Integration Guide

LADA supports hybrid voice mode with Amazon Echo Dot, automatically switching between Echo Dot and computer mic/speaker based on availability.

## Prerequisites

- Amazon Echo Dot (any generation)
- Amazon Developer Account (free)
- LADA running on your local network
- ngrok or Tailscale Funnel for public endpoint (Alexa requires HTTPS)

## Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Echo Dot      │ ───▶ │  Alexa Cloud    │ ───▶ │ LADA Skill API  │
│   (Mic/Speaker) │      │  (ASR + TTS)    │      │ (Flask + ngrok) │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                                                  │
        │                                                  ▼
        │                                         ┌─────────────────┐
        └─────────────────────────────────────────│  LADA Core      │
           (Optional: direct audio via WiFi)      │  (Processing)   │
                                                  └─────────────────┘
```

## Setup Steps

### 1. Create Alexa Skill

1. Go to [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
2. Click **Create Skill**
3. Settings:
   - Name: `LADA Assistant`
   - Model: **Custom**
   - Backend: **Provision your own**
   - Template: **Start from scratch**

### 2. Configure Skill Interaction Model

In the JSON Editor, paste:

```json
{
  "interactionModel": {
    "languageModel": {
      "invocationName": "lada",
      "intents": [
        {
          "name": "CommandIntent",
          "slots": [
            {
              "name": "query",
              "type": "AMAZON.SearchQuery"
            }
          ],
          "samples": [
            "{query}",
            "ask {query}",
            "tell me {query}",
            "do {query}",
            "please {query}"
          ]
        },
        {
          "name": "AMAZON.HelpIntent",
          "samples": []
        },
        {
          "name": "AMAZON.StopIntent",
          "samples": []
        },
        {
          "name": "AMAZON.CancelIntent",
          "samples": []
        }
      ]
    }
  }
}
```

Click **Save Model** then **Build Model**.

### 3. Start ngrok Tunnel

```bash
# Install ngrok if needed
# https://ngrok.com/download

# Start tunnel (LADA Flask runs on port 5001)
ngrok http 5001
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 4. Configure Alexa Endpoint

1. Go to **Endpoint** in Alexa Developer Console
2. Select **HTTPS**
3. Default Region: `https://abc123.ngrok.io/alexa`
4. SSL Certificate: **My development endpoint is a sub-domain of a domain that has a wildcard certificate**
5. **Save Endpoints**

### 5. Configure LADA Environment

Add to your `.env` file:

```bash
# Alexa Integration
ALEXA_SKILL_ID=amzn1.ask.skill.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ALEXA_SKILL_SECRET=your_secret_here  # Optional, for request verification

# Echo Dot IP (for direct audio - optional)
ECHO_DOT_IP=192.168.1.100

# Voice Mode
LADA_VOICE_MODE=hybrid  # auto | computer | echo_dot | hybrid
```

### 6. Start LADA Alexa Server

```bash
# From LADA root directory
python -c "from integrations.alexa_server import AlexaFlaskServer; AlexaFlaskServer().run()"
```

Or integrate into main LADA startup (happens automatically if `ALEXA_SKILL_ID` is set).

## Usage

### Via Echo Dot

1. Say: **"Alexa, open LADA"**
2. Then say your command: **"What's the weather today?"**
3. Or use one-shot: **"Alexa, ask LADA what time is it"**

### Hybrid Mode Behavior

| Echo Dot Status | LADA Behavior |
|-----------------|---------------|
| Connected & Responding | Routes voice through Echo Dot |
| Disconnected/Unresponsive | Falls back to computer mic/speaker |
| Reconnected | Auto-switches back to Echo Dot |

LADA checks Echo Dot connectivity every 10 seconds.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALEXA_SKILL_ID` | - | Your Alexa Skill ID (required) |
| `ALEXA_SKILL_SECRET` | - | Skill secret for request verification |
| `ECHO_DOT_IP` | - | Echo Dot IP for ping checks |
| `ALEXA_PORT` | 5001 | Flask server port |
| `LADA_VOICE_MODE` | auto | `auto`, `computer`, `echo_dot`, `hybrid` |
| `ECHO_DOT_CHECK_INTERVAL` | 10 | Seconds between connectivity checks |

## Troubleshooting

### "I can't reach LADA"

- Verify ngrok is running and URL matches Alexa endpoint
- Check LADA Flask server is running on correct port
- Ensure firewall allows incoming connections

### Echo Dot not detected

- Verify `ECHO_DOT_IP` is correct (check your router for Echo Dot IP)
- Ensure Echo Dot is on same network as LADA
- Try pinging: `ping 192.168.1.100`

### Slow response times

- ngrok free tier has latency; consider ngrok Pro or Tailscale Funnel
- Optimize LADA response generation
- Use faster local LLM models

### Request verification fails

- Ensure `ALEXA_SKILL_ID` matches your skill exactly
- Check system clock is synchronized (NTP)
- Verify request hasn't expired (300s tolerance)

## Using Tailscale Funnel (Recommended)

For permanent, free HTTPS endpoint:

```bash
# Install Tailscale
# https://tailscale.com/download

# Enable Funnel
tailscale funnel 5001

# Your URL will be: https://your-machine.your-tailnet.ts.net
```

Set in `.env`:
```bash
LADA_TAILSCALE_FUNNEL=true
```

## Security Notes

- Always use HTTPS for Alexa endpoints
- Verify request signatures in production
- Keep `ALEXA_SKILL_SECRET` secure
- Don't expose LADA port directly to internet without Alexa validation

## Related Files

- `integrations/alexa_server.py` - Flask server handling Alexa requests
- `integrations/alexa_hybrid.py` - Hybrid voice switcher
- `voice_tamil_free.py` - Main voice controller
- `docs/VOICE_COMMANDS.md` - Voice command reference
