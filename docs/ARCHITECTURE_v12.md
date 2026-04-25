# LADA v12.0 System Architecture

The v12.0 rewrite transitioned LADA from a monolithic desktop utility to an asynchronous, multi-agent AI system with distinct, independent subsystems. 

```mermaid
graph TD
    subgraph UI[Desktop Interface]
        App[lada_desktop_app.py]
        Settings[Settings Dialog]
        Orch[LADAOrchestrator]
    end

    subgraph Agents[AI Agents]
        Router[HybridAIRouter]
        Screen[ScreenAgent]
        Comet[CometBrowserAgent]
    end

    subgraph Memory[State & Memory]
        Mem0[(Mem0 Semantic DB)]
        CrossTab[CrossTabSynthesizer]
        Vector[(FAISS Vector Store)]
    end

    subgraph Security[Safety & Compliance]
        DLP[DLP Filter]
        YOLO[YOLO Permission Classifier]
        MCPInterceptor[MCP Interceptor]
    end

    subgraph Voice[Voice Pipeline]
        OWW[OpenWakeWord]
        STT[faster-whisper]
        TTS[edge-tts]
    end

    %% Wiring UI to Core
    App --> Orch
    Orch --> Router
    Orch --> Settings

    %% Agent Flow
    Router --> Screen
    Router --> Comet
    Screen --> Router
    Comet --> Router

    %% Safety Intercepts
    Screen -- OCR Output --> DLP
    DLP -- Redacted Text --> Router
    Router -- Tool Calls --> MCPInterceptor
    Router -- Commands --> YOLO

    %% Memory & State
    Comet --> CrossTab
    CrossTab --> Router
    Router --> Mem0
    Router --> Vector

    %% Voice I/O
    OWW --> STT
    STT --> Router
    Router --> TTS
```

## Key Subsystems

### 1. CometBrowserAgent + CrossTabSynthesizer
Uses the Playwright async API to manage multiple tabs concurrently. The `CrossTabSynthesizer` captures semantic snapshots of each tab to provide the AI with multi-page reasoning capabilities.

### 2. Mem0 Semantic Memory
Injected into the `HybridAIRouter`, it stores conversations and preferences over time, supplementing the existing FAISS RAG store.

### 3. Voice Pipeline Router
A sub-second latency voice I/O pipeline using `openwakeword` for wake-word detection, `faster-whisper` for STT, and `edge-tts` for high-quality text-to-speech.

### 4. Safety Guardrails (DLP, YOLO, MCP)
Three distinct security layers:
- **DLP**: Prevents sensitive data from reaching the cloud.
- **YOLO**: Classifies commands into SAFE, CONFIRM, and DENY tiers.
- **MCP Interceptor**: Rate-limits and audits external tool calls.
