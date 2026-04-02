'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { WSClient, generateId } from '@/lib/ws-client';
import {
  authFetch,
  checkSessionToken,
  clearStoredAuthToken,
  getStoredAuthToken,
  loginSession,
} from '@/lib/lada-api';
import {
  RemoteApiError,
  type RemoteBreadcrumb,
  type RemoteEntry,
  type RemoteStatus,
  downloadRemoteBinary,
  executeRemoteCommand,
  fetchRemoteFiles,
  fetchRemoteStatus,
} from '@/lib/remote-api';
import { cn } from '@/lib/utils';
import {
  RefreshCw,
  Wifi,
  WifiOff,
  CheckCircle2,
  XCircle,
  Trash2,
  Activity,
  Server,
  Gauge,
  Settings2,
  Shield,
  TerminalSquare,
  FolderOpen,
  Download,
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
    <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface)]/88 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-color)]">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border-color)]">
            <Icon className="w-4 h-4 text-[var(--accent-hover)]" />
          </div>
          <h2 className="font-semibold text-[var(--text)]">{title}</h2>
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
    <div className="p-4 rounded-lg bg-[var(--surface-2)]/65 border border-[var(--border-color)]">
      <div className="text-xs text-[var(--text-faint)] mb-1">{label}</div>
      <div className="text-lg font-mono text-[var(--text)]">{value}</div>
      {subtext && <div className="text-xs text-[var(--text-dim)] mt-0.5">{subtext}</div>}
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
  const [needsAuth, setNeedsAuth] = useState(false);
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authVersion, setAuthVersion] = useState(0);

  const [remoteStatus, setRemoteStatus] = useState<RemoteStatus | null>(null);
  const [remoteRefreshing, setRemoteRefreshing] = useState(false);
  const [remoteCommand, setRemoteCommand] = useState('');
  const [remoteRunning, setRemoteRunning] = useState(false);
  const [remoteOutput, setRemoteOutput] = useState('No remote command executed yet.');
  const [remotePath, setRemotePath] = useState('');
  const [remoteEntries, setRemoteEntries] = useState<RemoteEntry[]>([]);
  const [remoteBreadcrumbs, setRemoteBreadcrumbs] = useState<RemoteBreadcrumb[]>([]);
  const [remoteParentPath, setRemoteParentPath] = useState('');
  const [remoteLoading, setRemoteLoading] = useState(false);

  const wsRef = React.useRef<WSClient | null>(null);

  const loadRemoteFiles = useCallback(async (path: string) => {
    const target = path.trim();
    if (!target) {
      setRemoteEntries([]);
      setRemoteBreadcrumbs([]);
      return;
    }

    setRemoteLoading(true);
    try {
      const result = await fetchRemoteFiles(target);
      setRemoteEntries(result.entries);
      setRemoteBreadcrumbs(result.breadcrumbs);
      setRemoteParentPath(result.parent);
      setRemotePath(result.path);
    } catch (error) {
      if (error instanceof RemoteApiError && error.status === 401) {
        clearStoredAuthToken();
        setNeedsAuth(true);
        setAuthError('Session expired. Please log in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Could not load remote files';
      setRemoteOutput(`Error: ${message}`);
      setRemoteEntries([]);
      setRemoteBreadcrumbs([]);
    } finally {
      setRemoteLoading(false);
    }
  }, []);

  const loadRemoteStatus = useCallback(async () => {
    setRemoteRefreshing(true);
    try {
      const nextStatus = await fetchRemoteStatus();

      setRemoteStatus(nextStatus);
      const initialPath = nextStatus.current_path || nextStatus.allowed_roots[0] || '';
      setRemotePath(initialPath);

      if (nextStatus.downloads_enabled && initialPath) {
        await loadRemoteFiles(initialPath);
      } else {
        setRemoteEntries([]);
        setRemoteBreadcrumbs([]);
      }
    } catch (error) {
      if (error instanceof RemoteApiError && error.status === 401) {
        clearStoredAuthToken();
        setNeedsAuth(true);
        setAuthError('Session expired. Please log in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Could not load remote status';
      setRemoteOutput(`Error: ${message}`);
    } finally {
      setRemoteRefreshing(false);
    }
  }, [loadRemoteFiles]);

  const runRemoteCommand = useCallback(async () => {
    const command = remoteCommand.trim();
    if (!command || remoteRunning) return;

    setRemoteRunning(true);
    setRemoteOutput('Running command...');
    try {
      const result = await executeRemoteCommand(command);
      setRemoteOutput(`${result.response}\n\nEngine: ${result.engine}`);
    } catch (error) {
      if (error instanceof RemoteApiError && error.status === 401) {
        clearStoredAuthToken();
        setNeedsAuth(true);
        setAuthError('Session expired. Please log in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Remote command failed';
      setRemoteOutput(`Error: ${message}`);
    } finally {
      setRemoteRunning(false);
    }
  }, [remoteCommand, remoteRunning]);

  const downloadRemoteFile = useCallback(async (path: string) => {
    try {
      const result = await downloadRemoteBinary(path);

      const objectUrl = window.URL.createObjectURL(result.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = result.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);

      setRemoteOutput(`Downloaded: ${result.filename}`);
    } catch (error) {
      if (error instanceof RemoteApiError && error.status === 401) {
        clearStoredAuthToken();
        setNeedsAuth(true);
        setAuthError('Session expired. Please log in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Download failed';
      setRemoteOutput(`Error: ${message}`);
    }
  }, []);

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
      client.send({
        type: 'system',
        id: generateId(),
        data: { action: 'status' },
      });
    });

    client.onDisconnect((event) => {
      setConnected(false);
      if (event.code === 4001) {
        clearStoredAuthToken();
        if (!isCancelled) {
          setNeedsAuth(true);
          setAuthError('Session expired. Please log in again.');
        }
      }
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
          setAuthError('Please log in to view settings.');
        }
        return;
      }

      client.connect();
    };

    void bootstrap();

    return () => {
      isCancelled = true;
      client.disconnect();
    };
  }, [authVersion]);

  useEffect(() => {
    if (connected && !needsAuth) {
      void loadRemoteStatus();
    }
  }, [connected, needsAuth, loadRemoteStatus]);

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
      const message = error instanceof Error ? error.message : 'Login failed';
      setAuthError(message);
      setNeedsAuth(true);
    } finally {
      setAuthLoading(false);
    }
  }, [authLoading, authPassword]);

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

  if (needsAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
        <div className="w-full max-w-md rounded-2xl border border-[var(--border-color)] bg-[var(--surface)]/92 p-6 shadow-[0_20px_50px_rgba(0,0,0,.35)]">
          <h1 className="text-xl font-semibold text-[var(--text)]">Sign in to LADA</h1>
          <p className="mt-2 text-sm text-[var(--text-dim)]">
            Enter your LADA web password to access settings and remote controls.
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
    <div className="min-h-screen bg-[var(--bg)] p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text)] mb-2">Settings</h1>
            <p className="text-[var(--text-dim)]">
              System status, providers, and session management
            </p>
          </div>
          <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
            connected 
              ? "bg-[var(--accent-soft)] text-[var(--accent-hover)] border border-[var(--accent)]/30"
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
                  "text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
              >
                <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
                Refresh
              </button>
            }
          >
            {/* Summary */}
            <div className="flex items-center gap-4 mb-4 pb-4 border-b border-[var(--border-color)]">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-[var(--accent-hover)]" />
                <span className="text-sm text-[var(--text-dim)]">
                  <span className="font-medium">{availableCount}</span> available
                </span>
              </div>
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-red-400" />
                <span className="text-sm text-[var(--text-dim)]">
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
                        ? "bg-[var(--surface-2)]/65 border-[var(--border-color)] hover:border-[var(--accent)]/45"
                        : "bg-red-500/5 border-red-500/20"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "w-2 h-2 rounded-full",
                          p.available 
                            ? "bg-[var(--accent-hover)] shadow-[0_0_8px_rgba(25,187,147,0.45)]"
                            : "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]"
                        )}
                      />
                      <span className="text-sm font-medium text-[var(--text)]">{p.name}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-faint)]">
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
              <p className="text-sm text-[var(--text-faint)]">No rate limit data available.</p>
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
                <div className="text-sm font-medium text-[var(--text)]">
                  Clear Conversation History
                </div>
                <p className="text-xs text-[var(--text-faint)] mt-0.5">
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
              <div className="mt-4 flex items-center gap-2 text-sm text-[var(--accent-hover)]">
                <CheckCircle2 className="w-4 h-4" />
                {clearMessage}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Remote Access"
            icon={TerminalSquare}
            action={
              <div className="flex items-center gap-2">
                <Link
                  href="/remote"
                  className={cn(
                    'rounded-lg border border-[var(--border-color)] px-3 py-1.5 text-sm text-[var(--text-dim)] transition-all',
                    'hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
                  )}
                >
                  Open page
                </Link>
                <button
                  onClick={() => {
                    void loadRemoteStatus();
                  }}
                  disabled={!connected || remoteRefreshing}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all',
                    'text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                >
                  <RefreshCw className={cn('w-4 h-4', remoteRefreshing && 'animate-spin')} />
                  Refresh
                </button>
              </div>
            }
          >
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/60 p-3">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    remoteStatus?.enabled ? 'bg-[var(--accent-hover)]' : 'bg-red-400',
                  )}
                />
                <span className="text-sm text-[var(--text-dim)]">
                  Remote control: <span className="font-medium text-[var(--text)]">{remoteStatus?.enabled ? 'ON' : 'OFF'}</span>
                </span>
                <span className="text-sm text-[var(--text-dim)]">
                  Files: <span className="font-medium text-[var(--text)]">{remoteStatus?.downloads_enabled ? 'ON' : 'OFF'}</span>
                </span>
                <span className="text-xs text-[var(--text-faint)]">
                  Max download: {remoteStatus?.max_download_mb ?? 0} MB
                </span>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-[var(--text)]">Run Remote Command</div>
                <div className="flex gap-2">
                  <input
                    value={remoteCommand}
                    onChange={(event) => setRemoteCommand(event.target.value)}
                    className="flex-1 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
                    placeholder="open notepad"
                    disabled={!remoteStatus?.enabled}
                  />
                  <button
                    onClick={() => {
                      void runRemoteCommand();
                    }}
                    disabled={!remoteStatus?.enabled || remoteRunning || !remoteCommand.trim()}
                    className={cn(
                      'rounded-lg px-4 py-2 text-sm font-medium text-white transition-all',
                      'bg-[linear-gradient(145deg,var(--accent),var(--accent-dark))] hover:brightness-105',
                      'disabled:cursor-not-allowed disabled:opacity-60',
                    )}
                  >
                    {remoteRunning ? 'Running...' : 'Run'}
                  </button>
                </div>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/55 p-3 text-xs text-[var(--text-dim)] whitespace-pre-wrap">
                  {remoteOutput}
                </pre>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-[var(--text)]">Remote Files</div>
                <div className="flex flex-wrap gap-2">
                  <select
                    value={remotePath}
                    onChange={(event) => {
                      const nextPath = event.target.value;
                      setRemotePath(nextPath);
                      void loadRemoteFiles(nextPath);
                    }}
                    className="min-w-[220px] rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)]"
                    disabled={!remoteStatus?.downloads_enabled || !(remoteStatus?.allowed_roots?.length)}
                  >
                    {(remoteStatus?.allowed_roots || []).map((root) => (
                      <option key={root} value={root}>
                        {root}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => {
                      if (remoteParentPath) {
                        void loadRemoteFiles(remoteParentPath);
                      }
                    }}
                    disabled={!remoteStatus?.downloads_enabled || !remoteParentPath}
                    className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-dim)] hover:text-[var(--text)] disabled:opacity-50"
                  >
                    Up
                  </button>
                  <button
                    onClick={() => {
                      if (remotePath) {
                        void loadRemoteFiles(remotePath);
                      }
                    }}
                    disabled={!remoteStatus?.downloads_enabled || !remotePath}
                    className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-dim)] hover:text-[var(--text)] disabled:opacity-50"
                  >
                    Open
                  </button>
                </div>

                {remoteBreadcrumbs.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-faint)]">
                    {remoteBreadcrumbs.map((crumb, index) => (
                      <button
                        key={`${crumb.path}-${index}`}
                        onClick={() => {
                          void loadRemoteFiles(crumb.path);
                        }}
                        className={cn(
                          'rounded-full border px-2 py-0.5',
                          crumb.is_root
                            ? 'border-[var(--accent)] text-[var(--accent-hover)]'
                            : 'border-[var(--border-color)] text-[var(--text-dim)] hover:text-[var(--text)]',
                        )}
                      >
                        {crumb.name}
                      </button>
                    ))}
                  </div>
                )}

                <div className="mt-3 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/55">
                  {remoteLoading ? (
                    <div className="p-3 text-sm text-[var(--text-dim)]">Loading...</div>
                  ) : remoteEntries.length > 0 ? (
                    remoteEntries.map((entry) => (
                      <div
                        key={entry.path}
                        className="flex items-center justify-between gap-3 border-b border-[var(--border-color)] p-3 last:border-b-0"
                      >
                        <button
                          onClick={() => {
                            if (entry.is_dir) {
                              void loadRemoteFiles(entry.path);
                            } else {
                              void downloadRemoteFile(entry.path);
                            }
                          }}
                          className="flex items-center gap-2 text-sm text-[var(--text)] hover:text-[var(--accent-hover)]"
                        >
                          <FolderOpen className="h-4 w-4" />
                          {entry.name}
                        </button>
                        {!entry.is_dir && (
                          <button
                            onClick={() => {
                              void downloadRemoteFile(entry.path);
                            }}
                            className="flex items-center gap-1 rounded-lg border border-[var(--border-color)] px-2 py-1 text-xs text-[var(--text-dim)] hover:text-[var(--text)]"
                          >
                            <Download className="h-3.5 w-3.5" />
                            Download
                          </button>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="p-3 text-sm text-[var(--text-faint)]">No files loaded.</div>
                  )}
                </div>
              </div>
            </div>
          </SectionCard>

          {/* Security Note */}
          <div className="flex items-start gap-3 p-4 rounded-lg bg-[var(--accent-soft)] border border-[var(--accent)]/30">
            <Shield className="w-5 h-5 text-[var(--accent-hover)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-[var(--text-dim)]">
                All API keys and credentials are stored locally in your <code className="text-xs bg-[var(--surface-2)] px-1.5 py-0.5 rounded border border-[var(--border-color)]">.env</code> file.
              </p>
              <p className="text-xs text-[var(--text-faint)] mt-1">
                LADA never sends your credentials to external servers.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
