import type {
  Analysis,
  AnalyzeRequest,
  ConfigRequest,
  DemoServerRequest,
  DemoServerState,
  DemoStats,
  Example,
  Health,
  JmxImportResult,
  LoadPlan,
  LogRecord,
  RunDetail,
  RunListItem,
  ScanDetail,
  ScanRequest,
  ScanSummary,
  Timeseries,
  ValidationResult,
} from './types';

const BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '';
const TOKEN_KEY = 'lt.apiToken';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// sessionStorage limits token exposure to the current tab's lifetime.
export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: unknown) => {
          if (d && typeof d === 'object' && 'msg' in d) {
            const { msg, loc } = d as { msg: unknown; loc?: unknown };
            const where = Array.isArray(loc) ? loc.filter((p) => p !== 'body').join('.') : '';
            return where ? `${where}: ${String(msg)}` : String(msg);
          }
          return JSON.stringify(d);
        })
        .join('\n');
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  const token = tokenStore.get();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}/api/v1${path}`, { ...init, headers });
  } catch (err) {
    if (init.signal?.aborted) throw err;
    throw new ApiError(0, 'Cannot reach the lt API. Is `lt serve` running?');
  }
  if (res.status === 401) unauthorizedListeners.forEach((fn) => fn());
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

const runPath = (id: string) => `/runs/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<Health>('/health'),
  examples: () => request<Example[]>('/examples'),
  importJmx: (jmx: string) => post<JmxImportResult>('/configs/import/jmx', { jmx }),
  validate: (req: ConfigRequest, signal?: AbortSignal) =>
    request<ValidationResult>('/configs/validate', {
      method: 'POST',
      body: JSON.stringify(req),
      signal: signal ?? null,
    }),
  listRuns: () => request<RunListItem[]>('/runs'),
  startRun: (req: ConfigRequest) => post<RunDetail>('/runs', req),
  getRun: (id: string) => request<RunDetail>(runPath(id)),
  timeseries: (id: string) => request<Timeseries>(`${runPath(id)}/timeseries`),
  logs: (id: string, tail = 200) => request<LogRecord[]>(`${runPath(id)}/logs?tail=${tail}`),
  stopRun: (id: string, force = false) => post<RunDetail>(`${runPath(id)}/stop`, { force }),
  analyze: (id: string, req: AnalyzeRequest) => post<Analysis>(`${runPath(id)}/analyze`, req),
  deleteRun: (id: string) => request<undefined>(runPath(id), { method: 'DELETE' }),
  demoState: () => request<DemoServerState>('/demo-server'),
  demoStart: (req: DemoServerRequest) => post<DemoServerState>('/demo-server', req),
  demoStop: () => request<undefined>('/demo-server', { method: 'DELETE' }),
  demoStats: () => request<DemoStats>('/demo-server/stats'),
  listScans: () => request<ScanSummary[]>('/scans'),
  startScan: (req: ScanRequest) => post<ScanDetail>('/scans', req),
  getScan: (id: string) => request<ScanDetail>(`/scans/${encodeURIComponent(id)}`),
  runScan: (id: string, endpointIds: string[], plan: LoadPlan) =>
    post<ScanDetail>(`/scans/${encodeURIComponent(id)}/run`, { endpoint_ids: endpointIds, plan }),
  cancelScan: (id: string) => post<ScanDetail>(`/scans/${encodeURIComponent(id)}/cancel`),
  deleteScan: (id: string) =>
    request<undefined>(`/scans/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** Downloads via fetch so the bearer token is sent; plain links cannot carry it. */
  async downloadArtifact(id: string, name: string): Promise<void> {
    const headers = new Headers();
    const token = tokenStore.get();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const res = await fetch(`${BASE}/api/v1${runPath(id)}/artifacts/${encodeURIComponent(name)}`, {
      headers,
    });
    if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status})`);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = `${id}-${name}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
