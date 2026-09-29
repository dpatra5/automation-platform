/**
 * The "Quick test" form model and its conversion to an lt config.
 * Output is YAML so users can switch to the editor and keep refining the plan.
 */

export type LoadPattern = 'users' | 'rps';
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface QuickStep {
  name: string;
  method: HttpMethod;
  path: string;
  body: string;
  expectStatus: string;
  maxMs: string;
  bodyContains: string;
  extractVar: string;
  extractPath: string;
}

export interface QuickPlan {
  name: string;
  baseUrl: string;
  headers: string;
  pattern: LoadPattern;
  users: string;
  rampUp: string;
  duration: string;
  thinkTime: string;
  iterations: string;
  rps: string;
  maxRps: string;
  p95Ms: string;
  errorRatePct: string;
  steps: QuickStep[];
}

export const emptyStep = (): QuickStep => ({
  name: '',
  method: 'GET',
  path: '/',
  body: '',
  expectStatus: '',
  maxMs: '',
  bodyContains: '',
  extractVar: '',
  extractPath: '',
});

export const DEFAULT_PLAN: QuickPlan = {
  name: 'quick-test',
  baseUrl: 'http://127.0.0.1:8080',
  headers: '',
  pattern: 'users',
  users: '10',
  rampUp: '10s',
  duration: '30s',
  thinkTime: '1s',
  iterations: '',
  rps: '50',
  maxRps: '',
  p95Ms: '500',
  errorRatePct: '1',
  steps: [
    {
      ...emptyStep(),
      name: 'login',
      method: 'POST',
      path: '/app/login',
      body: '{"username": "user{{$vu}}", "password": "demo"}',
      extractVar: 'token',
      extractPath: '$.token',
    },
    {
      ...emptyStep(),
      name: 'products',
      path: '/app/products',
      maxMs: '500',
      bodyContains: 'items',
    },
  ],
};

const num = (v: string): number | undefined => {
  const n = Number(v.trim());
  return v.trim() !== '' && Number.isFinite(n) ? n : undefined;
};

function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const i = line.indexOf(':');
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

function parseBody(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

/** Build the config object; empty optional fields are omitted. */
export function buildConfig(plan: QuickPlan): Record<string, Json> {
  const closed = plan.pattern === 'users';
  const routes = plan.steps.map((s, i) => {
    const route: Record<string, Json> = {
      name: s.name.trim() || `step ${i + 1}`,
      method: s.method,
      path: s.path.trim() || '/',
    };
    const body = parseBody(s.body);
    if (body !== undefined) route.body = body as Json;
    const codes = s.expectStatus
      .split(/[\s,]+/)
      .map((c) => num(c))
      .filter((c): c is number => c !== undefined);
    if (codes.length) route.expect_status = codes;
    const assertions: Record<string, Json> = {};
    const maxMs = num(s.maxMs);
    if (maxMs !== undefined) assertions.max_ms = maxMs;
    if (s.bodyContains.trim()) assertions.body_contains = [s.bodyContains.trim()];
    if (Object.keys(assertions).length) route.assertions = assertions;
    if (closed && s.extractVar.trim() && s.extractPath.trim()) {
      route.extract = { [s.extractVar.trim()]: s.extractPath.trim() };
    }
    return route;
  });

  const duration = plan.duration.trim() || '30s';
  const model: Record<string, Json> = closed
    ? { type: 'closed', users: num(plan.users) ?? 1, ramp_up: plan.rampUp.trim() || '0s', duration }
    : { workers: 4, profile: [{ duration, rate: num(plan.rps) ?? 1 }] };
  if (closed) {
    if (plan.thinkTime.trim()) model.think_time = plan.thinkTime.trim();
    const iterations = num(plan.iterations);
    if (iterations !== undefined) model.iterations = iterations;
    const maxRps = num(plan.maxRps);
    if (maxRps !== undefined) model.max_rps = maxRps;
  }

  const thresholds: Record<string, Json> = {};
  const p95 = num(plan.p95Ms);
  if (p95 !== undefined) thresholds.p95_ms = p95;
  const errPct = num(plan.errorRatePct);
  if (errPct !== undefined) thresholds.error_rate = errPct / 100;

  const host = hostOf(plan.baseUrl.trim());
  const cfg: Record<string, Json> = {
    version: 1,
    name: plan.name.trim() || 'quick-test',
    base_url: plan.baseUrl.trim(),
    safety: { allowlist: host ? [host] : [] },
    model,
  };
  const headers = parseHeaders(plan.headers);
  if (Object.keys(headers).length) cfg.default_headers = headers;
  cfg.routes = routes;
  if (Object.keys(thresholds).length) cfg.thresholds = thresholds;
  return cfg;
}

const PLAIN_KEY = /^[A-Za-z_][\w -]*$/;

function scalar(v: Json): string {
  if (typeof v === 'string') return JSON.stringify(v);
  return String(v);
}

function isScalar(v: Json): boolean {
  return v === null || typeof v !== 'object';
}

/** Minimal YAML writer for plain JSON data (strings are always double-quoted, which is valid YAML). */
export function toYaml(value: Json, indent = 0): string {
  const pad = ' '.repeat(indent);
  if (Array.isArray(value)) {
    if (value.every(isScalar)) return `[${value.map(scalar).join(', ')}]`;
    return value
      .map((item) => {
        const text = toYaml(item, indent + 2);
        return `\n${pad}- ${isScalar(item) ? text : text.trimStart()}`;
      })
      .join('');
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length === 0) return '{}';
    return entries
      .map(([k, v]) => {
        const key = PLAIN_KEY.test(k) && !k.endsWith(' ') ? k : JSON.stringify(k);
        if (isScalar(v) || (Array.isArray(v) && v.every(isScalar)) || JSON.stringify(v) === '{}') {
          return `\n${pad}${key}: ${toYaml(v, indent + 2)}`;
        }
        return `\n${pad}${key}:${toYaml(v, indent + 2)}`;
      })
      .join('');
  }
  return scalar(value);
}

export function buildYaml(plan: QuickPlan): string {
  return `${toYaml(buildConfig(plan)).trimStart()}\n`;
}
