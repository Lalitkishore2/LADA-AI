'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { WSClient, generateId } from '@/lib/ws-client';
import { cn } from '@/lib/utils';
import {
  RefreshCw,
  Wifi,
  WifiOff,
  CheckCircle2,
  XCircle,
  Clock,
  Users,
  Trash2,
  Activity,
  Server,
  Gauge,
  Settings2,
  Shield,
} from 'lucide-react';
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
// Section Card Component
// ---------------------------------------------------------------------------

function SectionCard({ 
  title, 
  icon: Icon, 
  children,
  action
}: { 
  title: string; 
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/50 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800/50">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-zinc-800/50">
            <Icon className="w-4 h-4 text-indigo-400" />
          </div>
          <h2 className="font-semibold text-zinc-100">{title}</h2>
        </div>
        {action}
      </div>
      <div className="p-5">
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat Box Component
// ---------------------------------------------------------------------------

function StatBox({ 
  label, 
  value, 
  subtext 
}: { 
  label: string; 
  value: string | number; 
  subtext?: string;
}) {
  return (
    <div className="p-4 rounded-lg bg-zinc-800/30 border border-zinc-800/50">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className="text-lg font-mono text-zinc-200">{value}</div>
      {subtext && <div className="text-xs text-zinc-600 mt-0.5">{subtext}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [clearing, setClearing] = useState(false);
  const [clearMessage, setClearMessage] = useState('');
  const [refreshing, setRefreshing] = useState(false);

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
          setRefreshing(false);
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
      setRefreshing(true);
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

  // Stats
  const availableCount = providers.filter(p => p.available).length;
  const totalCount = providers.length;

  // ---- Render -------------------------------------------------------------

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100 mb-2">Settings</h1>
            <p className="text-zinc-400">
              System status, providers, and session management
            </p>
          </div>
          <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
            connected 
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              : "bg-red-500/10 text-red-400 border border-red-500/20"
          )}>
            {connected ? (
              <>
                <Wifi className="w-4 h-4" />
                <span>Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4" />
                <span>Disconnected</span>
              </>
            )}
          </div>
        </div>

        <div className="space-y-6">
          {/* Provider Status */}
          <SectionCard
            title="Providers"
            icon={Server}
            action={
              <button
                onClick={handleRefresh}
                disabled={!connected || refreshing}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all",
                  "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
              >
                <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
                Refresh
              </button>
            }
          >
            {/* Summary */}
            <div className="flex items-center gap-4 mb-4 pb-4 border-b border-zinc-800/50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span className="text-sm text-zinc-300">
                  <span className="font-medium">{availableCount}</span> available
                </span>
              </div>
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-red-400" />
                <span className="text-sm text-zinc-300">
                  <span className="font-medium">{totalCount - availableCount}</span> unavailable
                </span>
              </div>
            </div>

            {/* Provider grid */}
            {providers.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {providers.map((p) => (
                  <div
                    key={p.name}
                    className={cn(
                      "flex items-center justify-between p-3 rounded-lg border transition-colors",
                      p.available
                        ? "bg-zinc-800/30 border-zinc-800/50 hover:border-zinc-700/50"
                        : "bg-red-500/5 border-red-500/20"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "w-2 h-2 rounded-full",
                          p.available 
                            ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]"
                            : "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]"
                        )}
                      />
                      <span className="text-sm font-medium text-zinc-200">{p.name}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-500">
                {connected ? 'No provider data. Click Refresh.' : 'Connect to see providers.'}
              </p>
            )}
          </SectionCard>

          {/* Rate Limiter */}
          <SectionCard title="Rate Limits" icon={Gauge}>
            {status?.rate_limiter ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <StatBox
                  label="Requests"
                  value={status.rate_limiter.requests_made ?? 0}
                  subtext={status.rate_limiter.requests_limit 
                    ? `of ${status.rate_limiter.requests_limit}` 
                    : undefined}
                />
                <StatBox
                  label="Tokens Used"
                  value={(status.rate_limiter.tokens_used ?? 0).toLocaleString()}
                />
                <StatBox
                  label="Token Limit"
                  value={(status.rate_limiter.tokens_limit ?? 0).toLocaleString()}
                />
                <StatBox
                  label="Resets At"
                  value={status.rate_limiter.reset_at ?? '-'}
                />
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No rate limit data available.</p>
            )}
          </SectionCard>

          {/* Session Info */}
          <SectionCard title="Session" icon={Activity}>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <StatBox
                label="Session ID"
                value={sessionId ? sessionId.slice(0, 8) + '...' : 'Not connected'}
              />
              <StatBox
                label="Uptime"
                value={formatUptime(status?.uptime)}
              />
              <StatBox
                label="Active Connections"
                value={status?.ws_connections ?? '-'}
              />
            </div>
          </SectionCard>

          {/* Actions */}
          <SectionCard title="Actions" icon={Settings2}>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-zinc-200">
                  Clear Conversation History
                </div>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Remove all messages from the current session
                </p>
              </div>
              <button
                onClick={handleClearHistory}
                disabled={!connected || clearing}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  "bg-red-500/10 text-red-400 border border-red-500/20",
                  "hover:bg-red-500/20 hover:border-red-500/30",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
              >
                <Trash2 className="w-4 h-4" />
                {clearing ? 'Clearing...' : 'Clear History'}
              </button>
            </div>

            {clearMessage && (
              <div className="mt-4 flex items-center gap-2 text-sm text-emerald-400">
                <CheckCircle2 className="w-4 h-4" />
                {clearMessage}
              </div>
            )}
          </SectionCard>

          {/* Security Note */}
          <div className="flex items-start gap-3 p-4 rounded-lg bg-indigo-500/5 border border-indigo-500/20">
            <Shield className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-zinc-300">
                All API keys and credentials are stored locally in your <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded">.env</code> file.
              </p>
              <p className="text-xs text-zinc-500 mt-1">
                LADA never sends your credentials to external servers.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
