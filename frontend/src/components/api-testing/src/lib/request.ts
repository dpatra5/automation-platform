import type { Assertion, Auth, Body, Extraction, KeyValue, RequestSpec, Variable } from './types';

export const emptyKv = (): KeyValue => ({ key: '', value: '', enabled: true });
export const emptyVariable = (): Variable => ({ key: '', value: '', enabled: true, secret: false });
export const emptyBody = (): Body => ({ mode: 'none', content: '', form: [] });
export const emptyAuth = (): Auth => ({
  type: 'none',
  token: '',
  username: '',
  password: '',
  key: '',
  value: '',
  location: 'header',
});
export const emptyAssertion = (overrides: Partial<Assertion> = {}): Assertion => ({
  source: 'status',
  property: '',
  operator: 'equals',
  expected: '200',
  enabled: true,
  ...overrides,
});
export const emptyExtraction = (): Extraction => ({ variable: '', source: 'json', property: '$.', enabled: true });

export const newRequestSpec = (): RequestSpec => ({
  method: 'GET',
  url: '{{baseUrl}}/',
  params: [],
  headers: [],
  body: emptyBody(),
  auth: emptyAuth(),
  assertions: [emptyAssertion()],
  extractions: [],
  settings: { timeout_ms: 30000, follow_redirects: true, verify_tls: true },
  description: '',
});

export function specOf<T extends RequestSpec>(item: T): RequestSpec {
  const { method, url, params, headers, body, auth, assertions, extractions, settings, description } = item;
  return { method, url, params, headers, body, auth, assertions, extractions, settings, description };
}

const shellQuote = (value: string) => `'${value.replace(/'/g, `'\\''`)}'`;

/** A bash cURL command for the (unresolved) request, for sharing or running elsewhere. */
export function toCurl(spec: RequestSpec): string {
  const query = spec.params
    .filter((p) => p.enabled && p.key.trim())
    .map((p) => `${encodeURIComponent(p.key)}=${encodeURIComponent(p.value)}`);
  const headers = spec.headers.filter((h) => h.enabled && h.key.trim()).map((h) => [h.key, h.value] as const);
  const has = (name: string) => headers.some(([k]) => k.toLowerCase() === name);
  const auth = spec.auth;
  const extra: string[] = [];
  const authHeaders: (readonly [string, string])[] = [];
  if (auth.type === 'bearer') authHeaders.push(['Authorization', `Bearer ${auth.token}`]);
  if (auth.type === 'basic') extra.push(`-u ${shellQuote(`${auth.username}:${auth.password}`)}`);
  if (auth.type === 'api_key' && auth.key) {
    if (auth.location === 'header') authHeaders.push([auth.key, auth.value]);
    else query.push(`${encodeURIComponent(auth.key)}=${encodeURIComponent(auth.value)}`);
  }
  let url = spec.url;
  if (query.length) url += (url.includes('?') ? '&' : '?') + query.join('&');

  const parts = [`curl -X ${spec.method} ${shellQuote(url)}`];
  for (const [k, v] of [...headers, ...authHeaders]) parts.push(`-H ${shellQuote(`${k}: ${v}`)}`);
  const body = spec.body;
  const contentType = { json: 'application/json', xml: 'application/xml', text: 'text/plain', form: '', none: '' }[
    body.mode
  ];
  if (contentType && !has('content-type')) parts.push(`-H ${shellQuote(`Content-Type: ${contentType}`)}`);
  if (body.mode === 'form') {
    for (const f of body.form.filter((f) => f.enabled && f.key.trim()))
      parts.push(`--data-urlencode ${shellQuote(`${f.key}=${f.value}`)}`);
  } else if (body.mode !== 'none') {
    parts.push(`--data-raw ${shellQuote(body.content)}`);
  }
  if (!spec.settings.verify_tls) extra.push('-k');
  if (spec.settings.follow_redirects) extra.push('-L');
  return [...parts, ...extra].join(' \\\n  ');
}

type Schema = Record<string, unknown>;

/** Infer a strict-but-reasonable JSON Schema from an example response. */
export function inferSchema(value: unknown, depth = 0): Schema {
  if (depth > 10) return {};
  if (value === null) return { type: 'null' };
  if (Array.isArray(value)) {
    const first = value[0];
    return first === undefined ? { type: 'array' } : { type: 'array', items: inferSchema(first, depth + 1) };
  }
  switch (typeof value) {
    case 'string':
      return { type: 'string' };
    case 'number':
      return { type: Number.isInteger(value) ? 'integer' : 'number' };
    case 'boolean':
      return { type: 'boolean' };
    case 'object': {
      const entries = Object.entries(value as Record<string, unknown>);
      return {
        type: 'object',
        required: entries.map(([k]) => k),
        properties: Object.fromEntries(entries.map(([k, v]) => [k, inferSchema(v, depth + 1)])),
      };
    }
    default:
      return {};
  }
}

export function tryParseJson(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}
