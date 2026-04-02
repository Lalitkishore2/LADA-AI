import { authFetch } from '@/lib/lada-api';

export interface RemoteStatus {
  enabled: boolean;
  downloads_enabled: boolean;
  dangerous_enabled: boolean;
  allowed_roots: string[];
  max_download_mb: number;
  command_rpm?: number;
  files_rpm?: number;
  download_rpm?: number;
  current_path?: string;
  request_id?: string;
}

export interface RemoteEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
}

export interface RemoteBreadcrumb {
  name: string;
  path: string;
  is_root?: boolean;
}

export interface RemoteFilesResult {
  path: string;
  parent: string;
  entries: RemoteEntry[];
  breadcrumbs: RemoteBreadcrumb[];
}

export interface RemoteCommandResult {
  response: string;
  engine: string;
  request_id: string;
}

export interface RemoteDownloadResult {
  filename: string;
  blob: Blob;
}

export interface RolloutRemoteStatus {
  control_enabled: boolean;
  downloads_enabled: boolean;
  dangerous_enabled: boolean;
  allowlist_enforced: boolean;
}

export interface RolloutFunnelStatus {
  enabled: boolean;
  binary_found: boolean;
  deep_checked: boolean;
  status: string;
  connected: boolean;
  dns_name: string;
  public_url: string;
}

export interface RolloutReadinessStatus {
  ready: boolean;
  blockers: string[];
}

export interface RolloutStatus {
  request_id: string;
  env_name: string;
  rollout_stage: string;
  remote: RolloutRemoteStatus;
  funnel: RolloutFunnelStatus;
  readiness: RolloutReadinessStatus;
}

export class RemoteApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'RemoteApiError';
    this.status = status;
  }
}

async function parseJsonSafe(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function toError(payload: Record<string, unknown>, fallback: string, status: number): RemoteApiError {
  return new RemoteApiError(String(payload.detail || payload.error || fallback), status);
}

export async function fetchRemoteStatus(): Promise<RemoteStatus> {
  const response = await authFetch('/remote/status');
  const payload = await parseJsonSafe(response);
  if (!response.ok) {
    throw toError(payload, 'Could not load remote status', response.status);
  }

  return {
    enabled: Boolean(payload.enabled),
    downloads_enabled: Boolean(payload.downloads_enabled),
    dangerous_enabled: Boolean(payload.dangerous_enabled),
    allowed_roots: Array.isArray(payload.allowed_roots)
      ? payload.allowed_roots.map((item) => String(item))
      : [],
    max_download_mb: Number(payload.max_download_mb || 0),
    command_rpm: Number(payload.command_rpm || 0),
    files_rpm: Number(payload.files_rpm || 0),
    download_rpm: Number(payload.download_rpm || 0),
    current_path: String(payload.current_path || ''),
    request_id: String(payload.request_id || ''),
  };
}

export async function fetchRolloutStatus(deepCheck = false): Promise<RolloutStatus> {
  const query = new URLSearchParams({ deep_check: deepCheck ? 'true' : 'false' });
  const response = await authFetch(`/rollout/status?${query.toString()}`);
  const payload = await parseJsonSafe(response);
  if (!response.ok) {
    throw toError(payload, 'Could not load rollout status', response.status);
  }

  const remotePayload = (payload.remote || {}) as Record<string, unknown>;
  const funnelPayload = (payload.funnel || {}) as Record<string, unknown>;
  const readinessPayload = (payload.readiness || {}) as Record<string, unknown>;

  return {
    request_id: String(payload.request_id || ''),
    env_name: String(payload.env_name || ''),
    rollout_stage: String(payload.rollout_stage || ''),
    remote: {
      control_enabled: Boolean(remotePayload.control_enabled),
      downloads_enabled: Boolean(remotePayload.downloads_enabled),
      dangerous_enabled: Boolean(remotePayload.dangerous_enabled),
      allowlist_enforced: Boolean(remotePayload.allowlist_enforced),
    },
    funnel: {
      enabled: Boolean(funnelPayload.enabled),
      binary_found: Boolean(funnelPayload.binary_found),
      deep_checked: Boolean(funnelPayload.deep_checked),
      status: String(funnelPayload.status || 'unknown'),
      connected: Boolean(funnelPayload.connected),
      dns_name: String(funnelPayload.dns_name || ''),
      public_url: String(funnelPayload.public_url || ''),
    },
    readiness: {
      ready: Boolean(readinessPayload.ready),
      blockers: Array.isArray(readinessPayload.blockers)
        ? readinessPayload.blockers.map((item) => String(item))
        : [],
    },
  };
}

export async function fetchRemoteFiles(path: string, page = 1, pageSize = 100): Promise<RemoteFilesResult> {
  const query = new URLSearchParams({
    path,
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await authFetch(`/remote/files?${query.toString()}`);
  const payload = await parseJsonSafe(response);
  if (!response.ok) {
    throw toError(payload, 'Could not load remote files', response.status);
  }

  const entries = Array.isArray(payload.entries) ? (payload.entries as RemoteEntry[]) : [];
  const breadcrumbs = Array.isArray(payload.breadcrumbs)
    ? (payload.breadcrumbs as RemoteBreadcrumb[])
    : [];

  return {
    path: String(payload.path || path),
    parent: String(payload.parent || ''),
    entries,
    breadcrumbs,
  };
}

export async function executeRemoteCommand(command: string): Promise<RemoteCommandResult> {
  const response = await authFetch('/remote/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });
  const payload = await parseJsonSafe(response);
  if (!response.ok) {
    throw toError(payload, 'Remote command failed', response.status);
  }

  return {
    response: String(payload.response || 'Command executed.'),
    engine: String(payload.engine || 'unknown'),
    request_id: String(payload.request_id || ''),
  };
}

export async function downloadRemoteBinary(path: string): Promise<RemoteDownloadResult> {
  const response = await authFetch(`/remote/download?path=${encodeURIComponent(path)}`);
  if (!response.ok) {
    const payload = await parseJsonSafe(response);
    throw toError(payload, 'Download failed', response.status);
  }

  const contentDisposition = response.headers.get('content-disposition') || '';
  const match = contentDisposition.match(/filename="?([^";]+)"?/i);
  const filename = match ? match[1] : path.split(/[\\/]/).pop() || 'download.bin';

  return {
    filename,
    blob: await response.blob(),
  };
}
