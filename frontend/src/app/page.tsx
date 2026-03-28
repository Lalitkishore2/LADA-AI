'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { WSClient } from '@/lib/ws-client';
import ChatMessage from '@/components/ChatMessage';
import ProviderStatus from '@/components/ProviderStatus';
import AnimatedAIInput, { ModelInfo as AIModelInfo } from '@/components/ui/animated-ai-input';
import { cn } from '@/lib/utils';
import { Sparkles, Zap, Brain, Code2, MessageSquare } from 'lucide-react';
import type {
  ServerMessage,
  ModelInfo,
  Source,
} from '@/types/ws-protocol';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  sources?: Source[];
  streaming?: boolean;
}

interface Provider {
  name: string;
  status: string;
  available: boolean;
}

// ---------------------------------------------------------------------------
// Welcome Screen Component
// ---------------------------------------------------------------------------

function WelcomeScreen() {
  const capabilities = [
    { icon: MessageSquare, title: 'Chat', desc: 'Natural conversations with any AI model' },
    { icon: Zap, title: 'Commands', desc: 'Control your system with voice or text' },
    { icon: Brain, title: 'Research', desc: 'Deep web research with citations' },
    { icon: Code2, title: 'Code', desc: 'Write, debug, and explain code' },
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <div className="mb-8 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 mb-4">
          <Sparkles className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-zinc-100 mb-2">
          Welcome to LADA
        </h1>
        <p className="text-zinc-400 max-w-md">
          Your local AI desktop assistant. Ask questions, run commands, browse the web, or write code.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 max-w-lg w-full">
        {capabilities.map((cap, i) => (
          <div
            key={i}
            className={cn(
              "flex items-start gap-3 p-4 rounded-xl",
              "bg-zinc-900/50 border border-zinc-800/50",
              "hover:bg-zinc-800/50 hover:border-zinc-700/50 transition-colors"
            )}
          >
            <div className="p-2 rounded-lg bg-zinc-800">
              <cap.icon className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-sm font-medium text-zinc-200">{cap.title}</h3>
              <p className="text-xs text-zinc-500">{cap.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 text-center">
        <p className="text-xs text-zinc-600">
          Type a message below to get started
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function ChatPage() {
  // ---- State --------------------------------------------------------------

  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedModel, setSelectedModel] = useState('auto');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [sending, setSending] = useState(false);

  // Refs for mutable state accessible inside callbacks
  const wsRef = useRef<WSClient | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingIdRef = useRef<string | null>(null);

  // ---- Auto-scroll --------------------------------------------------------

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // ---- WebSocket setup ----------------------------------------------------

  useEffect(() => {
    const client = new WSClient();
    wsRef.current = client;

    client.onConnect(() => {
      setConnected(true);
      setSessionId(client.sessionId ?? undefined);
    });

    client.onDisconnect(() => {
      setConnected(false);
    });

    client.onMessage((msg: ServerMessage) => {
      switch (msg.type) {
        // -- Connection handshake -------------------------------------------
        case 'system.connected':
          setSessionId(msg.data.session_id);
          break;

        // -- Model list -----------------------------------------------------
        case 'system.models':
          setModels(msg.data.models);
          break;

        // -- System status (extract providers) ------------------------------
        case 'system.status': {
          const raw = msg.data as Record<string, unknown>;
          const providersRaw = raw.providers as
            | Record<string, Record<string, unknown>>
            | undefined;
          if (providersRaw && typeof providersRaw === 'object') {
            const list: Provider[] = Object.entries(providersRaw).map(
              ([key, val]) => ({
                name: (val.name as string) ?? key,
                status: (val.status as string) ?? 'unknown',
                available: Boolean(val.available ?? val.configured ?? false),
              }),
            );
            setProviders(list);
          }
          break;
        }

        // -- Streaming: start -----------------------------------------------
        case 'chat.start':
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '', streaming: true },
          ]);
          break;

        // -- Streaming: chunk -----------------------------------------------
        case 'chat.chunk':
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant' && last.streaming) {
              updated[updated.length - 1] = {
                ...last,
                content: last.content + (msg.data?.chunk ?? ''),
              };
            }
            return updated;
          });
          break;

        // -- Streaming: sources ---------------------------------------------
        case 'chat.sources':
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                sources: msg.data?.sources ?? [],
              };
            }
            return updated;
          });
          break;

        // -- Streaming: done ------------------------------------------------
        case 'chat.done':
          setSending(false);
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                streaming: false,
                model: (msg.data as Record<string, unknown>)?.model as string | undefined,
              };
            }
            return updated;
          });
          break;

        // -- Non-streaming response -----------------------------------------
        case 'chat.response':
          setSending(false);
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: msg.data.content,
              model: msg.data.model,
              streaming: false,
            },
          ]);
          break;

        // -- Error ----------------------------------------------------------
        case 'error':
          setSending(false);
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: `Error: ${msg.data?.message ?? 'Unknown error'}`,
              streaming: false,
            },
          ]);
          break;

        default:
          break;
      }
    });

    client.connect();

    return () => {
      client.disconnect();
    };
  }, []);

  // ---- Send handler -------------------------------------------------------

  const handleSend = useCallback((text: string) => {
    if (!text || !wsRef.current || sending) return;

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setSending(true);

    // Send via WS
    const model = selectedModel === 'auto' ? undefined : selectedModel;
    const id = wsRef.current.sendChat(text, true, model);
    pendingIdRef.current = id;
  }, [selectedModel, sending]);

  const handleStop = useCallback(() => {
    // Stop streaming - could send a cancel message to the server
    setSending(false);
  }, []);

  // Transform models for AnimatedAIInput
  const aiModels: AIModelInfo[] = models.map((m) => ({
    id: m.id,
    name: m.name || m.id,
    provider: m.provider || 'Unknown',
    tier: m.tier,
  }));

  // ---- Render -------------------------------------------------------------

  return (
    <div className="flex flex-col h-screen bg-zinc-950">
      {/* Status bar */}
      <div className="flex items-center justify-end px-4 py-2 border-b border-zinc-800/50">
        <ProviderStatus
          connected={connected}
          sessionId={sessionId}
          providers={providers}
        />
      </div>

      {/* Message area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeScreen />
        ) : (
          <div className="max-w-3xl mx-auto py-6 px-4">
            <div className="space-y-6">
              {messages.map((msg, idx) => (
                <ChatMessage
                  key={idx}
                  role={msg.role}
                  content={msg.content}
                  model={msg.model}
                  sources={msg.sources as { url: string; title: string; domain: string }[]}
                  streaming={msg.streaming}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-zinc-800/50 bg-zinc-950 py-4">
        <AnimatedAIInput
          models={aiModels}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={sending}
          disabled={!connected}
          placeholder={connected ? "Ask LADA anything..." : "Connecting..."}
        />
      </div>
    </div>
  );
}
