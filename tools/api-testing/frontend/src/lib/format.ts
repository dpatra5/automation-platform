export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatDate(iso: string): string {
  // Backend timestamps from SQLite may lack a zone; they are always UTC.
  const hasZone = /[zZ]|[+-]\d\d:?\d\d$/.test(iso);
  return new Date(hasZone ? iso : `${iso}Z`).toLocaleString();
}

export function statusTone(status: number | undefined): string {
  if (status === undefined) return 'bg-slate-100 text-slate-600';
  if (status < 300) return 'bg-emerald-100 text-emerald-700';
  if (status < 400) return 'bg-sky-100 text-sky-700';
  if (status < 500) return 'bg-amber-100 text-amber-800';
  return 'bg-rose-100 text-rose-700';
}

export const METHOD_COLORS: Record<string, string> = {
  GET: 'text-emerald-600',
  POST: 'text-amber-600',
  PUT: 'text-sky-600',
  PATCH: 'text-violet-600',
  DELETE: 'text-rose-600',
  HEAD: 'text-slate-500',
  OPTIONS: 'text-slate-500',
};

export function prettyBody(body: string, contentType: string): string {
  if (!/json/i.test(contentType) && !/^\s*[[{]/.test(body)) return body;
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}
