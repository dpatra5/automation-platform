// =====================================================================
// Session State Types
// =====================================================================

export type SessionState =
  | 'awaiting_problem'
  | 'analyzing'
  | 'review_summary'
  | 'creating_story_description'
  | 'review_story_description'
  | 'creating_sdlc_testplan'
  | 'review_sdlc_testplan'
  | 'creating_story_subtasks'
  | 'review_story_subtasks'
  | 'creating_test_cases'
  | 'review_test_cases'
  | 'creating_jira'
  | 'completed'
  | 'error';

// =====================================================================
// Step 1: Summary Data
// =====================================================================

export type Level = 'Low' | 'Medium' | 'High';

export interface SummaryData {
  summary: string;
  key_points: string[];
  suggested_scope: string;
  potential_challenges: string[];
  estimated_complexity: Level;
}

// =====================================================================
// Step 2: Story Description
// =====================================================================

export interface StoryDescriptionData {
  title: string;
  description: string;
  business_value: string;
  user_persona: string;
  success_metrics: string[];
}

// =====================================================================
// Step 3: SDLC Plan (Comprehensive)
// =====================================================================

export interface ProjectOverview {
  /** Usually a `Level`, but the LLM may return free text. */
  complexity: string;
  estimated_duration: string;
  total_work_hours: string;
  resource_count: string;
  recommended_team: string[];
}

export interface AgileExecutionPlan {
  methodology: string;
  sprint_count: string;
  sprint_duration: string;
  epic_name: string;
  story_mapping: string;
}

export interface SDLCPhase {
  phase: string;
  objective: string;
  estimatedEffort: string;
  workHours: string;
  resourcesRequired: string;
  tools: string[];
  deliverables: string[];
  dependencies: string[];
  expectedChallenges: string[];
  mitigationPlan: string[];
}

export interface TestingStrategy {
  unit_testing: string;
  integration_testing: string;
  system_testing: string;
  sit_testing: string;
  uat_testing: string;
  performance_testing: string;
  security_testing: string;
  regression_testing: string;
  automation_testing: string;
  entry_criteria: string[];
  exit_criteria: string[];
}

export interface DeploymentPlan {
  deployment_type: string;
  rollback_strategy: string;
  monitoring_tools: string[];
  post_go_live_activities: string[];
}

export interface RisksAndDependencies {
  technical_risks: string[];
  business_risks: string[];
  external_dependencies: string[];
}

export interface SDLCTestPlanData {
  project_overview: ProjectOverview;
  agile_execution_plan: AgileExecutionPlan;
  sdlc_phases: SDLCPhase[];
  testing_strategy: TestingStrategy;
  deployment_plan: DeploymentPlan;
  risks_and_dependencies: RisksAndDependencies;
}

// =====================================================================
// Step 4: Story & Tasks (Redesigned)
// =====================================================================

export interface StoryDetails {
  title: string;
  type: string;
  description: string;
  acceptance_criteria: string[];
  story_points: number;
  priority: Level;
  labels: string[];
  components: string[];
}

export interface Task {
  taskId: string;
  title: string;
  description: string;
  /** e.g. Frontend, Backend, Database, API, Testing, Documentation. */
  type: string;
  priority: Level;
  estimate: string;
}

export interface StoryTasksData {
  story: StoryDetails;
  tasks: Task[];
}

// =====================================================================
// Step 5: Test Cases (Redesigned)
// =====================================================================

export interface AutomationTestStep {
  sequence: number;
  action: string;
  expectedResult?: string;
}

export interface TestCase {
  testCaseId: string;
  title: string;
  preCondition: string;
  steps: string[];
  expectedResult: string;
  priority: Level;
  /** e.g. Positive, Negative, Boundary, Validation, UI. */
  type: string;

