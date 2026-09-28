export type Action =
  | "navigate"
  | "reload"
  | "go_back"
  | "go_forward"
  | "click"
  | "dblclick"
  | "right_click"
  | "hover"
  | "drag"
  | "scroll"
  | "fill"
  | "type"
  | "press_key"
  | "select"
  | "check"
  | "uncheck"
  | "upload"
  | "wait"
  | "wait_for_selector"
  | "wait_for_url"
  | "switch_tab"
  | "assert";

export type SelectorStrategy = "test_id" | "role" | "text" | "css" | "xpath";
export type RunStatus = "pending" | "running" | "passed" | "failed" | "error";
export type EvidenceType =
  | "screenshot"
  | "video"
  | "trace"
  | "console_log"
  | "network_log"
  | "report";
export type JiraSyncStatus = "skipped" | "posted" | "failed";

export interface Project {
  id: string;
  name: string;
  base_url: string;
  description: string | null;
  /** Optional Jira Test Execution issue, e.g. JGQE-23122. */
  jira_key: string | null;
  jira_browse_url?: string | null;
  created_at: string;
  test_case_count?: number;
  last_run_status?: RunStatus | null;
}

/** One entry of the backend's check catalogue, as the pickers render it. */
export interface AssertionOption {
  key: string;
  label: string;
  group: string;
  hint: string;
  needs_selector: boolean;
  needs_expected: boolean;
  expected_label: string;
  param_label: string;
  expected_is_number: boolean;
}

export interface JiraStatus {
  configured: boolean;
  url: string;
  required_issue_type: string;
  attaches_evidence: boolean;
}

export interface JiraIssueRef {
  key: string;
  summary: string;
  issue_type: string;
  status: string;
  url: string;
}

export interface JiraWhoami {
  account: string;
  display_name: string;
  email: string;
  /** Which authentication scheme Jira actually accepted. */
  auth: string;
  url: string;
}

/** Session captured during recording. Never carries the cookies themselves. */
export interface AuthProfile {
  id: string;
  project_id: string;
  name: string;
  expires_at: string | null;
  cookie_count: number;
  origins: string[];
  is_usable: boolean;
}

export interface Step {
  id?: string;
  test_case_id?: string;
  order_index: number;
  action: Action;
  selector: string;
  selector_strategy: SelectorStrategy;
  value: string | null;
  assertion_type: string | null;
  expected_value: string | null;
  /** Set when the element lives inside an iframe rather than the main page. */
  frame_url?: string | null;
  /**
   * JSON the recorder wrote describing the element - its tag, role, label and
   * other ways to reach it. Replay falls back to it when the selector stops
   * matching, so it has to survive a round trip through this editor.
   */
  element_meta?: string | null;
  /** Exit criteria run after every recorded step and decide the verdict. */
  is_exit_criteria?: boolean;
}

export interface TestCase {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  start_url: string | null;
  created_at: string;
  steps: Step[];
}

export interface StepResult {
  id: string;
  test_run_id: string;
  step_id: string;
  status: RunStatus;
  duration_ms: number | null;
  screenshot_path: string | null;
  error_message: string | null;
}

export interface Evidence {
  id: string;
  test_run_id: string;
  type: EvidenceType;
  file_path: string;
  created_at: string;
}

export interface TestRun {
  id: string;
  test_case_id: string;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  trigger_source: string;
  error_message: string | null;
  batch_id: string | null;
  batch_order: number | null;
  jira_issue_key: string | null;
  jira_status: JiraSyncStatus | null;
  jira_error: string | null;
  step_results: StepResult[];
  evidences: Evidence[];
}

/** Several test cases replayed one after another, reported together. */
export interface RunBatch {
  id: string;
  project_id: string | null;
  name: string;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  trigger_source: string | null;
  error_message: string | null;
  report_path: string | null;
  jira_issue_key: string | null;
  jira_status: JiraSyncStatus | null;
  jira_error: string | null;
  runs: TestRun[];
}
