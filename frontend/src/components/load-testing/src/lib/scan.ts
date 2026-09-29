import type { DiscoveredEndpoint, LoadPlan } from './types';

export const DEFAULT_PLAN: LoadPlan = {
  mode: 'per-endpoint',
  rate: 10,
  duration: '30s',
  warmup: null,
  expected_limit_rps: null,
};

/** Parses "Name: value" lines; returns the headers or the first offending line. */
export function parseHeaders(text: string): {
  headers: Record<string, string>;
  error: string | null;
} {
  const headers: Record<string, string> = {};
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const idx = line.indexOf(':');
    const name = idx > 0 ? line.slice(0, idx).trim() : '';
    if (!name || !/^[A-Za-z0-9!#$%&'*+.^_`|~-]+$/.test(name)) {
      return { headers: {}, error: `Invalid header line: "${line}" (expected "Name: value")` };
    }
    headers[name] = line.slice(idx + 1).trim();
  }
  return { headers, error: null };
}

export function splitList(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function isDefaultSelected(ep: DiscoveredEndpoint, includeUnsafe = false): boolean {
  return ep.in_scope && !ep.sensitive && (ep.safe || includeUnsafe);
}

export function endpointFlags(ep: DiscoveredEndpoint): string[] {
  const flags: string[] = [];
  if (!ep.in_scope) flags.push('out of scope');
  if (ep.sensitive) flags.push('auth-related');
  if (!ep.safe) flags.push('modifies data');
  if (ep.status !== null && ep.status >= 400) flags.push(`HTTP ${ep.status}`);
  if (ep.status === null) flags.push('no response');
  return flags;
}
