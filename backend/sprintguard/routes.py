"""
API routes for Jira SprintGuard - Complete Workflow.
Implements the full workflow from the Snapgrid flow diagram:

Step 1: Problem statement input → LLM analyzes → Summary review
Step 2: LLM creates story description → User reviews
Step 3: LLM creates SDLC & test plan → User reviews
Step 4: LLM creates story, sub-tasks, acceptance criteria → User reviews
Step 5: LLM creates manual test cases → User reviews
Step 6: Create Jira tickets (mock)
"""

import copy
import json
import logging
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .models import (
    ProblemStatementRequest,
    ReviewRequest,
    ModifyWithLLMRequest,
    SessionResponse,
    HealthResponse,
    ProgressResponse,
    StepInfo,
    AnalyzeResponse,
    SummaryData,
)
from .services import (
    session_manager,
    SessionState,
    SessionData,
    get_step_number,
    get_state_message,
)
from .llm_engine import generate_with_llama, extract_first_json_object
from .config import (
    ANALYZE_PROBLEM_PROMPT,
    CREATE_STORY_DESCRIPTION_PROMPT,
    CREATE_SDLC_TESTPLAN_PROMPT,
    CREATE_STORY_SUBTASKS_PROMPT,
    CREATE_TEST_CASES_PROMPT,
    MODIFY_CONTENT_PROMPT,
    EMPTY_SUMMARY_SCHEMA,
    EMPTY_STORY_DESC_SCHEMA,
    EMPTY_SDLC_SCHEMA,
    EMPTY_STORY_TASKS_SCHEMA,
    EMPTY_TEST_CASES_SCHEMA,
)


def _extract_text_from_item(item: Any) -> str:
    """Extract readable text from an item that might be a dict or string."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        # Try common text fields first
        for key in ["description", "text", "name", "title", "value", "point", "challenge"]:
            if key in item and isinstance(item[key], str):
                return item[key]
        # If no text field found, join all string values
        text_parts = [str(v) for v in item.values() if isinstance(v, (str, int, float))]
        return " - ".join(text_parts) if text_parts else str(item)
    return str(item)


def _normalize_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize summary data to ensure correct types."""
    result = copy.deepcopy(EMPTY_SUMMARY_SCHEMA)
    
    # Handle summary - ensure string
    if "summary" in data:
        val = data["summary"]
        result["summary"] = _extract_text_from_item(val)
    
    # Handle key_points - ensure list of strings
    if "key_points" in data:
        kp = data["key_points"]
        if isinstance(kp, list):
            result["key_points"] = [_extract_text_from_item(p) for p in kp]
        elif isinstance(kp, str):
            result["key_points"] = [kp]
    
    # Handle suggested_scope - ensure string (LLM sometimes returns dict)
    if "suggested_scope" in data:
        val = data["suggested_scope"]
        result["suggested_scope"] = _extract_text_from_item(val)
    
    # Handle potential_challenges - ensure list of strings
    if "potential_challenges" in data:
        pc = data["potential_challenges"]
        if isinstance(pc, list):
            result["potential_challenges"] = [_extract_text_from_item(c) for c in pc]
        elif isinstance(pc, str):
            result["potential_challenges"] = [pc]
    
    # Handle estimated_complexity - ensure string
    if "estimated_complexity" in data:
        val = data["estimated_complexity"]
        result["estimated_complexity"] = _extract_text_from_item(val)
    
    return result


