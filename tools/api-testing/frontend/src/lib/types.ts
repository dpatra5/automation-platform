export const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] as const;
export type Method = (typeof METHODS)[number];
export type BodyMode = 'none' | 'json' | 'text' | 'xml' | 'form';
export type AuthType = 'none' | 'bearer' | 'basic' | 'api_key';
export type AssertionSource = 'status' | 'response_time' | 'header' | 'json' | 'body' | 'json_schema';
export type Operator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'exists'
  | 'not_exists'
  | 'lt'
  | 'lte'
  | 'gt'
  | 'gte'
  | 'matches'
  | 'type_is';
export type ExtractionSource = 'json' | 'header' | 'regex' | 'status';

export interface KeyValue {
  key: string;
  value: string;
  enabled: boolean;
}

export interface Variable extends KeyValue {
  secret: boolean;
}

export interface Body {
  mode: BodyMode;
  content: string;
  form: KeyValue[];
}

export interface Auth {
  type: AuthType;
  token: string;
  username: string;
  password: string;
  key: string;
  value: string;
  location: 'header' | 'query';
}

export interface Assertion {
  source: AssertionSource;
  property: string;
  operator: Operator;
  expected: string;
  enabled: boolean;
}

export interface Extraction {
  variable: string;
  source: ExtractionSource;
  property: string;
  enabled: boolean;
}

export interface RequestSettings {
  timeout_ms: number;
  follow_redirects: boolean;
  verify_tls: boolean;
}

export interface RequestSpec {
  method: Method;
  url: string;
  params: KeyValue[];
  headers: KeyValue[];
  body: Body;
  auth: Auth;
  assertions: Assertion[];
  extractions: Extraction[];
  settings: RequestSettings;
  description: string;
}

export interface RequestItemIn extends RequestSpec {
  name: string;
}

export interface RequestItem extends RequestItemIn {
  id: number;
  collection_id: number;
  position: number;
  updated_at: string;
}

export interface CollectionIn {
  name: string;
  description: string;
  variables: Variable[];
}

export interface CollectionSummary {
  id: number;
  name: string;
  description: string;
  request_count: number;
  updated_at: string;
}

export interface Collection extends CollectionIn {
  id: number;
  updated_at: string;
  requests: RequestItem[];
}

export interface EnvironmentIn {
  name: string;
  variables: Variable[];
}

export interface Environment extends EnvironmentIn {
  id: number;
  updated_at: string;
}

export interface ResolvedRequest {
  method: string;
  url: string;
  headers: [string, string][];
  body: string | null;
}

export interface ResponseData {
  status: number;
  reason: string;
  http_version: string;
  headers: [string, string][];
  body: string;
  body_truncated: boolean;
  is_binary: boolean;
  size_bytes: number;
  elapsed_ms: number;
  content_type: string;
}

export interface AssertionResult {
  assertion: Assertion;
  passed: boolean;
  actual: string | null;
  message: string;
}

export interface ExtractionResult {
  variable: string;
  value: string | null;
  ok: boolean;
  message: string;
}

export interface ExecutionResult {
  request: ResolvedRequest;
  response: ResponseData | null;
  error: string | null;
  assertions: AssertionResult[];
  extractions: ExtractionResult[];
  extracted: Record<string, string>;
  unresolved: string[];
  passed: boolean;
}

export interface ExecuteIn {
  request: RequestSpec;
  collection_id?: number | null;
  environment_id?: number | null;
  variables?: Record<string, string>;
}

export interface RunIn {
  collection_id: number;
  environment_id: number | null;
  request_ids: number[] | null;
  iterations: number;
  data: string;
  stop_on_failure: boolean;
  delay_ms: number;
}

export interface RunTotals {
  iterations: number;
  requests: number;
  passed: number;
  failed: number;
  errors: number;
  assertions_total: number;
  assertions_passed: number;
  assertions_failed: number;
  avg_response_ms: number | null;
  duration_ms: number;
}

export interface RunSummary {
  id: number;
  collection_id: number | null;
  collection_name: string;
  environment_name: string | null;
  status: 'passed' | 'failed';
  started_at: string;
  finished_at: string;
  totals: RunTotals;
}

export interface RunStep {
  iteration: number;
  request_id: number | null;
  request_name: string;
  result: ExecutionResult;
}

export interface RunDetail extends RunSummary {
  steps: RunStep[];
}

export type ImportFormat = 'auto' | 'curl' | 'openapi' | 'postman' | 'native';

export interface ImportOut {
  collection: CollectionSummary;
  format: string;
  request_count: number;
  warnings: string[];
}

export interface Health {
  status: string;
  version: string;
  auth_required: boolean;
}
