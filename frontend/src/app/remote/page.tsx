'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
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
  type RolloutStatus,
  downloadRemoteBinary,
  executeRemoteCommand,
  fetchRemoteFiles,
  fetchRolloutStatus,
  fetchRemoteStatus,
} from '@/lib/remote-api';
import { cn } from '@/lib/utils';
import {
  RefreshCw,
  Shield,
  TerminalSquare,
  FolderOpen,
  Download,
  ArrowLeft,
  KeyRound,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

export default function RemotePage() {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  const [remoteStatus, setRemoteStatus] = useState<RemoteStatus | null>(null);
  const [rolloutStatus, setRolloutStatus] = useState<RolloutStatus | null>(null);
  const [remoteRefreshing, setRemoteRefreshing] = useState(false);
  const [remoteCommand, setRemoteCommand] = useState('');
  const [remoteRunning, setRemoteRunning] = useState(false);
  const [remoteOutput, setRemoteOutput] = useState('No remote command executed yet.');
  const [remotePath, setRemotePath] = useState('');
  const [remoteEntries, setRemoteEntries] = useState<RemoteEntry[]>([]);
  const [remoteBreadcrumbs, setRemoteBreadcrumbs] = useState<RemoteBreadcrumb[]>([]);
  const [remoteParentPath, setRemoteParentPath] = useState('');
  const [remoteLoading, setRemoteLoading] = useState(false);

  const requireAuth = useCallback((message: string) => {
    clearStoredAuthToken();
    setNeedsAuth(true);
    setAuthError(message);
  }, []);

  const loadRemoteFiles = useCallback(
    async (path: string) => {
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
          requireAuth('Session expired. Please sign in again.');
          return;
        }
        const message = error instanceof Error ? error.message : 'Could not load remote files';
        setRemoteOutput(`Error: ${message}`);
        setRemoteEntries([]);
        setRemoteBreadcrumbs([]);
      } finally {
        setRemoteLoading(false);
      }
    },
    [requireAuth],
  );

  const loadRemoteStatus = useCallback(async (deepCheck = false) => {
    setRemoteRefreshing(true);
    try {
      const [nextStatus, nextRollout] = await Promise.all([
        fetchRemoteStatus(),
        fetchRolloutStatus(deepCheck),
      ]);

      setRemoteStatus(nextStatus);
      setRolloutStatus(nextRollout);
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
        requireAuth('Session expired. Please sign in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Could not load remote status';
      setRemoteOutput(`Error: ${message}`);
    } finally {
      setRemoteRefreshing(false);
    }
  }, [loadRemoteFiles, requireAuth]);

  const runRemoteCommand = useCallback(async () => {
    const command = remoteCommand.trim();
    if (!command || remoteRunning) return;

    setRemoteRunning(true);
    setRemoteOutput('Running command...');

    try {
      const result = await executeRemoteCommand(command);
      const requestId = result.request_id || remoteStatus?.request_id || '';
      setRemoteOutput(
        `${result.response}\n\nEngine: ${result.engine}${requestId ? `\nRequest ID: ${requestId}` : ''}`,
      );
    } catch (error) {
      if (error instanceof RemoteApiError && error.status === 401) {
        requireAuth('Session expired. Please sign in again.');
        return;
      }
      const message = error instanceof Error ? error.message : 'Remote command failed';
      setRemoteOutput(`Error: ${message}`);
    } finally {
      setRemoteRunning(false);
    }
  }, [remoteCommand, remoteRunning, remoteStatus?.request_id, requireAuth]);

  const downloadRemoteFile = useCallback(
    async (path: string) => {
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
          requireAuth('Session expired. Please sign in again.');
          return;
        }
        const message = error instanceof Error ? error.message : 'Download failed';
        setRemoteOutput(`Error: ${message}`);
      }
    },
    [requireAuth],
  );

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      const token = getStoredAuthToken();
      if (!token) {
        if (!cancelled) {
          setNeedsAuth(true);
        }
        return;
      }

      const valid = await checkSessionToken(token);
      if (!valid) {
        if (!cancelled) {
          requireAuth('Please sign in to use remote control.');
        }
        return;
      }

      if (!cancelled) {
        setNeedsAuth(false);
        setAuthError('');
      }

      await loadRemoteStatus();
    };

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [loadRemoteStatus, requireAuth]);

  const handleAuthLogin = useCallback(async () => {
    const password = authPassword.trim();
    if (!password || authLoading) return;

    setAuthLoading(true);
    setAuthError('');
    try {
      await loginSession(password);
      setNeedsAuth(false);
      setAuthPassword('');
      await loadRemoteStatus();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed';
      setAuthError(message);
      setNeedsAuth(true);
    } finally {
      setAuthLoading(false);
    }
  }, [authLoading, authPassword, loadRemoteStatus]);

  if (needsAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
        <div className="w-full max-w-md rounded-2xl border border-[var(--border-color)] bg-[var(--surface)]/92 p-6 shadow-[0_20px_50px_rgba(0,0,0,.35)]">
          <div className="mb-3 flex items-center gap-2 text-[var(--text)]">
            <KeyRound className="h-5 w-5 text-[var(--accent-hover)]" />
            <h1 className="text-xl font-semibold">Sign in to Remote Control</h1>
          </div>
          <p className="text-sm text-[var(--text-dim)]">
            Enter your LADA web password to access remote commands and files.
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

          {authError && <p className="mt-3 text-sm text-red-300">{authError}</p>}

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
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text)]">Remote Control</h1>
            <p className="text-sm text-[var(--text-dim)]">
              Run safe remote commands and browse/download allowed files.
            </p>
          </div>
          <button
            onClick={() => {
              void loadRemoteStatus(false);
            }}
            disabled={remoteRefreshing}
            className={cn(
              'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-all',
              'text-[var(--text-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            <RefreshCw className={cn('h-4 w-4', remoteRefreshing && 'animate-spin')} />
            Refresh
          </button>
        </div>

        <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface)]/88 p-5">
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/60 p-3">
            <span
              className={cn(
                'h-2.5 w-2.5 rounded-full',
                remoteStatus?.enabled ? 'bg-[var(--accent-hover)]' : 'bg-red-400',
              )}
            />
            <span className="text-sm text-[var(--text-dim)]">
              Remote control:{' '}
              <span className="font-medium text-[var(--text)]">{remoteStatus?.enabled ? 'ON' : 'OFF'}</span>
            </span>
            <span className="text-sm text-[var(--text-dim)]">
              Files:{' '}
              <span className="font-medium text-[var(--text)]">
                {remoteStatus?.downloads_enabled ? 'ON' : 'OFF'}
              </span>
            </span>
            <span className="text-xs text-[var(--text-faint)]">
              Max download: {remoteStatus?.max_download_mb ?? 0} MB
            </span>
            {remoteStatus?.request_id && (
              <span className="rounded-full border border-[var(--border-color)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-faint)]">
                {remoteStatus.request_id}
              </span>
            )}
          </div>

          <div className="mb-5 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/45 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-[0.08em] text-[var(--text-faint)]">Rollout status</div>
                <div className="mt-1 flex items-center gap-2 text-sm text-[var(--text-dim)]">
                  {rolloutStatus?.readiness.ready ? (
                    <CheckCircle2 className="h-4 w-4 text-[var(--accent-hover)]" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                  )}
                  Stage:
                  <span className="font-semibold text-[var(--text)]">{rolloutStatus?.rollout_stage || 'unknown'}</span>
                  <span className="text-[var(--text-faint)]">env: {rolloutStatus?.env_name || 'n/a'}</span>
                </div>
              </div>

              <button
                onClick={() => {
                  void loadRemoteStatus(true);
                }}
                disabled={remoteRefreshing}
                className={cn(
                  'rounded-lg border border-[var(--border-color)] px-3 py-1.5 text-xs transition-all',
                  'text-[var(--text-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                Deep check
              </button>
            </div>

            <div className="grid gap-2 text-xs text-[var(--text-dim)] md:grid-cols-2">
              <div>
                Funnel status:{' '}
                <span className="font-medium text-[var(--text)]">{rolloutStatus?.funnel.status || 'unknown'}</span>
              </div>
              <div>
                Connected:{' '}
                <span className="font-medium text-[var(--text)]">{rolloutStatus?.funnel.connected ? 'yes' : 'no'}</span>
              </div>
              <div>
                Remote policy:{' '}
                <span className="font-medium text-[var(--text)]">
                  {rolloutStatus?.remote.allowlist_enforced ? 'allowlist' : 'blocklist'}
                </span>
              </div>
              <div>
                Remote enabled:{' '}
                <span className="font-medium text-[var(--text)]">
                  {rolloutStatus?.remote.control_enabled || rolloutStatus?.remote.downloads_enabled
                    ? 'yes'
                    : 'no'}
                </span>
              </div>
            </div>

            {rolloutStatus?.funnel.public_url && (
              <div className="mt-2 rounded-md border border-[var(--border-color)] bg-[var(--surface-2)] px-2 py-1 font-mono text-[11px] text-[var(--text-faint)]">
                {rolloutStatus.funnel.public_url}
              </div>
            )}

            {rolloutStatus && !rolloutStatus.readiness.ready && rolloutStatus.readiness.blockers.length > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-200/90">
                {rolloutStatus.readiness.blockers.map((blocker, idx) => (
                  <li key={`${blocker}-${idx}`}>{blocker}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="mb-5">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-[var(--text)]">
              <TerminalSquare className="h-4 w-4 text-[var(--accent-hover)]" />
              Run Remote Command
            </div>
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
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/55 p-3 text-xs whitespace-pre-wrap text-[var(--text-dim)]">
              {remoteOutput}
            </pre>
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-[var(--text)]">
              <FolderOpen className="h-4 w-4 text-[var(--accent-hover)]" />
              Remote Files
            </div>

            <div className="mb-2 flex flex-wrap gap-2">
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
                className="flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-dim)] hover:text-[var(--text)] disabled:opacity-50"
              >
                <ArrowLeft className="h-4 w-4" />
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
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-faint)]">
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

            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-2)]/55">
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

        <div className="mt-5 flex items-start gap-3 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent-soft)] p-4">
          <Shield className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--accent-hover)]" />
          <div>
            <p className="text-sm text-[var(--text-dim)]">
              Remote endpoints are protected by session auth and rollout stage policy.
            </p>
            <p className="mt-1 text-xs text-[var(--text-faint)]">
              If commands are denied, check deployment stage and remote feature flags.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
