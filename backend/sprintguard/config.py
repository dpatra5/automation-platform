"""
Configuration for Jira SprintGuard service.
Environment loading, model paths, and prompt templates for complete workflow.
"""

import os
import ssl
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


# ---------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------

def load_env_file() -> None:
    possible_paths = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]

    for env_path in possible_paths:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            break


load_env_file()

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "86400")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "86400")

if os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = os.getenv("HF_ENDPOINT", "").rstrip("/")

if os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN", "")
    os.environ["HUGGING_FACE_HUB_TOKEN"] = os.getenv("HF_TOKEN", "")

if os.getenv("DISABLE_SSL_VERIFY", "true").lower() == "true":
    ssl._create_default_https_context = ssl._create_unverified_context
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")


# ---------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------

MODEL_ID = os.getenv("LLAMA_MODEL_ID", "meta-llama/Llama-3.2-1B-Instruct")

SNAPSHOT_PATH = os.getenv(
    "LLAMA_LOCAL_MODEL_PATH",
    r"C:\Users\ADas155\.cache\huggingface\hub\models--meta-llama--Llama-3.2-1B-Instruct\snapshots\68ee529b2225d27a5cab3a3c77db152b56abfdd1",
)

MAX_INPUT_CHARS = int(os.getenv("LLM_MAX_INPUT_CHARS", "6000"))
MAX_NEW_TOKENS = int(os.getenv("LLM_MAX_NEW_TOKENS", "3000"))


# ---------------------------------------------------------------------
# API Configuration
# ---------------------------------------------------------------------

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")


# ---------------------------------------------------------------------
# Jira Configuration
# ---------------------------------------------------------------------

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://dev.jira.jnj.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "JGQE")
# Set to "true" to use mock Jira (for testing without Jira access)
JIRA_USE_MOCK = os.getenv("JIRA_USE_MOCK", "false").lower() == "true"


# ---------------------------------------------------------------------
# Prompt Templates for Complete Workflow
# ---------------------------------------------------------------------

# Step 1: Analyze Problem Statement
ANALYZE_PROBLEM_PROMPT = """Analyze this problem statement and extract insights. Be specific to the actual problem.

Problem: {problem_statement}

Return JSON with these fields:
- summary: comprehensive overview of the core problem (MUST be at least 40 words, covering problem context, impact, and what needs to be solved)
- key_points: array of 3-4 specific points extracted from the problem
- suggested_scope: a single comma-separated string listing what should be included and excluded (e.g., "User authentication, Dashboard UI, API integration; Excludes: Mobile app, Admin panel")
- potential_challenges: array of 2-3 realistic technical or business challenges
- estimated_complexity: "Low", "Medium", or "High"

Output ONLY valid JSON."""

# Step 2: Create Story Description
CREATE_STORY_DESCRIPTION_PROMPT = """Create a user story based on this problem and summary. Make it specific.

Problem: {problem_statement}
Summary: {summary}

Return JSON with these fields:
- title: concise action-oriented title for this specific feature
- description: 2 paragraphs explaining the feature in detail
- business_value: 1 sentence on why this matters to the business
- user_persona: who will use this feature and why
- success_metrics: array of 2-3 measurable KPIs

Output ONLY valid JSON."""

