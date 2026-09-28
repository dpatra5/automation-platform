const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const decFmt = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});

type Num = number | null | undefined;

export const isNum = (v: Num): v is number => typeof v === 'number' && Number.isFinite(v);

export function formatInt(v: Num): string {
  return isNum(v) ? intFmt.format(v) : '—';
}

export function formatRps(v: Num): string {
  return isNum(v) ? decFmt.format(v) : '—';
}

export function formatMs(v: Num): string {
  if (!isNum(v)) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(2)} s`;
  return `${v < 10 ? v.toFixed(2) : v.toFixed(1)} ms`;
}

export function formatPct(ratio: Num, digits = 1): string {
  return isNum(ratio) ? `${(ratio * 100).toFixed(digits)}%` : '—';
}

export function formatDuration(seconds: Num): string {
  if (!isNum(seconds)) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${Number(seconds.toFixed(1))} s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(1)} ${units[i] ?? 'GB'}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Math.round((now - t) / 1000);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (Math.abs(diff) < 60) return rtf.format(-diff, 'second');
  if (Math.abs(diff) < 3600) return rtf.format(-Math.round(diff / 60), 'minute');
  if (Math.abs(diff) < 86400) return rtf.format(-Math.round(diff / 3600), 'hour');
  return rtf.format(-Math.round(diff / 86400), 'day');
}

export function humanize(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\brps\b/g, 'RPS')
    .replace(/\bpct\b/g, '%');
}
