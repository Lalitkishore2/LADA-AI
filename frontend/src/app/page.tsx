'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { WSClient, generateId } from '@/lib/ws-client';
import ChatMessage from '@/components/ChatMessage';
import ModelSelector from '@/components/ModelSelector';
import ProviderStatus from '@/components/ProviderStatus';
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
// Component
// ---------------------------------------------------------------------------

export default function ChatPage() {
  // ---- State --------------------------------------------------------------

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState('auto');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [sending, setSending] = useState(false);

  // Refs for mutable state accessible inside callbacks
  const wsRef = useRef<WSClient | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || !wsRef.current || sending) return;

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setSending(true);

    // Send via WS
    const model = selectedModel === 'auto' ? undefined : selectedModel;
    const id = wsRef.current.sendChat(text, true, model);
    pendingIdRef.current = id;

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, selectedModel, sending]);

  // ---- Keyboard handler ---------------------------------------------------

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // ---- Auto-resize textarea ----------------------------------------------

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value);
      const el = e.target;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    },
    [],
  );

  // ---- Render -------------------------------------------------------------

  return (
    <div className="flex flex-col flex-1 h-[calc(100vh-3.5rem)]">
      {/* Top bar: model selector + connection status */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <ModelSelector
          models={models}
          selectedModel={selectedModel}
          onSelect={setSelectedModel}
        />
        <ProviderStatus
          connected={connected}
          sessionId={sessionId}
          providers={providers}
        />
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
          /* Empty state */
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
                LADA
              </h2>
              <p className="text-[var(--text-secondary)] text-sm">
                Language Agnostic Digital Assistant. Type a message below to
                start a conversation with any of the configured AI models.
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-1">
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
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-end gap-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Shift+Enter for newline)"
            rows={1}
            className="flex-1 resize-none bg-[var(--bg-tertiary)] text-[var(--text-primary)] placeholder-[var(--text-secondary)] border border-[var(--border)] rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending || !connected}
            className="flex-shrink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {sending ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
