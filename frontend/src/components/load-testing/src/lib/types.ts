// Mirrors backend/src/lt/api/schemas.py and the artifact JSON written by the engine.

export type RunStatus = 'running' | 'stopping' | 'completed' | 'interrupted' | 'failed';

export interface Health {
  status: 'ok';
  version: string;
  auth_required: boolean;
}

export interface Overrides {
  rps?: number | null;
  duration?: string | null;
  workers?: number | null;
  processes?: number | null;
  max_rps_cap?: number | null;
  http2?: boolean | null;
  connections?: number | null;
  streams?: number | null;
  concurrency?: number | null;
  events_sample_rate?: number | null;
}

export interface ConfigRequest {
  yaml: string;
  overrides?: Overrides;
}

export interface ConfigSummary {
  name: string | null;
  base_url: string;
  host: string;
  peak_rps: number;
  effective_cap: number;
  duration_s: number;
  expected_requests: number;
  processes: number;
  workers: number;
  concurrency_per_process: number;
  http2: boolean;
  profile: { duration_s: number; rate: number; end_rate: number | null; name: string | null }[];
  routes: { name: string; method: string; path: string; weight: number; tenant: string | null }[];
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: ConfigSummary | null;
}

export interface Totals {
  attempted: number;
  accepted: number;
  '429': number;
  errors: number;
  dropped?: number;
}

export interface LatencySummary {
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  mean: number | null;
  count?: number;
  [key: string]: number | null | undefined;
}

export interface RunSummary {
  run_id: string;
  name: string | null;
  base_url: string;
  started_at: string;
  finished_at: string;
  interrupted: boolean;
  duration_s: number;
  totals: Totals;
  means: Record<'attempted_rps' | 'accepted_rps' | '429_rps' | 'error_rps', number>;
  ratios: Record<'accepted' | '429' | 'errors', number>;
  latency_ms: LatencySummary;
  scheduler: {
    rate_error_pct: number;
    mean_abs_window_error_pct: number;
    lag_p99_ms: number | null;
  };
  status_codes: Record<string, number>;
}

export interface RunMetrics {
  planned_duration_s: number;
  planned_events: number;
  latency_by_family_ms: Record<string, LatencySummary>;
  error_types: Record<string, number>;
  routes: Record<string, Record<string, number>>;
  headers: Record<string, unknown>;
  client: Record<string, number | boolean>;
  execution: Record<string, number>;
  [key: string]: unknown;
}

export interface RunListItem {
  run_id: string;
  status: RunStatus;
  name: string | null;
  base_url: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  totals: Totals | null;
  means: RunSummary['means'] | null;
  ratios: RunSummary['ratios'] | null;
  latency_ms: LatencySummary | null;
  analysis_pass: boolean | null;
}

export interface Artifact {
  name: string;
  size: number;
}

export interface AnalysisSection {
  applicable?: boolean;
  pass?: boolean | null;
  [key: string]: unknown;
}

export interface Analysis {
  run_id: string;
  pass: boolean;
  checks: Record<string, boolean | null>;
  settings: Record<string, number | null>;
  validity: { pass: boolean; reasons: string[]; scheduler_lag_p99_ms: number | null };
  sustained: AnalysisSection;
  burst: AnalysisSection;
  step: AnalysisSection & {
    capacity_curve?: { asked: number; accepted: number; '429_rate': number }[];
    estimated_capacity_rps?: number | null;
  };
  fairness: AnalysisSection & { tenants?: Record<string, Record<string, number>> };
  headers: AnalysisSection;
  window_semantics: { classification: string; confidence: number; rationale: string };
}

export interface RunDetail {
  run_id: string;
  status: RunStatus;
  error: string | null;
  progress: { elapsed_s: number; planned_duration_s: number | null } | null;
  config: Record<string, unknown> | null;
  summary: RunSummary | null;
  metrics: RunMetrics | null;
  analysis: Analysis | null;
  artifacts: Artifact[];
}

export interface MetricsRow {
  second: number;
  attempted_rps: number | null;
  accepted_rps: number | null;
  '429_rps': number | null;
  error_rps: number | null;
  p50_ms: number | null;
  p90_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  dropped: number | null;
}

export interface LivePoint {
  second: number;
  attempted: number;
  accepted: number;
  rate_limited: number;
  errors: number;
}

export interface RouteRow {
  second: number;
  route: string;
  attempted: number;
  accepted: number;
  '429': number;
  errors: number;
}

export interface Timeseries {
  metrics: MetricsRow[];
  live: LivePoint[];
  routes: RouteRow[];
}

export interface LogRecord {
  ts?: string;
  level?: string;
  msg?: string;
  [key: string]: unknown;
}

export interface AnalyzeRequest {
  expected_limit_rps?: number | null;
  expected_burst?: number | null;
  tolerance?: number | null;
  fairness_threshold?: number | null;
}

export interface Example {
  name: string;
  filename: string;
  yaml: string;
}

export type DemoAlgo = 'token-bucket' | 'fixed-window' | 'sliding-window';
export type DemoScope = 'global' | 'per-key';

export interface DemoServerRequest {
  port: number;
  rate: number;
  burst: number | null;
  window: string;
  algo: DemoAlgo;
  scope: DemoScope;
  key_header: string;
  latency_ms: number;
}

export interface DemoServerState {
  running: boolean;
  base_url: string | null;
  settings: DemoServerRequest | null;
}

export type DemoStats = Record<string, { allowed: number; denied: number }>;

export type ScanStatus =
  'discovering' | 'discovered' | 'running' | 'completed' | 'cancelled' | 'failed';
export type ScanItemStatus =
  'pending' | 'running' | 'completed' | 'interrupted' | 'failed' | 'skipped' | 'cancelled';

export interface DiscoveryOptions {
  url: string;
  max_pages?: number;
  max_depth?: number;
  wait_ms?: number;
  scope?: string[];
  headers?: Record<string, string>;
  ignore_https_errors?: boolean;
}

export interface LoadPlan {
  mode: 'per-endpoint' | 'combined';
  rate: number;
  duration: string;
  warmup?: string | null;
  expected_limit_rps?: number | null;
}

export interface ScanRequest {
  discovery: DiscoveryOptions;
  plan: LoadPlan;
  auto_run: boolean;
  include_unsafe_methods: boolean;
}

export interface DiscoveredEndpoint {
  id: string;
  method: string;
  base_url: string;
  path: string;
  template: string;
  resource_type: string;
  in_scope: boolean;
  sensitive: boolean;
  safe: boolean;
  count: number;
  status: number | null;
  content_type: string | null;
  has_body: boolean;
  pages: string[];
}

export interface ScanItem {
  name: string;
  endpoint_ids: string[];
  status: ScanItemStatus;
  run_id: string | null;
  error: string | null;
  accepted_rps: number | null;
  ratio_429: number | null;
  p99_ms: number | null;
  analysis_pass: boolean | null;
}

export interface ScanSummary {
  id: string;
  url: string;
  status: ScanStatus;
  created_at: string;
  error: string | null;
  endpoints_found: number;
  items_total: number;
  items_done: number;
}

export interface ScanDetail extends ScanSummary {
  options: {
    max_pages: number;
    max_depth: number;
    wait_ms: number;
    scope: string[];
    header_names: string[];
  };
  pages: string[];
  discovery_errors: string[];
  out_of_scope_hosts: Record<string, number>;
  endpoints: DiscoveredEndpoint[];
  plan: LoadPlan | null;
  items: ScanItem[];
}