# Step 3: Create Comprehensive SDLC Plan
CREATE_SDLC_TESTPLAN_PROMPT = """
You are an experienced Project Manager and Solution Architect.

Analyze the user story and create a realistic Agile SDLC execution plan.

Story: {title}
Description: {description}
Acceptance Criteria: {acceptance_criteria}

Analyze the story complexity and provide SPECIFIC VALUES (not placeholders):
- Frontend complexity
- Backend complexity  
- Database impact
- API integrations
- Security requirements
- Deployment effort
- Testing effort

Generate JSON with ACTUAL VALUES filled in:

{{
  "project_overview": {{
    "complexity": "<choose one: Low, Medium, or High based on analysis>",
    "estimated_duration": "<e.g.in weeks>",
    "total_work_hours": "<e.g. in hours>",
    "resource_count": "<e.g.number people>",
    "recommended_team": ["<list specific roles needed>"]
  }},

  "agile_execution_plan": {{
    "methodology": "Scrum",
    "sprint_count": "<e.g.,number of sprints>",
    "sprint_duration": "<e.g., in weeks>",
    "epic_name": "<create a meaningful epic name for this feature>",
    "story_mapping": "<brief description of story breakdown>"
  }},

  "sdlc_phases": [
    {{
      "phase": "<phase name>",
      "objective": "<specific objective for this feature>",
      "estimatedEffort": "<e.g., 3 days, 1 week>",
      "workHours": "<e.g., 24, 40 hours>",
      "resourcesRequired": "<e.g., 2 developers, 1 QA>",
      "tools": ["<specific tools>"],
      "deliverables": ["<specific deliverables>"],
      "dependencies": ["<specific dependencies>"]
    }}
  ],

  "testing_strategy": {{
    "unit_testing": "<testing approach>",
    "integration_testing": "<testing approach>",
    "system_testing": "<testing approach>",
    "sit_testing": "<testing approach>",
    "uat_testing": "<testing approach>",
    "performance_testing": "<testing approach>",
    "security_testing": "<testing approach>",
    "regression_testing": "<testing approach>",
    "automation_testing": "<testing approach>",
    "entry_criteria": ["<list entry criteria>"],
    "exit_criteria": ["<list exit criteria>"]
  }},

  "deployment_plan": {{
    "deployment_type": "<e.g., Blue-Green, Rolling, Canary>",
    "rollback_strategy": "<describe rollback approach>",
    "monitoring_tools": ["<list monitoring tools>"],
    "post_go_live_activities": ["<list activities>"]
  }}
}}

Use the following SDLC phases:
1. Requirement Analysis
2. Solution Design
3. Sprint Planning
4. Development
5. Code Review
6. Testing & Validation
7. Deployment & Release
8. Hypercare & Support

IMPORTANT: Replace all <placeholder> text with ACTUAL VALUES based on your analysis of the story. Do not output placeholder text.

Output ONLY valid JSON.
"""

# Step 4: Create Categorized Implementation Tasks
CREATE_STORY_SUBTASKS_PROMPT = """Create implementation tasks for this story. Tasks must be specific to the feature.

Story: {title}
Description: {description}
Acceptance Criteria: {acceptance_criteria}

Return JSON with:
- story: object with:
  - title: the story title
  - type: "Story"
  - description: user story format (As a... I want... So that...)
  - acceptance_criteria: array of 5-6 DETAILED acceptance criteria covering all aspects of the feature (functional requirements, UI behavior, error handling, performance, security)
  - story_points: estimate (1-13)
  - priority: High/Medium/Low
  - labels: relevant labels array
  - components: affected system components array
- tasks: array of 6 task objects, each with taskId, title, description, type (Frontend/Backend/Database/API/Testing/Documentation), priority, estimate

Cover all task types. Make tasks specific to "{title}" - not generic software tasks.
Output ONLY valid JSON."""

# Step 5: Create Comprehensive Test Cases
CREATE_TEST_CASES_PROMPT = """You are a senior QA architect. Produce automation-ready test cases
for the story below. Every case will later be converted to an executable Rewind script,
so each step must be concrete, observable, and unambiguous.

Story title: {title}
Acceptance criteria: {acceptance_criteria}

Return JSON with a "test_cases" array of 8 objects. Each object MUST contain:

- testCaseId          e.g. "TC-001"
- requirementId       stable id for the parent requirement/story
- acceptanceCriteriaIds  array of AC ids this case validates, e.g. ["AC-1","AC-3"]
- title               short, specific to "{title}"
- objective           1 sentence explaining the business behavior verified
- category            one of: Positive | Negative | Boundary | Validation | Authorization | ErrorHandling | UI
- priority            High | Medium | Low
- severity            Critical | Major | Minor | Trivial
- preconditions       array of concrete setup statements (e.g. "User account exists with role=admin")
- testData            object with the exact input values needed (keys: field name, values: literal data)
- steps               array of 3-6 objects, each with:
                        - sequence (int, starts at 1)
                        - action  (concrete UI/API action — e.g. "Click the 'Submit' button")
                        - expectedResult (observable outcome for THIS step)
- expectedResult      final observable outcome for the whole case
- postconditions      array of statements describing the final system state
- cleanup             array of steps needed to reset state (may be empty)
- tags                array of short labels, e.g. ["login","smoke","regression"]
- automationEligible  boolean — true only if the case is deterministic and does not require human judgement
- automationNotes     array of notes for the script generator (selectors, wait conditions, etc.)

Coverage requirements (produce all 8 cases, distributed roughly like this):
- 2 Positive happy-path
- 2 Negative (invalid input, unauthorized, missing data)
- 1 Boundary (min/max/empty)
- 1 Validation (cross-field rule)
- 1 Authorization or ErrorHandling
- 1 Regression/UI

Also keep for backwards compatibility with the existing UI:
- preCondition   string, semicolon-joined summary of preconditions
- type           one of: Positive | Negative | Boundary | Validation | UI

Rules — a case MUST be rejected if it contains any of these:
- vague verbs like "verify functionality", "check response", "test the page"
- steps that do not describe a concrete user or system action
- unresolved placeholders like "{{value}}"
- duplicated coverage of another case in the same batch

Output ONLY valid JSON."""

