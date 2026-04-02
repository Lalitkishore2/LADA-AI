const TOKEN_STORAGE_KEY = 'lada_auth_token';
const LEGACY_TOKEN_STORAGE_KEY = 'lada_token';

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export function getApiBaseUrl(): string {
  const envBase = process.env.NEXT_PUBLIC_LADA_API_BASE_URL;
  if (envBase && envBase.trim()) {
    return trimTrailingSlash(envBase.trim());
  }

  if (typeof window !== 'undefined') {
    if (window.location.port === '3000') {
      return `${window.location.protocol}//${window.location.hostname}:5000`;
    }
    return trimTrailingSlash(window.location.origin);
  }

  return 'http://127.0.0.1:5000';
}

export function createRequestId(prefix = 'web'): string {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase() || 'web';
  const rand = Math.random().toString(36).slice(2, 10);
  return `${safePrefix}-${Date.now()}-${rand}`;
}

export function getStoredAuthToken(): string {
  if (typeof window === 'undefined') return '';
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) return token;

  const legacy = window.localStorage.getItem(LEGACY_TOKEN_STORAGE_KEY);
  if (legacy) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, legacy);
    window.localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
    return legacy;
  }

  return '';
}

export function setStoredAuthToken(token: string): void {
  if (typeof window === 'undefined') return;
  if (!token) {
    clearStoredAuthToken();
    return;
  }
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredAuthToken(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
}

function toAbsoluteUrl(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalized}`;
}

async function readJsonSafe(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export async function loginSession(password: string): Promise<string> {
  const response = await fetch(toAbsoluteUrl('/auth/login'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': createRequestId('http'),
    },
    body: JSON.stringify({ password }),
  });

  const payload = await readJsonSafe(response);
  if (!response.ok) {
    const detail = String(payload.detail || payload.error || 'Login failed');
    throw new Error(detail);
  }

  const token = String(payload.token || '');
  if (!token) {
    throw new Error('Login succeeded but no token was returned.');
  }

  setStoredAuthToken(token);
  return token;
}

export async function checkSessionToken(token?: string): Promise<boolean> {
  const candidate = token || getStoredAuthToken();
  if (!candidate) return false;

  const response = await fetch(toAbsoluteUrl('/auth/check'), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${candidate}`,
      'X-Request-ID': createRequestId('http'),
    },
  });

  if (!response.ok) {
    clearStoredAuthToken();
    return false;
  }

  return true;
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getStoredAuthToken();
  if (!token) {
    throw new Error('You are not authenticated. Please log in.');
  }

  const headers = new Headers(init.headers || {});
  headers.set('Authorization', `Bearer ${token}`);
  if (!headers.has('X-Request-ID')) {
    headers.set('X-Request-ID', createRequestId('http'));
  }

  return fetch(toAbsoluteUrl(path), {
    ...init,
    headers,
  });
}
