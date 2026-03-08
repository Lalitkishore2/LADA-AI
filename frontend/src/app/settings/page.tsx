'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { WSClient, generateId } from '@/lib/ws-client';
import ProviderStatus from '@/components/ProviderStatus';
import type { ServerMessage } from '@/types/ws-protocol';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Provider {
  name: string;
  status: string;
  available: boolean;
}

interface RateLimiterStats {
  requests_made?: number;
  requests_limit?: number;
  tokens_used?: number;
  tokens_limit?: number;
  reset_at?: string;
}

interface SystemStatus {
  uptime?: number;
  ws_connections?: number;
  providers?: Record<string, Record<string, unknown>>;
  backends?: Record<string, unknown>;
  cost?: Record<string, unknown>;
  rate_limiter?: RateLimiterStats;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatUptime(seconds?: number): string {
  if (!seconds) return '-';
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [clearing, setClearing] = useState(false);
  const [clearMessage, setClearMessage] = useState('');

  const wsRef = React.useRef<WSClient | null>(null);

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
        case 'system.connected':
          setSessionId(msg.data.session_id);
          break;

        case 'system.status': {
          const raw = msg.data as unknown as SystemStatus;
          setStatus(raw);

          // Parse providers
          if (raw.providers && typeof raw.providers === 'object') {
            const list: Provider[] = Object.entries(raw.providers).map(
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

        case 'system.ack':
          setClearing(false);
          setClearMessage('History cleared successfully.');
          setTimeout(() => setClearMessage(''), 3000);
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

  // ---- Handlers -----------------------------------------------------------

  const handleRefresh = useCallback(() => {
    if (wsRef.current?.connected) {
      wsRef.current.send({
        type: 'system',
        id: generateId(),
        data: { action: 'status' },
      });
    }
  }, []);

  const handleClearHistory = useCallback(() => {
    if (!wsRef.current?.connected) return;
    setClearing(true);
    setClearMessage('');
    wsRef.current.send({
      type: 'system',
      id: generateId(),
      data: { action: 'clear_history' },
    });
  }, []);

  // ---- Render -------------------------------------------------------------

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-1">Settings</h1>
      <p className="text-[var(--text-secondary)] text-sm mb-8">
        System status, provider health, and session management.
      </p>

      {/* ---- Connection / Provider status ---- */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Provider Status</h2>
          <button
            onClick={handleRefresh}
            disabled={!connected}
            className="text-xs text-indigo-400 hover:text-indigo-300 disabled:text-gray-600 transition-colors"
          >
            Refresh
          </button>
        </div>

        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
          <ProviderStatus
            connected={connected}
            sessionId={sessionId}
            providers={providers}
          />

          {/* Per-provider cards */}
          {providers.length > 0 && (
            <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {providers.map((p) => (
                <div
                  key={p.name}
                  className="flex items-center justify-between bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-4 py-3"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-block w-2.5 h-2.5 rounded-full ${
                        p.available
                          ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.4)]'
                          : 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]'
                      }`}
                    />
                    <span className="text-sm font-medium">{p.name}</span>
                  </div>
                  <span
                    className={`text-xs ${
                      p.available ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {p.available ? 'Available' : 'Unavailable'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {providers.length === 0 && connected && (
            <p className="mt-4 text-sm text-[var(--text-secondary)]">
              No provider data received yet. Click Refresh to retry.
            </p>
          )}
        </div>
      </section>

      {/* ---- Rate Limiter Stats ---- */}
      {status?.rate_limiter && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4">Rate Limiter</h2>
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <div className="text-xs text-[var(--text-secondary)] mb-1">
                  Requests
                </div>
                <div className="text-lg font-mono">
                  {status.rate_limiter.requests_made ?? '-'}
                  {status.rate_limiter.requests_limit && (
                    <span className="text-sm text-[var(--text-secondary)]">
                      {' '}
                      / {status.rate_limiter.requests_limit}
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-xs text-[var(--text-secondary)] mb-1">
                  Tokens Used
                </div>
                <div className="text-lg font-mono">
                  {status.rate_limiter.tokens_used?.toLocaleString() ?? '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-[var(--text-secondary)] mb-1">
                  Token Limit
                </div>
                <div className="text-lg font-mono">
                  {status.rate_limiter.tokens_limit?.toLocaleString() ?? '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-[var(--text-secondary)] mb-1">
                  Resets At
                </div>
                <div className="text-sm font-mono">
                  {status.rate_limiter.reset_at ?? '-'}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ---- Session Info ---- */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Session</h2>
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-[var(--text-secondary)] mb-1">
                Session ID
              </div>
              <div className="text-sm font-mono">
                {sessionId ?? 'Not connected'}
              </div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-secondary)] mb-1">
                Uptime
              </div>
              <div className="text-sm font-mono">
                {formatUptime(status?.uptime)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-secondary)] mb-1">
                WS Connections
              </div>
              <div className="text-sm font-mono">
                {status?.ws_connections ?? '-'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Actions ---- */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Actions</h2>
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Clear Conversation History</div>
              <div className="text-xs text-[var(--text-secondary)] mt-0.5">
                Remove all messages from the current session.
              </div>
            </div>
            <button
              onClick={handleClearHistory}
              disabled={!connected || clearing}
              className="bg-red-600 hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded-lg px-4 py-2 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              {clearing ? 'Clearing...' : 'Clear History'}
            </button>
          </div>

          {clearMessage && (
            <div className="mt-3 text-sm text-green-400">{clearMessage}</div>
          )}
        </div>
      </section>
    </div>
  );
}