  // Automation-ready fields (optional so legacy backends keep working).
  requirementId?: string;
  acceptanceCriteriaIds?: string[];
  objective?: string;
  category?:
    | 'Positive'
    | 'Negative'
    | 'Boundary'
    | 'Validation'
    | 'Authorization'
    | 'ErrorHandling'
    | 'UI';
  severity?: 'Critical' | 'Major' | 'Minor' | 'Trivial';
  preconditions?: string[];
  testData?: Record<string, unknown>;
  automationSteps?: AutomationTestStep[];
  postconditions?: string[];
  cleanup?: string[];
  tags?: string[];
  automationEligible?: boolean;
  automationNotes?: string[];
  validationStatus?: 'pending' | 'valid' | 'invalid';
  scriptStatus?:
    | 'not_generated'
    | 'generating'
    | 'generated'
    | 'invalid'
    | 'ready';
  executionStatus?:
    | 'not_started'
    | 'queued'
    | 'running'
    | 'passed'
    | 'failed'
    | 'cancelled';
}

export interface TestCasesData {
  test_cases: TestCase[];
}

// =====================================================================
// Step 6: Jira Output (Enhanced)
// =====================================================================

export interface JiraTicketItem {
  id: string;
  summary: string;
  description: string;
  task: string;
  squad: string;
  owner: string;
  status: string;
  sprint: string;
  acceptanceCriteria: string[];
  parentId?: string;
  type?: string;
  priority?: string;
  estimate?: string;
}

export interface JiraTicket {
  key: string;
  type: string;
  title: string;
  status: string;
  parent_key: string | null;
}

export interface JiraActivity {
  timestamp: string;
  user: string;
  action: string;
  details: string;
}

export interface JiraComment {
  id: string;
  author: string;
  avatar?: string;
  timestamp: string;
  content: string;
}

export interface JiraOutput {
  // New format
  tickets: JiraTicketItem[];
  notFound: string[];
  // Legacy fields
  story_key: string;
  story_title: string;
  story_description: string;
  story_status: string;
  story_priority: string;
  story_sprint: string;
  story_type: string;
  assignee: string;
  reporter: string;
  squad: string;
  created_date: string;
  updated_date: string;
  acceptance_criteria: string[];
  business_requirement: string;
  attachments: string[];
  sub_task_keys: string[];
  test_case_count: number;
  created_tickets: JiraTicket[];
  activities: JiraActivity[];
  comments: JiraComment[];
  raw_data: Record<string, unknown>;
  jira_url: string | null;
}

// =====================================================================
// Session Response
// =====================================================================

export interface SessionResponse {
  session_id: string;
  state: SessionState;
  current_step: number;
  message: string;
  problem_statement: string | null;
  skip_sdlc: boolean;
  summary: SummaryData | null;
  story_description: StoryDescriptionData | null;
  sdlc_testplan: SDLCTestPlanData | null;
  story_tasks: StoryTasksData | null;
  test_cases: TestCasesData | null;
  jira_output: JiraOutput | null;
  error_message: string | null;
}

// =====================================================================
// Progress Types
// =====================================================================

export interface StepInfo {
  step_number: number;
  name: string;
  state: 'pending' | 'in_progress' | 'completed';
  completed: boolean;
  data_available: boolean;
}

export interface ProgressResponse {
  session_id: string;
  current_step: number;
  total_steps: number;
  steps: StepInfo[];
  state: string;
  message: string;
}

// =====================================================================
// Request Types
// =====================================================================

export interface ProblemStatementRequest {
  problem_statement: string;
  skip_sdlc?: boolean;
}

export interface ReviewRequest {
  approved: boolean;
}

export interface ModifyRequest {
  user_feedback: string;
}

// =====================================================================
// UI State Types
// =====================================================================

export type Step = 1 | 2 | 3 | 4 | 5 | 6;

export interface AppState {
  currentStep: Step;
  viewingStep: Step | null;
  sessionId: string | null;
  sessionState: SessionState;
  problemStatement: string;
  skipSdlc: boolean;
  summary: SummaryData | null;
  storyDescription: StoryDescriptionData | null;
  sdlcTestplan: SDLCTestPlanData | null;
  storyTasks: StoryTasksData | null;
  testCases: TestCasesData | null;
  jiraOutput: JiraOutput | null;
  isLoading: boolean;
  error: string | null;
  message: string;
  showJiraDetails: boolean;
}

// =====================================================================
// Health Check
// =====================================================================

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  version: string;
}
