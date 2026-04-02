'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { WSClient } from '@/lib/ws-client';
import ChatMessage from '@/components/ChatMessage';
import ProviderStatus from '@/components/ProviderStatus';
import AnimatedAIInput, { ModelInfo as AIModelInfo } from '@/components/ui/animated-ai-input';
import { cn } from '@/lib/utils';
import {
  authFetch,
  checkSessionToken,
  clearStoredAuthToken,
  getStoredAuthToken,
  loginSession,
} from '@/lib/lada-api';
import {
  Sparkles,
  Zap,
  Brain,
  Code2,
  MessageSquare,
  FolderOpen,
  History,
  Save,
  RefreshCw,
  Plus,
  Trash2,
  Globe,
  CheckCircle2,
  AlertTriangle,
  Info,
  X,
} from 'lucide-react';
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

interface ConversationSummary {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at?: string;
}

interface WorkspaceNotice {
  id: string;
  kind: 'success' | 'info' | 'error';
  message: string;
}

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };
    return String(payload.detail ?? payload.message ?? fallback);
  } catch {
    return fallback;
  }
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
      <div className="mb-9 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[linear-gradient(145deg,var(--accent),var(--accent-dark))] mb-4 shadow-[0_10px_24px_rgba(16,163,127,.3)]">
          <Sparkles className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-3xl font-semibold text-[var(--text)] mb-2 tracking-tight">
          Welcome to LADA
        </h1>
        <p className="text-[var(--text-dim)] max-w-md leading-relaxed">
          Your local AI desktop assistant. Ask questions, run commands, browse the web, or write code.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 max-w-xl w-full">
        {capabilities.map((cap, i) => (
          <div
            key={i}
            className={cn(
              "flex items-start gap-3 p-4 rounded-xl border",
              "bg-[var(--surface)]/80 border-[var(--border-color)]",
              "hover:bg-[var(--surface-2)]/80 hover:border-[var(--accent)]/45 transition-colors"
            )}
          >
            <div className="p-2 rounded-lg bg-[var(--surface-2)]/70 border border-[var(--border-color)]/70">
              <cap.icon className="w-4 h-4 text-[var(--accent-hover)]" />
            </div>
            <div>
              <h3 className="text-sm font-medium text-[var(--text)]">{cap.title}</h3>
              <p className="text-xs text-[var(--text-dim)]">{cap.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 text-center">
        <p className="text-xs text-[var(--text-faint)]">
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
  const [needsAuth, setNeedsAuth] = useState(false);
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authVersion, setAuthVersion] = useState(0);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [sessions, setSessions] = useState<string[]>([]);
  const [activeSession, setActiveSession] = useState('');
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState('');
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [workspaceError, setWorkspaceError] = useState('');
  const [composerDraft, setComposerDraft] = useState('');
  const [sessionFilter, setSessionFilter] = useState('');
  const [conversationFilter, setConversationFilter] = useState('');
  const [notices, setNotices] = useState<WorkspaceNotice[]>([]);

  // Refs for mutable state accessible inside callbacks
  const wsRef = useRef<WSClient | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingIdRef = useRef<string | null>(null);

  const dismissNotice = useCallback((id: string) => {
    setNotices((prev) => prev.filter((notice) => notice.id !== id));
  }, []);

  const pushNotice = useCallback((kind: WorkspaceNotice['kind'], message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setNotices((prev) => [...prev.slice(-2), { id, kind, message }]);
    window.setTimeout(() => {
      setNotices((prev) => prev.filter((notice) => notice.id !== id));
    }, 2800);
  }, []);

  const filteredSessions = useMemo(() => {
    const query = sessionFilter.trim().toLowerCase();
    if (!query) {
      return sessions;
    }
    return sessions.filter((item) => item.toLowerCase().includes(query));
  }, [sessionFilter, sessions]);

  const filteredConversations = useMemo(() => {
    const query = conversationFilter.trim().toLowerCase();
    if (!query) {
      return conversations;
    }
    return conversations.filter(
      (item) =>
        item.title.toLowerCase().includes(query) ||
        item.id.toLowerCase().includes(query),
    );
  }, [conversationFilter, conversations]);

  // ---- Auto-scroll --------------------------------------------------------

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // ---- Workspace data helpers --------------------------------------------

  const requireReauth = useCallback((message = 'Session expired. Please log in again.') => {
    clearStoredAuthToken();
    setNeedsAuth(true);
    setAuthError(message);
  }, []);

  const toUiMessages = useCallback((rows: Array<Record<string, unknown>>): Message[] => {
    return rows
      .map((row) => {
        const role = row.role === 'user' ? 'user' : 'assistant';
        const content = String(row.content ?? row.message ?? '').trim();
        if (!content) {
          return null;
        }
        return { role, content, streaming: false } as Message;
      })
      .filter((item): item is Message => Boolean(item));
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const response = await authFetch('/sessions');
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not load sessions.'));
      }
      const payload = (await response.json()) as { sessions?: unknown };
      setSessions(Array.isArray(payload.sessions) ? payload.sessions.map((name) => String(name)) : []);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not load sessions.';
      setWorkspaceError(msg);
    }
  }, [requireReauth]);

  const loadConversations = useCallback(async () => {
    try {
      const response = await authFetch('/conversations');
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not load conversations.'));
      }
      const payload = (await response.json()) as { conversations?: unknown };
      const list = Array.isArray(payload.conversations)
        ? (payload.conversations as Array<Record<string, unknown>>).map((item) => ({
            id: String(item.id ?? ''),
            title: String(item.title ?? 'Untitled'),
            message_count: Number(item.message_count ?? 0),
            created_at: String(item.created_at ?? ''),
            updated_at: String(item.updated_at ?? ''),
          }))
        : [];
      setConversations(list.filter((item) => item.id.length > 0));
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not load conversations.';
      setWorkspaceError(msg);
    }
  }, [requireReauth]);

  const refreshWorkspaceData = useCallback(async () => {
    setWorkspaceError('');
    await Promise.all([loadSessions(), loadConversations()]);
  }, [loadConversations, loadSessions]);

  const toggleWebSearch = useCallback(() => {
    setWebSearchEnabled((prev) => {
      const next = !prev;
      pushNotice('info', next ? 'Web search enabled.' : 'Web search disabled.');
      return next;
    });
  }, [pushNotice]);

  const startFreshChat = useCallback(() => {
    setMessages([]);
    setActiveConversationId('');
    setComposerDraft('');
    setWorkspaceError('');
    pushNotice('info', 'Started a fresh chat.');
  }, [pushNotice]);

  const switchSession = useCallback(async (name: string) => {
    const next = name.trim();
    if (!next) {
      setActiveSession('');
      return;
    }

    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await authFetch('/sessions/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: next }),
      });
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not switch session.'));
      }

      const payload = (await response.json()) as { messages?: unknown };
      const nextMessages = Array.isArray(payload.messages)
        ? toUiMessages(payload.messages as Array<Record<string, unknown>>)
        : [];

      setMessages(nextMessages);
      setActiveSession(next);
      setActiveConversationId('');
      setComposerDraft('');
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not switch session.';
      setWorkspaceError(msg);
    } finally {
      setWorkspaceBusy(false);
    }
  }, [requireReauth, toUiMessages]);

  const createSession = useCallback(async () => {
    const suggested = `session-${new Date().toISOString().slice(0, 10)}`;
    const name = window.prompt('Enter a new session name:', suggested)?.trim();
    if (!name) {
      return;
    }

    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await authFetch('/sessions/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not create session.'));
      }

      await loadSessions();
      await switchSession(name);
      pushNotice('success', `Session "${name}" is ready.`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not create session.';
      setWorkspaceError(msg);
    } finally {
      setWorkspaceBusy(false);
    }
  }, [loadSessions, pushNotice, requireReauth, switchSession]);

  const deleteActiveSession = useCallback(async () => {
    if (!activeSession) {
      return;
    }
    const confirmed = window.confirm(`Delete session "${activeSession}"?`);
    if (!confirmed) {
      return;
    }

    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await authFetch(`/sessions/${encodeURIComponent(activeSession)}`, {
        method: 'DELETE',
      });
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not delete session.'));
      }

      setActiveSession('');
      setMessages([]);
      await loadSessions();
      pushNotice('success', `Session "${activeSession}" deleted.`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not delete session.';
      setWorkspaceError(msg);
    } finally {
      setWorkspaceBusy(false);
    }
  }, [activeSession, loadSessions, pushNotice, requireReauth]);

  const saveActiveSession = useCallback(async (options?: { silent?: boolean }) => {
    if (!activeSession) {
      return;
    }
    const silent = Boolean(options?.silent);
    const serializableMessages = messages
      .filter((message) => !message.streaming && message.content.trim().length > 0)
      .map((message) => ({ role: message.role, content: message.content, model: message.model }));

    try {
      const response = await authFetch('/sessions/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: activeSession, messages: serializableMessages }),
      });
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not save session.'));
      }
      if (!silent) {
        pushNotice('success', `Saved session "${activeSession}".`);
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not save session.';
      setWorkspaceError(msg);
    }
  }, [activeSession, messages, pushNotice, requireReauth]);

  const openConversation = useCallback(async (conversationId: string) => {
    const target = conversationId.trim();
    if (!target) {
      setActiveConversationId('');
      return;
    }

    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await authFetch(`/conversations/${encodeURIComponent(target)}`);
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not open conversation.'));
      }

      const payload = (await response.json()) as { messages?: unknown };
      const nextMessages = Array.isArray(payload.messages)
        ? toUiMessages(payload.messages as Array<Record<string, unknown>>)
        : [];

      setMessages(nextMessages);
      setActiveConversationId(target);
      setActiveSession('');
      setComposerDraft('');
      pushNotice('info', 'Conversation loaded.');
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not open conversation.';
      setWorkspaceError(msg);
    } finally {
      setWorkspaceBusy(false);
    }
  }, [pushNotice, requireReauth, toUiMessages]);

  const deleteActiveConversation = useCallback(async () => {
    if (!activeConversationId) {
      return;
    }
    const confirmed = window.confirm('Delete this conversation?');
    if (!confirmed) {
      return;
    }

    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await authFetch(`/conversations/${encodeURIComponent(activeConversationId)}`, {
        method: 'DELETE',
      });
      if (response.status === 401) {
        requireReauth();
        return;
      }
      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Could not delete conversation.'));
      }

      setActiveConversationId('');
      setMessages([]);
      await loadConversations();
      pushNotice('success', 'Conversation deleted.');
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Could not delete conversation.';
      setWorkspaceError(msg);
    } finally {
      setWorkspaceBusy(false);
    }
  }, [activeConversationId, loadConversations, pushNotice, requireReauth]);

  useEffect(() => {
    if (!activeSession || sending) {
      return;
    }
    const hasCompletedMessages = messages.some(
      (message) => !message.streaming && message.content.trim().length > 0,
    );
    if (!hasCompletedMessages) {
      return;
    }

    const timer = window.setTimeout(() => {
      void saveActiveSession({ silent: true });
    }, 800);

    return () => {
      window.clearTimeout(timer);
    };
  }, [activeSession, messages, saveActiveSession, sending]);

  // ---- WebSocket setup ----------------------------------------------------

  useEffect(() => {
    const client = new WSClient();
    wsRef.current = client;
    let isCancelled = false;

    client.onConnect(() => {
      setConnected(true);
      setSessionId(client.sessionId ?? undefined);
      setNeedsAuth(false);
      setAuthError('');
      void refreshWorkspaceData();
    });

    client.onDisconnect((event) => {
      setConnected(false);
      if (event.code === 4001) {
        if (!isCancelled) {
          requireReauth();
        }
      }
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

    const bootstrap = async () => {
      const token = getStoredAuthToken();
      if (!token) {
        if (!isCancelled) setNeedsAuth(true);
        return;
      }

      const valid = await checkSessionToken(token);
      if (!valid) {
        if (!isCancelled) {
          setNeedsAuth(true);
          setAuthError('Please log in to connect to LADA.');
        }
        return;
      }

      await refreshWorkspaceData();
      client.connect();
    };

    void bootstrap();

    return () => {
      isCancelled = true;
      client.disconnect();
    };
  }, [authVersion, refreshWorkspaceData, requireReauth]);

  // ---- Send handler -------------------------------------------------------

  const sendMessage = useCallback((text: string, includeUserBubble = true): boolean => {
    if (!text || !wsRef.current || sending || needsAuth) {
      return false;
    }

    const payload = text.trim();
    if (!payload) {
      return false;
    }

    if (includeUserBubble) {
      setMessages((prev) => [...prev, { role: 'user', content: payload }]);
    }

    setSending(true);
    setWorkspaceError('');

    const model = selectedModel === 'auto' ? undefined : selectedModel;
    const id = wsRef.current.sendChat(payload, true, model, {
      useWebSearch: webSearchEnabled,
    });
    pendingIdRef.current = id;
    return true;
  }, [needsAuth, selectedModel, sending, webSearchEnabled]);

  const handleSend = useCallback((text: string) => {
    const sent = sendMessage(text, true);
    if (sent) {
      setComposerDraft('');
    }
  }, [sendMessage]);

  const handleUseAsPrompt = useCallback((content: string, role: 'user' | 'assistant') => {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    const prefix = role === 'assistant' ? 'Context from previous answer:\n' : '';
    setComposerDraft((prev) => {
      if (!prev.trim()) {
        return `${prefix}${trimmed}`;
      }
      return `${prev.trim()}\n\n${prefix}${trimmed}`;
    });
    pushNotice('info', 'Added message content to prompt.');
  }, [pushNotice]);

  const handleResendUserMessage = useCallback((content: string) => {
    const sent = sendMessage(content, true);
    if (sent) {
      pushNotice('info', 'Resent message.');
      return;
    }
    pushNotice('error', 'Could not resend right now.');
  }, [pushNotice, sendMessage]);

  const handleRegenerateAt = useCallback((assistantIndex: number) => {
    for (let idx = assistantIndex - 1; idx >= 0; idx -= 1) {
      const priorMessage = messages[idx];
      if (priorMessage?.role === 'user' && priorMessage.content.trim().length > 0) {
        const sent = sendMessage(priorMessage.content, false);
        if (!sent) {
          setWorkspaceError('Could not regenerate right now.');
          pushNotice('error', 'Could not regenerate right now.');
          return;
        }
        pushNotice('info', 'Regenerating answer...');
        return;
      }
    }
    setWorkspaceError('No matching user prompt found for regeneration.');
    pushNotice('error', 'No matching user prompt found for regeneration.');
  }, [messages, pushNotice, sendMessage]);

  const handleStop = useCallback(() => {
    // Stop streaming - could send a cancel message to the server
    setSending(false);
    pushNotice('info', 'Stopped response generation.');
  }, [pushNotice]);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      const tag = target.tagName.toLowerCase();
      return (
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select' ||
        target.isContentEditable
      );
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (needsAuth) {
        return;
      }

      if (event.key === 'Escape') {
        setWorkspaceError('');
        return;
      }

      if (isEditableTarget(event.target)) {
        return;
      }

      if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
        const key = event.key.toLowerCase();
        if (key === 'n') {
          event.preventDefault();
          startFreshChat();
          return;
        }
        if (key === 'w') {
          event.preventDefault();
          toggleWebSearch();
          return;
        }
      }

      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'r') {
        event.preventDefault();
        void refreshWorkspaceData();
        pushNotice('info', 'Workspace refreshed.');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [needsAuth, pushNotice, refreshWorkspaceData, startFreshChat, toggleWebSearch]);

  const handleAuthLogin = useCallback(async () => {
    const password = authPassword.trim();
    if (!password || authLoading) return;

    setAuthLoading(true);
    setAuthError('');
    try {
      await loginSession(password);
      setNeedsAuth(false);
      setAuthPassword('');
      setAuthVersion((prev) => prev + 1);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Login failed';
      setAuthError(msg);
      setNeedsAuth(true);
    } finally {
      setAuthLoading(false);
    }
  }, [authLoading, authPassword]);

  // Transform models for AnimatedAIInput
  const aiModels: AIModelInfo[] = models.map((m) => ({
    id: m.id,
    name: m.name || m.id,
    provider: m.provider || 'Unknown',
    tier: m.tier,
  }));

  // ---- Render -------------------------------------------------------------

  if (needsAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
        <div className="w-full max-w-md rounded-2xl border border-[var(--border-color)] bg-[var(--surface)]/92 p-6 shadow-[0_20px_50px_rgba(0,0,0,.35)]">
          <h1 className="text-xl font-semibold text-[var(--text)]">Sign in to LADA</h1>
          <p className="mt-2 text-sm text-[var(--text-dim)]">
            Enter your LADA web password to open a session for the Next.js client.
          </p>

          <input
            type="password"
            value={authPassword}
            onChange={(event) => setAuthPassword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                void handleAuthLogin();
              }
            }}
            className="mt-4 w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
            placeholder="LADA_WEB_PASSWORD"
          />

          {authError && (
            <p className="mt-3 text-sm text-red-300">{authError}</p>
          )}

          <button
            onClick={() => {
              void handleAuthLogin();
            }}
            disabled={authLoading || !authPassword.trim()}
            className={cn(
              'mt-5 w-full rounded-lg px-4 py-2 text-sm font-medium text-white transition-all',
              'bg-[linear-gradient(145deg,var(--accent),var(--accent-dark))] hover:brightness-105',
              'disabled:cursor-not-allowed disabled:opacity-60',
            )}
          >
            {authLoading ? 'Signing in...' : 'Sign in'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-[var(--bg)]">
      {notices.length > 0 && (
        <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-[320px] flex-col gap-2">
          {notices.map((notice) => (
            <div
              key={notice.id}
              className={cn(
                'pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-xs shadow-[0_10px_30px_rgba(0,0,0,.28)] backdrop-blur',
                notice.kind === 'success' && 'border-emerald-400/35 bg-emerald-500/15 text-emerald-100',
                notice.kind === 'info' && 'border-sky-400/35 bg-sky-500/15 text-sky-100',
                notice.kind === 'error' && 'border-red-400/35 bg-red-500/15 text-red-100',
              )}
            >
              {notice.kind === 'success' && <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />}
              {notice.kind === 'info' && <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />}
              {notice.kind === 'error' && <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />}
              <span className="flex-1 leading-relaxed">{notice.message}</span>
              <button
                className="rounded p-0.5 text-current/70 transition-colors hover:bg-white/10 hover:text-current"
                onClick={() => dismissNotice(notice.id)}
                aria-label="Dismiss notice"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Status bar */}
      <div className="flex items-center justify-end px-4 py-2 border-b border-[var(--border-color)] bg-[linear-gradient(180deg,rgba(18,25,35,.84)_0%,rgba(18,25,35,.74)_100%)] backdrop-blur">
        <ProviderStatus
          connected={connected}
          sessionId={sessionId}
          providers={providers}
        />
      </div>

      {/* Workspace controls */}
      <div className="border-b border-[var(--border-color)] bg-[var(--surface)]/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1120px] flex-wrap items-center gap-2 px-4 py-3">
          <div className="flex items-center gap-2 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/70 px-2 py-1.5">
            <FolderOpen className="h-3.5 w-3.5 text-[var(--text-faint)]" />
            <input
              value={sessionFilter}
              onChange={(event) => setSessionFilter(event.target.value)}
              placeholder="Filter sessions"
              className="w-[120px] rounded border border-[var(--border-color)] bg-[var(--surface-3)] px-2 py-1 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
            />
            <select
              value={activeSession}
              onChange={(event) => {
                void switchSession(event.target.value);
              }}
              className="min-w-[170px] bg-transparent text-xs text-[var(--text)] outline-none"
              disabled={workspaceBusy}
            >
              <option value="">No active session</option>
              {filteredSessions.map((sessionName) => (
                <option key={sessionName} value={sessionName}>
                  {sessionName}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                void createSession();
              }}
              className="rounded-md p-1 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text)]"
              title="New session"
              disabled={workspaceBusy}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => {
                void saveActiveSession();
              }}
              className="rounded-md p-1 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-50"
              title="Save active session"
              disabled={workspaceBusy || !activeSession}
            >
              <Save className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => {
                void deleteActiveSession();
              }}
              className="rounded-md p-1 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-3)] hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
              title="Delete active session"
              disabled={workspaceBusy || !activeSession}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <span className="text-[10px] text-[var(--text-faint)]">
              {filteredSessions.length}/{sessions.length}
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/70 px-2 py-1.5">
            <History className="h-3.5 w-3.5 text-[var(--text-faint)]" />
            <input
              value={conversationFilter}
              onChange={(event) => setConversationFilter(event.target.value)}
              placeholder="Filter conversations"
              className="w-[140px] rounded border border-[var(--border-color)] bg-[var(--surface-3)] px-2 py-1 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
            />
            <select
              value={activeConversationId}
              onChange={(event) => {
                void openConversation(event.target.value);
              }}
              className="min-w-[190px] bg-transparent text-xs text-[var(--text)] outline-none"
              disabled={workspaceBusy}
            >
              <option value="">Load conversation</option>
              {filteredConversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title} ({conversation.message_count})
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                void loadConversations();
              }}
              className="rounded-md p-1 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text)]"
              title="Refresh conversations"
              disabled={workspaceBusy}
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => {
                void deleteActiveConversation();
              }}
              className="rounded-md p-1 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-3)] hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
              title="Delete selected conversation"
              disabled={workspaceBusy || !activeConversationId}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <span className="text-[10px] text-[var(--text-faint)]">
              {filteredConversations.length}/{conversations.length}
            </span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={startFreshChat}
              className="flex items-center gap-2 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/70 px-3 py-2 text-xs font-medium text-[var(--text-dim)] transition-colors hover:text-[var(--text)]"
              title="Start a fresh chat view"
            >
              <Plus className="h-3.5 w-3.5" />
              New Chat
            </button>

            <button
              onClick={() => {
                toggleWebSearch();
              }}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                webSearchEnabled
                  ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-hover)]'
                  : 'border-[var(--border-color)] bg-[var(--surface-2)]/70 text-[var(--text-dim)] hover:text-[var(--text)]',
              )}
              title="Toggle web search for new messages"
            >
              <Globe className="h-3.5 w-3.5" />
              {webSearchEnabled ? 'Web Search ON' : 'Web Search OFF'}
            </button>
          </div>
        </div>

        {workspaceError && (
          <div className="mx-auto w-full max-w-[1120px] px-4 pb-3 text-xs text-red-300">
            {workspaceError}
          </div>
        )}

        <div className="mx-auto w-full max-w-[1120px] px-4 pb-3 text-[10px] text-[var(--text-faint)]">
          Shortcuts: Alt+N new chat, Alt+W toggle web search, Ctrl+Shift+R refresh workspace
        </div>
      </div>

      {/* Message area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeScreen />
        ) : (
          <div className="max-w-[860px] mx-auto py-5 px-5">
            <div className="space-y-4">
              {messages.map((msg, idx) => (
                <ChatMessage
                  key={idx}
                  role={msg.role}
                  content={msg.content}
                  model={msg.model}
                  sources={msg.sources as { url: string; title: string; domain: string }[]}
                  streaming={msg.streaming}
                  onUseAsPrompt={handleUseAsPrompt}
                  onResend={msg.role === 'user' ? handleResendUserMessage : undefined}
                  onRegenerate={msg.role === 'assistant' ? () => handleRegenerateAt(idx) : undefined}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-[var(--border-color)] bg-[linear-gradient(180deg,rgba(18,25,35,.76)_0%,rgba(18,25,35,.92)_100%)] backdrop-blur py-3">
        <AnimatedAIInput
          models={aiModels}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={sending}
          disabled={!connected}
          placeholder={connected ? "Ask LADA anything..." : "Connecting..."}
          value={composerDraft}
          onValueChange={setComposerDraft}
        />
      </div>
    </div>
  );
}