def _normalize_story_description(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize story description data to ensure correct types."""
    result = copy.deepcopy(EMPTY_STORY_DESC_SCHEMA)
    
    if "title" in data:
        result["title"] = _extract_text_from_item(data["title"])
    
    if "description" in data:
        result["description"] = _extract_text_from_item(data["description"])
    
    if "business_value" in data:
        result["business_value"] = _extract_text_from_item(data["business_value"])
    
    if "user_persona" in data:
        result["user_persona"] = _extract_text_from_item(data["user_persona"])
    
    if "success_metrics" in data:
        sm = data["success_metrics"]
        if isinstance(sm, list):
            result["success_metrics"] = [_extract_text_from_item(m) for m in sm]
        elif isinstance(sm, str):
            result["success_metrics"] = [sm]
    
    return result


def _normalize_sdlc_testplan(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize comprehensive SDLC plan data with new structure."""
    result = copy.deepcopy(EMPTY_SDLC_SCHEMA)
    
    # Normalize project_overview
    if "project_overview" in data and isinstance(data["project_overview"], dict):
        po = data["project_overview"]
        result["project_overview"] = {
            "complexity": _extract_text_from_item(po.get("complexity", "Medium")),
            "estimated_duration": _extract_text_from_item(po.get("estimated_duration", "")),
            "total_work_hours": _extract_text_from_item(po.get("total_work_hours", "")),
            "resource_count": _extract_text_from_item(po.get("resource_count", "")),
            "recommended_team": [_extract_text_from_item(t) for t in po.get("recommended_team", [])]
        }
    
    # Normalize agile_execution_plan
    if "agile_execution_plan" in data and isinstance(data["agile_execution_plan"], dict):
        aep = data["agile_execution_plan"]
        result["agile_execution_plan"] = {
            "methodology": _extract_text_from_item(aep.get("methodology", "Scrum")),
            "sprint_count": _extract_text_from_item(aep.get("sprint_count", "")),
            "sprint_duration": _extract_text_from_item(aep.get("sprint_duration", "")),
            "epic_name": _extract_text_from_item(aep.get("epic_name", "")),
            "story_mapping": _extract_text_from_item(aep.get("story_mapping", ""))
        }
    
    # Normalize sdlc_phases
    if "sdlc_phases" in data and isinstance(data["sdlc_phases"], list):
        phases = []
        for phase in data["sdlc_phases"]:
            if isinstance(phase, dict):
                normalized_phase = {
                    "phase": _extract_text_from_item(phase.get("phase", "")),
                    "objective": _extract_text_from_item(phase.get("objective", "")),
                    "estimatedEffort": _extract_text_from_item(phase.get("estimatedEffort", phase.get("estimated_effort", "3-5 days"))),
                    "workHours": _extract_text_from_item(phase.get("workHours", phase.get("work_hours", ""))),
                    "resourcesRequired": _extract_text_from_item(phase.get("resourcesRequired", phase.get("resources_required", ""))),
                    "tools": [_extract_text_from_item(t) for t in phase.get("tools", [])],
                    "deliverables": [_extract_text_from_item(d) for d in phase.get("deliverables", [])],
                    "dependencies": [_extract_text_from_item(d) for d in phase.get("dependencies", [])],
                    "expectedChallenges": [_extract_text_from_item(c) for c in phase.get("expectedChallenges", phase.get("expected_challenges", phase.get("risks", [])))],
                    "mitigationPlan": [_extract_text_from_item(m) for m in phase.get("mitigationPlan", phase.get("mitigation_plan", []))]
                }
                phases.append(normalized_phase)
        result["sdlc_phases"] = phases
    
    # Normalize testing_strategy
    if "testing_strategy" in data and isinstance(data["testing_strategy"], dict):
        ts = data["testing_strategy"]
        result["testing_strategy"] = {
            "unit_testing": _extract_text_from_item(ts.get("unit_testing", "")),
            "integration_testing": _extract_text_from_item(ts.get("integration_testing", "")),
            "system_testing": _extract_text_from_item(ts.get("system_testing", "")),
            "sit_testing": _extract_text_from_item(ts.get("sit_testing", "")),
            "uat_testing": _extract_text_from_item(ts.get("uat_testing", "")),
            "performance_testing": _extract_text_from_item(ts.get("performance_testing", "")),
            "security_testing": _extract_text_from_item(ts.get("security_testing", "")),
            "regression_testing": _extract_text_from_item(ts.get("regression_testing", "")),
            "automation_testing": _extract_text_from_item(ts.get("automation_testing", "")),
            "entry_criteria": [_extract_text_from_item(c) for c in ts.get("entry_criteria", [])],
            "exit_criteria": [_extract_text_from_item(c) for c in ts.get("exit_criteria", [])]
        }
    
    # Normalize deployment_plan
    if "deployment_plan" in data and isinstance(data["deployment_plan"], dict):
        dp = data["deployment_plan"]
        result["deployment_plan"] = {
            "deployment_type": _extract_text_from_item(dp.get("deployment_type", "")),
            "rollback_strategy": _extract_text_from_item(dp.get("rollback_strategy", "")),
            "monitoring_tools": [_extract_text_from_item(t) for t in dp.get("monitoring_tools", [])],
            "post_go_live_activities": [_extract_text_from_item(a) for a in dp.get("post_go_live_activities", [])]
        }
    
    # Normalize risks_and_dependencies
    if "risks_and_dependencies" in data and isinstance(data["risks_and_dependencies"], dict):
        rd = data["risks_and_dependencies"]
        result["risks_and_dependencies"] = {
            "technical_risks": [_extract_text_from_item(r) for r in rd.get("technical_risks", [])],
            "business_risks": [_extract_text_from_item(r) for r in rd.get("business_risks", [])],
            "external_dependencies": [_extract_text_from_item(d) for d in rd.get("external_dependencies", [])]
        }
    
    return result


def _normalize_story_tasks(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize story tasks data with categorized tasks."""
    result = copy.deepcopy(EMPTY_STORY_TASKS_SCHEMA)
    
    if "story" in data and isinstance(data["story"], dict):
        story = data["story"]
        result["story"] = {
            "title": _extract_text_from_item(story.get("title", "")),
            "type": _extract_text_from_item(story.get("type", "Story")),
            "description": _extract_text_from_item(story.get("description", "")),
            "acceptance_criteria": [_extract_text_from_item(ac) for ac in story.get("acceptance_criteria", [])],
            "story_points": int(story.get("story_points", 3)) if story.get("story_points") else 3,
            "priority": _extract_text_from_item(story.get("priority", "Medium")),
            "labels": [_extract_text_from_item(l) for l in story.get("labels", [])],
            "components": [_extract_text_from_item(c) for c in story.get("components", [])]
        }
    
    # Handle both "tasks" and "sub_tasks" for backwards compatibility
    tasks_key = "tasks" if "tasks" in data else "sub_tasks"
    if tasks_key in data and isinstance(data[tasks_key], list):
        tasks = []
        for i, task in enumerate(data[tasks_key]):
            if isinstance(task, dict):
                normalized_task = {
                    "taskId": _extract_text_from_item(task.get("taskId", task.get("task_id", f"TASK-{i+1:03d}"))),
                    "title": _extract_text_from_item(task.get("title", "")),
                    "description": _extract_text_from_item(task.get("description", "")),
                    "type": _extract_text_from_item(task.get("type", task.get("assignee_role", "Backend"))),
                    "priority": _extract_text_from_item(task.get("priority", "Medium")),
                    "estimate": _extract_text_from_item(task.get("estimate", f"{task.get('estimated_hours', 4)}h"))
                }
                tasks.append(normalized_task)
        result["tasks"] = tasks
    
    return result


_VAGUE_STEP_PATTERNS = (
    "verify functionality",
    "check response",
    "test the page",
    "verify the application works",
    "check the response",
    "validate the page",
    "test the functionality",
    "it works",
)

_ALLOWED_CATEGORIES = {
    "Positive", "Negative", "Boundary", "Validation",
    "Authorization", "ErrorHandling", "UI",
}

_LEGACY_TYPE_MAP = {
    "authorization": "Negative",
    "errorhandling": "Negative",
    "error_handling": "Negative",
    "ui": "UI",
    "positive": "Positive",
    "negative": "Negative",
    "boundary": "Boundary",
    "validation": "Validation",
}


def _is_vague(text: str) -> bool:
    """True when a step's text matches any known vague, non-actionable phrase."""
    t = (text or "").strip().lower()
    if len(t) < 5:
        return True
    return any(p in t for p in _VAGUE_STEP_PATTERNS)


def _norm_step(raw: Any, seq: int) -> Dict[str, Any]:
    """Normalize a step to {sequence, action, expectedResult}. Accepts str or dict."""
    if isinstance(raw, str):
        return {"sequence": seq, "action": raw.strip(), "expectedResult": ""}
    if isinstance(raw, dict):
        return {
            "sequence": int(raw.get("sequence", seq) or seq),
            "action": _extract_text_from_item(raw.get("action", raw.get("step", ""))),
            "expectedResult": _extract_text_from_item(
                raw.get("expectedResult", raw.get("expected_result", ""))
            ),
        }
    return {"sequence": seq, "action": str(raw), "expectedResult": ""}


def _legacy_type_from_category(category: str) -> str:
    return _LEGACY_TYPE_MAP.get((category or "").strip().lower(), "Positive")


def _normalize_test_cases(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize test cases data into the automation-ready shape.

    Preserves rich fields for the automation pipeline and also emits the
    legacy `preCondition` string and `steps: [str]` shape the current UI uses.
    Duplicates and cases containing vague steps are dropped.
    """
    result = copy.deepcopy(EMPTY_TEST_CASES_SCHEMA)
    
    if "test_cases" in data and isinstance(data["test_cases"], list):
        cases: List[Dict[str, Any]] = []
        seen_signatures: set = set()

        for i, tc in enumerate(data["test_cases"]):
            if not isinstance(tc, dict):
                continue

            raw_steps = tc.get("steps", tc.get("test_steps", [])) or []
            structured_steps = [_norm_step(s, idx + 1) for idx, s in enumerate(raw_steps)]

            if any(_is_vague(s["action"]) for s in structured_steps):
                logger.info("Dropping test case with vague steps: %s", tc.get("title"))
                continue
            if not structured_steps:
                continue

            preconditions_raw = tc.get("preconditions", [])
            if isinstance(preconditions_raw, str):
                preconditions_list = [preconditions_raw]
            else:
                preconditions_list = [_extract_text_from_item(p) for p in preconditions_raw]

            precondition_str = _extract_text_from_item(
                tc.get("preCondition", "; ".join(preconditions_list))
            )

            category = _extract_text_from_item(tc.get("category", tc.get("type", "Positive")))
            if category not in _ALLOWED_CATEGORIES:
                category = "Positive"

            test_data = tc.get("testData")
            if not isinstance(test_data, dict):
                test_data = {}

            ac_ids_raw = tc.get("acceptanceCriteriaIds", tc.get("acceptance_criteria_ids", []))
            ac_ids = [_extract_text_from_item(x) for x in ac_ids_raw] if isinstance(ac_ids_raw, list) else []

            tags_raw = tc.get("tags", []) or []
            tags = [_extract_text_from_item(x) for x in tags_raw] if isinstance(tags_raw, list) else []

            normalized_tc = {
                "testCaseId": _extract_text_from_item(
                    tc.get("testCaseId", tc.get("test_case_id", f"TC-{i+1:03d}"))
                ),
                "requirementId": _extract_text_from_item(tc.get("requirementId", "")),
                "acceptanceCriteriaIds": ac_ids,
                "title": _extract_text_from_item(tc.get("title", "")),
                "objective": _extract_text_from_item(tc.get("objective", "")),
                "category": category,
                "type": _extract_text_from_item(tc.get("type", _legacy_type_from_category(category))),
                "priority": _extract_text_from_item(tc.get("priority", "Medium")),
                "severity": _extract_text_from_item(tc.get("severity", "Major")),
                "preconditions": preconditions_list,
                "preCondition": precondition_str,
                "testData": test_data,
                "automationSteps": structured_steps,
                "steps": [s["action"] for s in structured_steps],
                "expectedResult": _extract_text_from_item(
                    tc.get("expectedResult", tc.get("expected_result", ""))
                ),
                "postconditions": [_extract_text_from_item(p) for p in tc.get("postconditions", []) or []],
                "cleanup": [_extract_text_from_item(p) for p in tc.get("cleanup", []) or []],
                "tags": tags,
                "automationEligible": bool(tc.get("automationEligible", True)),
                "automationNotes": [_extract_text_from_item(n) for n in tc.get("automationNotes", []) or []],
                "validationStatus": "pending",
                "scriptStatus": "not_generated",
                "executionStatus": "not_started",
            }

            signature = (
                normalized_tc["title"].strip().lower(),
                "|".join(s["action"].strip().lower() for s in structured_steps),
                normalized_tc["expectedResult"].strip().lower(),
            )
            if signature in seen_signatures:
                logger.info("Dropping duplicate test case: %s", normalized_tc["title"])
                continue
            seen_signatures.add(signature)

            cases.append(normalized_tc)

        result["test_cases"] = cases
    
    return result


router = APIRouter()


# =====================================================================
# Health & Session Management
# =====================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    model_loaded = False
    try:
        from .llm_engine import _model
        model_loaded = _model is not None
    except Exception:
        pass
    
    return HealthResponse(
        status="healthy",
        model_loaded=model_loaded,
        version="1.0.0"
    )


@router.post("/session/create", response_model=SessionResponse)
async def create_session():
    """Create a new session for the workflow."""
    session = session_manager.create_session()
    return _build_session_response(session)


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get the current state of a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_session_response(session)


@router.get("/session/{session_id}/progress", response_model=ProgressResponse)
async def get_progress(session_id: str):
    """Get detailed progress of the workflow."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    steps = [
        StepInfo(
            step_number=1,
            name="Problem Analysis",
            state=_get_step_state(session, 1),
            completed=session.summary is not None and session.current_step > 1,
            data_available=session.summary is not None
        ),
        StepInfo(
            step_number=2,
            name="Story Description",
            state=_get_step_state(session, 2),
            completed=session.story_description is not None and session.current_step > 2,
            data_available=session.story_description is not None
        ),
        StepInfo(
            step_number=3,
            name="SDLC & Test Plan",
            state=_get_step_state(session, 3),
            completed=session.sdlc_testplan is not None and session.current_step > 3,
            data_available=session.sdlc_testplan is not None
        ),
        StepInfo(
            step_number=4,
            name="Story & Sub-tasks",
            state=_get_step_state(session, 4),
            completed=session.story_tasks is not None and session.current_step > 4,
            data_available=session.story_tasks is not None
        ),
        StepInfo(
            step_number=5,
            name="Test Cases",
            state=_get_step_state(session, 5),
            completed=session.test_cases is not None and session.current_step > 5,
            data_available=session.test_cases is not None
        ),
        StepInfo(
            step_number=6,
            name="Jira Creation",
            state=_get_step_state(session, 6),
            completed=session.state == SessionState.COMPLETED,
            data_available=session.jira_output is not None
        ),
    ]
    
    return ProgressResponse(
        session_id=session.session_id,
        current_step=session.current_step,
        total_steps=6,
        steps=steps,
        state=session.state.value,
        message=get_state_message(session.state)
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_manager.delete_session(session_id):
        return {"message": "Session deleted successfully"}
    raise HTTPException(status_code=404, detail="Session not found")


# =====================================================================
# Step 1: Problem Statement Analysis
# =====================================================================

@router.post("/step1/analyze/{session_id}", response_model=AnalyzeResponse)
async def analyze_problem(session_id: str, request: ProblemStatementRequest):
    """
    Step 1: User submits problem statement → LLM analyzes → Returns summary only.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.state = SessionState.ANALYZING
    session.problem_statement = request.problem_statement
    session.skip_sdlc = request.skip_sdlc
    session_manager.update_session(session)
    
    try:
        prompt = ANALYZE_PROBLEM_PROMPT.format(
            problem_statement=request.problem_statement
        )
        
        raw_response = generate_with_llama(prompt)
        summary = extract_first_json_object(raw_response)
        
        if not summary:
            logger.warning(f"Failed to parse summary JSON. Raw response: {raw_response[:500]}")
            summary = copy.deepcopy(EMPTY_SUMMARY_SCHEMA)
            summary["summary"] = raw_response[:500] if raw_response else "Analysis failed"
        
        # Normalize to ensure correct types
        summary = _normalize_summary(summary)
        
        session.summary = summary
        session.state = SessionState.REVIEW_SUMMARY
        session.current_step = 1
        session_manager.update_session(session)
        
        return AnalyzeResponse(
            session_id=session.session_id,
            state=session.state.value,
            current_step=session.current_step,
            summary=SummaryData(**summary),
            message="Please review the summary"
        )
        
    except Exception as e:
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step1/review/{session_id}", response_model=SessionResponse)
async def review_summary(session_id: str, request: ReviewRequest):
    """
    Step 1 Review: User approves or rejects the summary.
    Approved → Proceed to Step 2
    Rejected → Stay for modification
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_SUMMARY:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    if request.approved:
        # Proceed to Step 2: Create Story Description
        return await _create_story_description(session)
    else:
        # Stay in review state for modification
        return _build_session_response(session, message="Please provide feedback to modify the summary")


@router.post("/step1/modify/{session_id}", response_model=SessionResponse)
async def modify_summary(session_id: str, request: ModifyWithLLMRequest):
    """
    Step 1 Modify: LLM modifies the summary based on user feedback.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_SUMMARY:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    try:
        prompt = MODIFY_CONTENT_PROMPT.format(
            current_content=json.dumps(session.summary, indent=2),
            user_feedback=request.user_feedback
        )
        
        raw_response = generate_with_llama(prompt)
        modified = extract_first_json_object(raw_response)
        
        if modified:
            modified = _normalize_summary(modified)
            session.add_modification("step1", "summary", session.summary, modified)
            session.summary = modified
        
        session_manager.update_session(session)
        return _build_session_response(session)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Step 2: Story Description
# =====================================================================

async def _create_story_description(session: SessionData) -> SessionResponse:
    """Internal: Create story description using LLM."""
    session.state = SessionState.CREATING_STORY_DESC
    session_manager.update_session(session)
    
    try:
        prompt = CREATE_STORY_DESCRIPTION_PROMPT.format(
            problem_statement=session.problem_statement,
            summary=json.dumps(session.summary, indent=2)
        )
        
        raw_response = generate_with_llama(prompt)
        story_desc = extract_first_json_object(raw_response)
        
        if not story_desc:
            logger.warning(f"Failed to parse story_desc JSON. Raw response: {raw_response[:500]}")
            story_desc = copy.deepcopy(EMPTY_STORY_DESC_SCHEMA)
            story_desc["title"] = session.summary.get("summary", "Story Description")[:100]
            story_desc["description"] = raw_response[:500] if raw_response else session.problem_statement
        
        # Normalize to ensure correct types
        story_desc = _normalize_story_description(story_desc)
        
        # Fallback: if title/description still empty after normalization, use summary data
        if not story_desc.get("title"):
            story_desc["title"] = session.summary.get("summary", "Story Description")[:100]
        if not story_desc.get("description"):
            story_desc["description"] = session.summary.get("summary", session.problem_statement)
        
        session.story_description = story_desc
        session.state = SessionState.REVIEW_STORY_DESC
        session.current_step = 2
        session_manager.update_session(session)
        
        return _build_session_response(session)
        
    except Exception as e:
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step2/review/{session_id}", response_model=SessionResponse)
async def review_story_description(session_id: str, request: ReviewRequest):
    """
    Step 2 Review: User approves or rejects story description.
    If skip_sdlc is True, goes directly to creating story tasks.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_STORY_DESC:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    if request.approved:
        # If skip_sdlc is True, skip SDLC and go directly to story tasks
        if session.skip_sdlc:
            return await _create_story_tasks(session)
        return await _create_sdlc_testplan(session)
    else:
        return _build_session_response(session, message="Please provide feedback to modify the story description")


@router.post("/step2/modify/{session_id}", response_model=SessionResponse)
async def modify_story_description(session_id: str, request: ModifyWithLLMRequest):
    """
    Step 2 Modify: LLM modifies story description based on feedback.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_STORY_DESC:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    try:
        prompt = MODIFY_CONTENT_PROMPT.format(
            current_content=json.dumps(session.story_description, indent=2),
            user_feedback=request.user_feedback
        )
        
        raw_response = generate_with_llama(prompt)
        modified = extract_first_json_object(raw_response)
        
        if modified:
            modified = _normalize_story_description(modified)
            session.add_modification("step2", "story_description", session.story_description, modified)
            session.story_description = modified
        
        session_manager.update_session(session)
        return _build_session_response(session)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Step 3: SDLC & Test Plan
# =====================================================================

async def _create_sdlc_testplan(session: SessionData) -> SessionResponse:
    """Internal: Create SDLC phases using LLM."""
    session.state = SessionState.CREATING_SDLC
    session_manager.update_session(session)
    
    try:
        # Get title and description with fallback
        title = session.story_description.get("title", "") or session.summary.get("summary", "")[:100]
        description = session.story_description.get("description", "") or session.problem_statement
        
        # Get acceptance criteria from summary key_points or create from business value
        key_points = session.summary.get("key_points", [])
        business_value = session.story_description.get("business_value", "")
        success_metrics = session.story_description.get("success_metrics", [])
        
        acceptance_criteria = []
        for kp in key_points:
            acceptance_criteria.append(f"- {kp}")
        if business_value:
            acceptance_criteria.append(f"- Business Value: {business_value}")
        for sm in success_metrics:
            acceptance_criteria.append(f"- Success Metric: {sm}")
        
        acceptance_criteria_str = "\n".join(acceptance_criteria) if acceptance_criteria else "- Feature works as expected"
        
        prompt = CREATE_SDLC_TESTPLAN_PROMPT.format(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria_str
        )
        
        raw_response = generate_with_llama(prompt)
        sdlc_data = extract_first_json_object(raw_response)
        
        if not sdlc_data:
            logger.warning(f"Failed to parse sdlc_data JSON. Raw response: {raw_response[:500]}")
            sdlc_data = copy.deepcopy(EMPTY_SDLC_SCHEMA)
        
        # Normalize to ensure correct types
        sdlc_data = _normalize_sdlc_testplan(sdlc_data)
        
        session.sdlc_testplan = sdlc_data
        session.state = SessionState.REVIEW_SDLC
        session.current_step = 3
        session_manager.update_session(session)
        
        return _build_session_response(session)
        
    except Exception as e:
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step3/review/{session_id}", response_model=SessionResponse)
async def review_sdlc(session_id: str, request: ReviewRequest):
    """
    Step 3 Review: User approves or rejects SDLC & test plan.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_SDLC:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    if request.approved:
        return await _create_story_tasks(session)
    else:
        return _build_session_response(session, message="Please provide feedback to modify SDLC/test plan")


@router.post("/step3/modify/{session_id}", response_model=SessionResponse)
async def modify_sdlc(session_id: str, request: ModifyWithLLMRequest):
    """
    Step 3 Modify: LLM modifies SDLC/test plan based on feedback.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_SDLC:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    try:
        prompt = MODIFY_CONTENT_PROMPT.format(
            current_content=json.dumps(session.sdlc_testplan, indent=2),
            user_feedback=request.user_feedback
        )
        
        raw_response = generate_with_llama(prompt)
        modified = extract_first_json_object(raw_response)
        
        if modified:
            modified = _normalize_sdlc_testplan(modified)
            session.add_modification("step3", "sdlc_testplan", session.sdlc_testplan, modified)
            session.sdlc_testplan = modified
        
        session_manager.update_session(session)
        return _build_session_response(session)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Step 4: Story with Sub-tasks & Acceptance Criteria
# =====================================================================

async def _create_story_tasks(session: SessionData) -> SessionResponse:
    """Internal: Create story with categorized tasks using LLM."""
    session.state = SessionState.CREATING_STORY_TASKS
    session_manager.update_session(session)
    
    try:
        # Get title and description with fallback to summary/problem statement
        title = session.story_description.get("title", "")
        description = session.story_description.get("description", "")
        
        # Fallback: if title/description empty, use summary data
        if not title:
            title = session.summary.get("summary", session.problem_statement[:100])
        if not description:
            description = session.story_description.get("business_value", "") or session.summary.get("summary", "")
        
        # Get acceptance criteria from summary key_points
        key_points = session.summary.get("key_points", [])
        success_metrics = session.story_description.get("success_metrics", [])
        
        acceptance_criteria = []
        for kp in key_points:
            acceptance_criteria.append(f"- {kp}")
        for sm in success_metrics:
            acceptance_criteria.append(f"- {sm}")
        
        acceptance_criteria_str = "\n".join(acceptance_criteria) if acceptance_criteria else "- Feature works as expected"
        
        prompt = CREATE_STORY_SUBTASKS_PROMPT.format(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria_str
        )
        
        raw_response = generate_with_llama(prompt)
        story_tasks = extract_first_json_object(raw_response)
        
        if not story_tasks:
            logger.warning(f"Failed to parse story_tasks JSON. Raw response: {raw_response[:500]}")
            story_tasks = copy.deepcopy(EMPTY_STORY_TASKS_SCHEMA)
            story_tasks["story"]["title"] = session.story_description.get("title", "")
        
        # Normalize to ensure correct types
        story_tasks = _normalize_story_tasks(story_tasks)
        
        session.story_tasks = story_tasks
        session.state = SessionState.REVIEW_STORY_TASKS
        session.current_step = 4
        session_manager.update_session(session)
        
        return _build_session_response(session)
        
    except Exception as e:
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step4/review/{session_id}", response_model=SessionResponse)
async def review_story_tasks(session_id: str, request: ReviewRequest):
    """
    Step 4 Review: User approves or rejects story & sub-tasks.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_STORY_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    if request.approved:
        return await _create_test_cases(session)
    else:
        return _build_session_response(session, message="Please provide feedback to modify story/sub-tasks")


@router.post("/step4/modify/{session_id}", response_model=SessionResponse)
async def modify_story_tasks(session_id: str, request: ModifyWithLLMRequest):
    """
    Step 4 Modify: LLM modifies story/sub-tasks based on feedback.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_STORY_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    try:
        prompt = MODIFY_CONTENT_PROMPT.format(
            current_content=json.dumps(session.story_tasks, indent=2),
            user_feedback=request.user_feedback
        )
        
        raw_response = generate_with_llama(prompt)
        modified = extract_first_json_object(raw_response)
        
        if modified:
            modified = _normalize_story_tasks(modified)
            session.add_modification("step4", "story_tasks", session.story_tasks, modified)
            session.story_tasks = modified
        
        session_manager.update_session(session)
        return _build_session_response(session)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Step 5: Manual Test Cases
# =====================================================================

async def _create_test_cases(session: SessionData) -> SessionResponse:
    """Internal: Create manual test cases using LLM."""
    session.state = SessionState.CREATING_TEST_CASES
    session_manager.update_session(session)
    
    try:
        acceptance_criteria = session.story_tasks.get("story", {}).get("acceptance_criteria", [])
        title = session.story_description.get("title", "") or session.summary.get("summary", "")[:100]

        if not acceptance_criteria:
            raise RuntimeError(
                "Cannot generate test cases: story has no acceptance criteria. "
                "Approve Step 4 with valid acceptance criteria first."
            )

        prompt = CREATE_TEST_CASES_PROMPT.format(
            title=title,
            acceptance_criteria="\n".join(f"- {ac}" for ac in acceptance_criteria)
        )
        
        raw_response = generate_with_llama(prompt)
        logger.info(f"Test cases raw LLM response length: {len(raw_response)}")
        logger.info(f"Test cases raw response preview: {raw_response[:1000]}")
        
        test_cases = extract_first_json_object(raw_response)
        
        if not test_cases or not test_cases.get("test_cases"):
            logger.error("LLM returned no parseable test_cases JSON. Raw response: %s", raw_response[:1000])
            raise RuntimeError(
                "LLM did not return any test cases. Please retry or modify the story."
            )

        test_cases = _normalize_test_cases(test_cases)

        if not test_cases.get("test_cases"):
            raise RuntimeError(
                "All generated test cases were rejected by the quality gate "
                "(vague steps, duplicates, or missing fields). Please retry."
            )

        session.test_cases = test_cases
        session.state = SessionState.REVIEW_TEST_CASES
        session.current_step = 5
        session_manager.update_session(session)
        
        return _build_session_response(session)
        
    except Exception as e:
        logger.error(f"Error creating test cases: {e}")
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step5/review/{session_id}", response_model=SessionResponse)
async def review_test_cases(session_id: str, request: ReviewRequest):
    """
    Step 5 Review: User approves or rejects test cases.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_TEST_CASES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    if request.approved:
        return await _create_jira(session)
    else:
        return _build_session_response(session, message="Please provide feedback to modify test cases")


@router.post("/step5/modify/{session_id}", response_model=SessionResponse)
async def modify_test_cases(session_id: str, request: ModifyWithLLMRequest):
    """
    Step 5 Modify: LLM modifies test cases based on feedback.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_TEST_CASES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    try:
        prompt = MODIFY_CONTENT_PROMPT.format(
            current_content=json.dumps(session.test_cases, indent=2),
            user_feedback=request.user_feedback
        )
        
        raw_response = generate_with_llama(prompt)
        modified = extract_first_json_object(raw_response)
        
        if modified:
            modified = _normalize_test_cases(modified)
            session.add_modification("step5", "test_cases", session.test_cases, modified)
            session.test_cases = modified
        
        session_manager.update_session(session)
        return _build_session_response(session)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Step 6: Jira Creation (Real Integration)
# =====================================================================

async def _create_jira(session: SessionData) -> SessionResponse:
    """
    Internal: Create Jira tickets using real Jira API.
    Falls back to mock if JIRA_USE_MOCK is true or connection fails.
    """
    from .config import JIRA_USE_MOCK, JIRA_SERVER
    
    session.state = SessionState.CREATING_JIRA
    session_manager.update_session(session)
    
    try:
        if JIRA_USE_MOCK:
            logger.info("Using mock Jira (JIRA_USE_MOCK=true)")
            return await _create_jira_mock(session)
        
        # Try real Jira integration
        try:
            from .jira_service import create_jira_tickets_from_session
            
            session_data = {
                "story_tasks": session.story_tasks,
                "story_description": session.story_description,
                "summary": session.summary,
                "test_cases": session.test_cases
            }
            
            jira_output = create_jira_tickets_from_session(session_data)
            
            session.jira_output = jira_output
            session.state = SessionState.COMPLETED
            session.current_step = 6
            session_manager.update_session(session)
            
            logger.info(f"Jira tickets created successfully: {jira_output.get('story_key')}")
            return _build_session_response(session)
            
        except ConnectionError as e:
            logger.warning(f"Jira connection failed, falling back to mock: {e}")
            return await _create_jira_mock(session)
        except Exception as e:
            logger.error(f"Jira creation failed: {e}")
            raise
        
    except Exception as e:
        session.state = SessionState.ERROR
        session.error_message = str(e)
        session_manager.update_session(session)
        raise HTTPException(status_code=500, detail=str(e))


async def _create_jira_mock(session: SessionData) -> SessionResponse:
    """
    Mock Jira creation for testing without Jira access.
    """
    from datetime import datetime
    import random
    
    # Get data from session
    story = session.story_tasks.get("story", {})
    tasks = session.story_tasks.get("tasks", [])
    test_cases = session.test_cases.get("test_cases", [])
    story_desc = session.story_description or {}
    summary = session.summary or {}
    
    # Generate mock keys
    ticket_num = random.randint(100, 999)
    story_key = f"JGQE-{ticket_num}"
    current_time = datetime.now().isoformat()
    
    # Format acceptance criteria as strings
    ac_list = story.get("acceptance_criteria", [])
    formatted_ac = []
    for i, ac in enumerate(ac_list):
        formatted_ac.append(f"AC {i+1}: {ac}")
    
    # Build tickets array in expected format
    tickets = [
        {
            "id": story_key,
            "summary": story.get("title", story_desc.get("title", "")),
            "description": story.get("description", story_desc.get("description", "")),
            "task": "Story",
            "squad": "Development Team",
            "owner": "Unassigned",
            "status": "To Do",
            "sprint": "PI01 Iteration 5",
            "acceptanceCriteria": formatted_ac
        }
    ]
    
    # Add sub-tasks
    for i, task in enumerate(tasks):
        tickets.append({
            "id": f"{story_key}-{i+1}",
            "summary": task.get("title", ""),
            "description": task.get("description", ""),
            "task": "Sub-task",
            "squad": "Development Team",
            "owner": "Unassigned",
            "status": "To Do",
            "sprint": "PI01 Iteration 5",
            "acceptanceCriteria": [],
            "parentId": story_key,
            "type": task.get("type", ""),
            "priority": task.get("priority", "Medium"),
            "estimate": task.get("estimate", "")
        })
    
    # Build Jira output in expected format
    jira_output = {
        "tickets": tickets,
        "notFound": [],
        # Keep legacy fields for backward compatibility
        "story_key": story_key,
        "story_title": story.get("title", story_desc.get("title", "")),
        "story_description": story.get("description", story_desc.get("description", "")),
        "story_status": "To Do",
        "story_priority": story.get("priority", "Medium"),
        "story_sprint": "PI01 Iteration 5",
        "story_type": "Story",
        "assignee": "Unassigned",
        "reporter": "System Generated",
        "squad": "Development Team",
        "created_date": current_time,
        "updated_date": current_time,
        "acceptance_criteria": formatted_ac,
        "business_requirement": story_desc.get("business_value", summary.get("summary", "")),
        "attachments": [],
        "sub_task_keys": [f"{story_key}-{i+1}" for i in range(len(tasks))],
        "test_case_count": len(test_cases),
        "created_tickets": [{"key": t["id"], "type": t["task"], "title": t["summary"], "status": t["status"], "parent_key": t.get("parentId")} for t in tickets],
        "activities": [
            {"timestamp": current_time, "user": "System", "action": "Created", "details": f"Story {story_key} was created (MOCK)"},
            {"timestamp": current_time, "user": "System", "action": "Sprint Changed", "details": "Added to PI01 Iteration 5"},
            {"timestamp": current_time, "user": "System", "action": "Status Changed", "details": "Status set to To Do"}
        ],
        "comments": [],
        "raw_data": {
            "session_id": session.session_id,
            "problem_statement": session.problem_statement,
            "summary": session.summary,
            "story_description": session.story_description,
            "sdlc_testplan": session.sdlc_testplan,
            "story_tasks": session.story_tasks,
            "test_cases": session.test_cases
        },
        "jira_url": f"https://jira.example.com/browse/{story_key}"
    }
    
    session.jira_output = jira_output
    session.state = SessionState.COMPLETED
    session.current_step = 6
    session_manager.update_session(session)
    
    return _build_session_response(session)


@router.post("/step6/create/{session_id}", response_model=SessionResponse)
async def create_jira_endpoint(session_id: str):
    """
    Step 6: Manually trigger Jira creation (if needed).
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != SessionState.REVIEW_TEST_CASES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {session.state.value}")
    
    return await _create_jira(session)


# =====================================================================
# Legacy Endpoints (for backward compatibility)
# =====================================================================

@router.post("/analyze", response_model=SessionResponse)
async def analyze_problem_legacy(request: ProblemStatementRequest):
    """Legacy endpoint: Creates session and analyzes in one call."""
    session = session_manager.create_session()
    return await analyze_problem(session.session_id, request)


# =====================================================================
# Helper Functions
# =====================================================================

def _build_session_response(session: SessionData, message: str = None) -> SessionResponse:
    """Build a SessionResponse from session data."""
    return SessionResponse(
        session_id=session.session_id,
        state=session.state.value,
        current_step=session.current_step,
        message=message or get_state_message(session.state),
        problem_statement=session.problem_statement,
        skip_sdlc=session.skip_sdlc,
        summary=session.summary,
        story_description=session.story_description,
        sdlc_testplan=session.sdlc_testplan,
        story_tasks=session.story_tasks,
        test_cases=session.test_cases,
        jira_output=session.jira_output,
        error_message=session.error_message
    )


def _get_step_state(session: SessionData, step: int) -> str:
    """Get the state of a specific step."""
    if session.current_step > step:
        return "completed"
    elif session.current_step == step:
        return "in_progress"
    else:
        return "pending"
