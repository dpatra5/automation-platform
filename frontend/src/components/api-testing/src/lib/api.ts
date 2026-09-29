import type {
  Collection,
  CollectionIn,
  CollectionSummary,
  Environment,
  EnvironmentIn,
  ExecuteIn,
  ExecutionResult,
  Health,
  ImportFormat,
  ImportOut,
  RequestItem,
  RequestItemIn,
  RunDetail,
  RunIn,
  RunSummary,
} from './types';

const TOKEN_KEY = 'apit.apiToken';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// sessionStorage keeps the token scoped to this tab's lifetime.
export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

const unauthorizedListeners = new Set<() => void>();
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body as { detail: unknown };
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
        .join('; ');
    }
  }
  return fallback;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const token = tokenStore.get();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (res.status === 401) unauthorizedListeners.forEach((l) => l());
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

async function download(path: string, fallbackName: string): Promise<void> {
  const res = await send(path);
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  health: () => request<Health>('/health'),

  listCollections: () => request<CollectionSummary[]>('/collections'),
  getCollection: (id: number) => request<Collection>(`/collections/${id}`),
  createCollection: (body: CollectionIn) => request<Collection>('/collections', json('POST', body)),
  updateCollection: (id: number, body: CollectionIn) => request<Collection>(`/collections/${id}`, json('PUT', body)),
  deleteCollection: (id: number) => request<void>(`/collections/${id}`, { method: 'DELETE' }),
  exportCollection: (id: number) => download(`/collections/${id}/export`, 'collection.apitest.json'),
  reorder: (id: number, requestIds: number[]) =>
    request<Collection>(`/collections/${id}/order`, json('PUT', { request_ids: requestIds })),

  createRequest: (collectionId: number, body: RequestItemIn) =>
    request<RequestItem>(`/collections/${collectionId}/requests`, json('POST', body)),
  updateRequest: (id: number, body: RequestItemIn) => request<RequestItem>(`/requests/${id}`, json('PUT', body)),
  deleteRequest: (id: number) => request<void>(`/requests/${id}`, { method: 'DELETE' }),
  duplicateRequest: (id: number) => request<RequestItem>(`/requests/${id}/duplicate`, { method: 'POST' }),

  listEnvironments: () => request<Environment[]>('/environments'),
  createEnvironment: (body: EnvironmentIn) => request<Environment>('/environments', json('POST', body)),
  updateEnvironment: (id: number, body: EnvironmentIn) =>
    request<Environment>(`/environments/${id}`, json('PUT', body)),
  deleteEnvironment: (id: number) => request<void>(`/environments/${id}`, { method: 'DELETE' }),

  execute: (body: ExecuteIn) => request<ExecutionResult>('/execute', json('POST', body)),

  createRun: (body: RunIn) => request<RunDetail>('/runs', json('POST', body)),
  listRuns: (collectionId?: number) =>
    request<RunSummary[]>(collectionId ? `/runs?collection_id=${collectionId}` : '/runs'),
  getRun: (id: number) => request<RunDetail>(`/runs/${id}`),
  deleteRun: (id: number) => request<void>(`/runs/${id}`, { method: 'DELETE' }),
  downloadReport: (id: number, format: 'json' | 'junit' | 'html') =>
    download(`/runs/${id}/report?format=${format}`, `run-${id}.${format === 'junit' ? 'xml' : format}`),

  importCollection: (body: { content: string; format: ImportFormat; name?: string }) =>
    request<ImportOut>('/import', json('POST', body)),
};
