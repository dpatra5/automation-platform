"""
Pydantic models for complete Jira SprintGuard API following Snapgrid flow.
Request and response models for all workflow steps.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# =====================================================================
# Base Response Models
# =====================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    version: str = "1.0.0"


class SessionResponse(BaseModel):
    """Complete session response."""
    session_id: str
    state: str
    current_step: int
    message: str
    problem_statement: Optional[str] = None
    skip_sdlc: bool = False
    summary: Optional[Dict[str, Any]] = None
    story_description: Optional[Dict[str, Any]] = None
    sdlc_testplan: Optional[Dict[str, Any]] = None
    story_tasks: Optional[Dict[str, Any]] = None
    test_cases: Optional[Dict[str, Any]] = None
    jira_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    session_id: Optional[str] = None


# =====================================================================
# Step 1: Problem Statement & Summary
# =====================================================================

class ProblemStatementRequest(BaseModel):
    """Request to submit a problem statement."""
    problem_statement: str = Field(..., min_length=10, description="The problem statement to analyze")
    skip_sdlc: bool = Field(default=False, description="Skip SDLC phases and go directly to tasks")


class SummaryData(BaseModel):
    """Summary data structure."""
    summary: str
    key_points: List[str]
    suggested_scope: str
    potential_challenges: List[str]
    estimated_complexity: str = Field(default="Medium", description="Low/Medium/High")


class AnalyzeResponse(BaseModel):
    """Response after analyzing problem statement."""
    session_id: str
    state: str
    current_step: int
    summary: SummaryData
    message: str = "Please review the summary"


# =====================================================================
# Step 2: Story Description
# =====================================================================

class StoryDescriptionData(BaseModel):
    """Story description data structure."""
    title: str
    description: str
    business_value: str
    user_persona: str
    success_metrics: List[str]


class StoryDescriptionResponse(BaseModel):
    """Response after creating story description."""
    session_id: str
    state: str
    current_step: int
    story_description: StoryDescriptionData
    message: str = "Please review the story description"


# =====================================================================
# Step 3: SDLC & Test Plan
# =====================================================================

class SDLCPhase(BaseModel):
    """SDLC phase structure."""
    phase: str
    activities: List[str]
    deliverables: List[str]
    duration_days: int = 5


class TestPlan(BaseModel):
    """Test plan structure."""
    testing_approach: str
    test_types: List[str]
    test_environments: List[str]
    entry_criteria: List[str]
    exit_criteria: List[str]
    risk_areas: List[str]


class SDLCTestPlanData(BaseModel):
    """SDLC and test plan combined data."""
    sdlc_phases: List[SDLCPhase]
    test_plan: TestPlan


class SDLCTestPlanResponse(BaseModel):
    """Response after creating SDLC and test plan."""
    session_id: str
    state: str
    current_step: int
    sdlc_testplan: SDLCTestPlanData
    message: str = "Please review SDLC phases and test plan"


# =====================================================================
# Step 4: Story with Sub-tasks & Acceptance Criteria
# =====================================================================

class StoryDetails(BaseModel):
    """Complete story details."""
    title: str
    type: str = "Story"
    description: str
    acceptance_criteria: List[str]
    story_points: int = Field(default=3, ge=1, le=21)
    priority: str = Field(default="Medium", description="High/Medium/Low")
    labels: List[str] = []
    components: List[str] = []


class SubTask(BaseModel):
    """Sub-task structure."""
    title: str
    description: str
    estimated_hours: int = 8
    assignee_role: str = "Developer"


class StoryTasksData(BaseModel):
    """Story with sub-tasks."""
    story: StoryDetails
    sub_tasks: List[SubTask]


class StoryTasksResponse(BaseModel):
    """Response after creating story with sub-tasks."""
    session_id: str
    state: str
    current_step: int
    story_tasks: StoryTasksData
    message: str = "Please review story and sub-tasks"


# =====================================================================
# Step 5: Manual Test Cases
# =====================================================================

class TestStep(BaseModel):
    """Test step structure."""
    step_number: int
    action: str
    expected_result: str


class TestCase(BaseModel):
    """Manual test case structure."""
    test_case_id: str
    title: str
    description: str
    preconditions: List[str]
    test_steps: List[TestStep]
    test_data: str = ""
    priority: str = "Medium"
    category: str = "Functional"


class TestCasesData(BaseModel):
    """Test cases collection."""
    test_cases: List[TestCase]


class TestCasesResponse(BaseModel):
    """Response after creating test cases."""
    session_id: str
    state: str
    current_step: int
    test_cases: TestCasesData
    message: str = "Please review test cases"


# =====================================================================
# Step 6: Jira Creation
# =====================================================================

class JiraTicket(BaseModel):
    """Jira ticket structure."""
    key: str = ""  # Will be set after actual Jira creation
    type: str
    title: str
    status: str = "To Do"
    parent_key: Optional[str] = None


class JiraOutput(BaseModel):
    """Jira creation output."""
    story_key: str = ""
    story_title: str
    sub_task_keys: List[str] = []
    test_case_count: int = 0
    created_tickets: List[JiraTicket] = []
    jira_url: Optional[str] = None


class JiraCreationResponse(BaseModel):
    """Response after creating Jira tickets."""
    session_id: str
    state: str
    current_step: int
    jira_output: JiraOutput
    message: str = "Jira tickets created successfully"


# =====================================================================
# Review & Edit Requests
# =====================================================================

class ReviewRequest(BaseModel):
    """Request to review current step (approve or reject)."""
    approved: bool = Field(..., description="True to approve, False to request edit")


class EditRequest(BaseModel):
    """Request to edit content with feedback."""
    feedback: str = Field(..., min_length=5, description="Edit instructions/feedback")
    field_to_edit: Optional[str] = Field(None, description="Specific field to edit (optional)")


class ModifyWithLLMRequest(BaseModel):
    """Request to modify content using LLM."""
    user_feedback: str = Field(..., min_length=5, description="Instructions for LLM modification")


# =====================================================================
# Progress Tracking
# =====================================================================

class StepInfo(BaseModel):
    """Information about a workflow step."""
    step_number: int
    name: str
    state: str
    completed: bool
    data_available: bool


class ProgressResponse(BaseModel):
    """Workflow progress response."""
    session_id: str
    current_step: int
    total_steps: int = 6
    steps: List[StepInfo]
    state: str
    message: str