# Modification prompts for user edits
MODIFY_CONTENT_PROMPT = """Modify this content based on user feedback. Keep same JSON structure.

Current: {current_content}
Feedback: {user_feedback}

Return ONLY valid JSON with requested changes."""


# ----------------------------------------
# Session States for Complete Workflow
# ----------------------------------------

SESSION_STATES = {
    "AWAITING_PROBLEM": "awaiting_problem",
    "ANALYZING": "analyzing",
    "REVIEW_SUMMARY": "review_summary",
    "CREATING_STORY_DESC": "creating_story_description",
    "REVIEW_STORY_DESC": "review_story_description",
    "CREATING_SDLC": "creating_sdlc_testplan",
    "REVIEW_SDLC": "review_sdlc_testplan",
    "CREATING_STORY_TASKS": "creating_story_subtasks",
    "REVIEW_STORY_TASKS": "review_story_subtasks",
    "CREATING_TEST_CASES": "creating_test_cases",
    "REVIEW_TEST_CASES": "review_test_cases",
    "CREATING_JIRA": "creating_jira",
    "COMPLETED": "completed",
    "ERROR": "error"
}


# ---------------------------------------------------------------------
# Empty Schema Templates
# ---------------------------------------------------------------------

EMPTY_SUMMARY_SCHEMA: Dict[str, Any] = {
    "summary": "",
    "key_points": [],
    "suggested_scope": "",
    "potential_challenges": [],
    "estimated_complexity": "Medium"
}

EMPTY_STORY_DESC_SCHEMA: Dict[str, Any] = {
    "title": "",
    "description": "",
    "business_value": "",
    "user_persona": "",
    "success_metrics": []
}

EMPTY_SDLC_SCHEMA: Dict[str, Any] = {
    "project_overview": {
        "complexity": "Medium",
        "estimated_duration": "",
        "total_work_hours": "",
        "resource_count": "",
        "recommended_team": []
    },
    "agile_execution_plan": {
        "methodology": "Scrum",
        "sprint_count": "",
        "sprint_duration": "",
        "epic_name": "",
        "story_mapping": ""
    },
    "sdlc_phases": [],
    "testing_strategy": {
        "unit_testing": "",
        "integration_testing": "",
        "system_testing": "",
        "sit_testing": "",
        "uat_testing": "",
        "performance_testing": "",
        "security_testing": "",
        "regression_testing": "",
        "automation_testing": "",
        "entry_criteria": [],
        "exit_criteria": []
    },
    "deployment_plan": {
        "deployment_type": "",
        "rollback_strategy": "",
        "monitoring_tools": [],
        "post_go_live_activities": []
    },
    "risks_and_dependencies": {
        "technical_risks": [],
        "business_risks": [],
        "external_dependencies": []
    }
}

EMPTY_STORY_TASKS_SCHEMA: Dict[str, Any] = {
    "story": {
        "title": "",
        "type": "Story",
        "description": "",
        "acceptance_criteria": [],
        "story_points": 3,
        "priority": "Medium",
        "labels": [],
        "components": []
    },
    "tasks": []
}

EMPTY_TEST_CASES_SCHEMA: Dict[str, Any] = {
    "test_cases": []
}
