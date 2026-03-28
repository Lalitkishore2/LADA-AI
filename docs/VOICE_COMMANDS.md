# LADA Voice Commands Guide

LADA supports always-on voice control with wake word activation.

## Wake Word System

### Activation
- Say **"LADA WAKEUP"** to start listening
- LADA will confirm: *"I'm listening"*
- Give commands naturally without repeating the wake word

### Deactivation
- Say **"LADA TURN OFF"** to stop listening
- LADA will confirm: *"Going to sleep"*

## Voice Commands

### System Control
| Command | Action |
|---------|--------|
| "Set volume to 50" | Adjust system volume |
| "Mute" / "Unmute" | Toggle audio |
| "Increase brightness" | Screen brightness up |
| "Take a screenshot" | Capture screen |
| "Lock computer" | Lock workstation |

### Applications
| Command | Action |
|---------|--------|
| "Open Chrome" | Launch browser |
| "Open Spotify" | Launch music |
| "Close Notepad" | Close application |
| "Switch to VS Code" | Focus window |

### Web & Search
| Command | Action |
|---------|--------|
| "Search for Python tutorials" | Web search |
| "Research AI news" | Deep research |
| "What's the weather" | Weather info |
| "Read the news" | News summary |

### Productivity
| Command | Action |
|---------|--------|
| "Set timer for 5 minutes" | Timer |
| "Set alarm for 7 AM" | Alarm |
| "Check my calendar" | Calendar events |
| "Send email to John" | Email compose |

### MoltBot Robot (if connected)
| Command | Action |
|---------|--------|
| "Move robot forward" | Drive forward |
| "Turn robot left" | Rotate left |
| "Open claw" | Open gripper |
| "Robot pick up" | Pick sequence |

## Voice Settings

Configure in `.env`:

```env
# Wake phrases (comma-separated)
LADA_WAKE_PHRASES=lada wakeup,hey lada,ok lada

# Continuous listening timeout (seconds)
LADA_CONTINUOUS_TIMEOUT=300

# STT model (auto-selects based on VRAM)
WHISPER_MODEL=large-v3-turbo

# TTS engine
TTS_ENGINE=xtts  # xtts, kokoro, gtts, pyttsx3
```

## Echo Dot Integration

LADA can use your Amazon Echo Dot as mic/speaker:

1. Set `ECHO_DOT_IP` in `.env`
2. LADA auto-switches between Echo and local audio
3. Health check every 10 seconds

```env
ECHO_DOT_IP=192.168.1.50
ECHO_DOT_PORT=8080
LADA_VOICE_MODE=auto  # auto, local, echo
```

## Troubleshooting

### Wake word not detected
- Check microphone permissions
- Verify `WHISPER_MODEL` is loaded
- Try speaking closer to mic

### Voice sounds robotic
- Switch TTS engine: `TTS_ENGINE=xtts`
- Provide voice sample: `XTTS_VOICE_SAMPLE=path/to/sample.wav`

### High latency
- Use lighter model: `WHISPER_MODEL=small`
- Disable GPU: `WHISPER_DEVICE=cpu`
