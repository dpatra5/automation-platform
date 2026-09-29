"""
Core services for complete Jira SprintGuard workflow.
Session management following the Snapgrid flow diagram.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime


class SessionState(str, Enum):
    """Enum for tracking session states following Snapgrid flow."""
    # Initial state
    AWAITING_PROBLEM = "awaiting_problem"
    
    # Step 1: Problem Analysis
    ANALYZING = "analyzing"
    REVIEW_SUMMARY = "review_summary"
    
    # Step 2: Story Description
    CREATING_STORY_DESC = "creating_story_description"
    REVIEW_STORY_DESC = "review_story_description"
    
    # Step 3: SDLC & Test Plan
    CREATING_SDLC = "creating_sdlc_testplan"
    REVIEW_SDLC = "review_sdlc_testplan"
    
    # Step 4: Story, Sub-tasks, Acceptance Criteria
    CREATING_STORY_TASKS = "creating_story_subtasks"
    REVIEW_STORY_TASKS = "review_story_subtasks"
    
    # Step 5: Manual Test Cases
    CREATING_TEST_CASES = "creating_test_cases"
    REVIEW_TEST_CASES = "review_test_cases"
    
    # Step 6: Jira Creation
    CREATING_JIRA = "creating_jira"
    
    # Final states
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class SessionData:
    """Complete session data for tracking the entire workflow."""
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    state: SessionState = SessionState.AWAITING_PROBLEM
    current_step: int = 1
    skip_sdlc: bool = False
    
    # Step 1: Problem Statement & Summary
    problem_statement: str = ""
    summary: Optional[Dict[str, Any]] = None
    
    # Step 2: Story Description
    story_description: Optional[Dict[str, Any]] = None
    
    # Step 3: SDLC & Test Plan
    sdlc_testplan: Optional[Dict[str, Any]] = None
    
    # Step 4: Story with Sub-tasks & Acceptance Criteria
    story_tasks: Optional[Dict[str, Any]] = None
    
    # Step 5: Manual Test Cases
    test_cases: Optional[Dict[str, Any]] = None
    
    # Step 6: Final Jira Output
    jira_output: Optional[Dict[str, Any]] = None
    
    # Error tracking
    error_message: Optional[str] = None
    
    # History of modifications (for undo/audit)
    modification_history: list = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state.value,
            "current_step": self.current_step,
            "skip_sdlc": self.skip_sdlc,
            "problem_statement": self.problem_statement,
            "summary": self.summary,
            "story_description": self.story_description,
            "sdlc_testplan": self.sdlc_testplan,
            "story_tasks": self.story_tasks,
            "test_cases": self.test_cases,
            "jira_output": self.jira_output,
            "error_message": self.error_message,
            "modification_history": self.modification_history
        }
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()
    
    def add_modification(self, step: str, field: str, old_value: Any, new_value: Any):
        """Track modifications for audit."""
        self.modification_history.append({
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "field": field,
            "action": "modified"
        })


class SessionManager:
    """Manages user sessions for the complete workflow."""
    
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
    
    def create_session(self) -> SessionData:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session = SessionData(session_id=session_id)
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def update_session(self, session: SessionData) -> None:
        """Update a session."""
        session.update_timestamp()
        self._sessions[session.session_id] = session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def get_all_sessions(self) -> Dict[str, SessionData]:
        """Get all sessions (for admin purposes)."""
        return self._sessions
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Clean up sessions older than max_age_hours."""
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0
        sessions_to_remove = []
        
        for session_id, session in self._sessions.items():
            session_time = datetime.fromisoformat(session.updated_at)
            if session_time < cutoff:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self._sessions[session_id]
            removed += 1
        
        return removed


# Global session manager
session_manager = SessionManager()


# Helper functions for state transitions
def get_next_state(current_state: SessionState, approved: bool) -> SessionState:
    """Get the next state based on current state and approval status."""
    state_transitions = {
        # After summary review
        SessionState.REVIEW_SUMMARY: {
            True: SessionState.CREATING_STORY_DESC,  # Approved → create story desc
            False: SessionState.REVIEW_SUMMARY  # Not approved → stay for edit
        },
        # After story description review
        SessionState.REVIEW_STORY_DESC: {
            True: SessionState.CREATING_SDLC,  # Approved → create SDLC
            False: SessionState.REVIEW_STORY_DESC  # Not approved → stay for edit
        },
        # After SDLC review
        SessionState.REVIEW_SDLC: {
            True: SessionState.CREATING_STORY_TASKS,  # Approved → create story tasks
            False: SessionState.REVIEW_SDLC  # Not approved → stay for edit
        },
        # After story tasks review
        SessionState.REVIEW_STORY_TASKS: {
            True: SessionState.CREATING_TEST_CASES,  # Approved → create test cases
            False: SessionState.REVIEW_STORY_TASKS  # Not approved → stay for edit
        },
        # After test cases review
        SessionState.REVIEW_TEST_CASES: {
            True: SessionState.CREATING_JIRA,  # Approved → create Jira
            False: SessionState.REVIEW_TEST_CASES  # Not approved → stay for edit
        },
    }
    
    return state_transitions.get(current_state, {}).get(approved, current_state)


def get_step_number(state: SessionState) -> int:
    """Get the step number for a given state."""
    step_mapping = {
        SessionState.AWAITING_PROBLEM: 1,
        SessionState.ANALYZING: 1,
        SessionState.REVIEW_SUMMARY: 1,
        SessionState.CREATING_STORY_DESC: 2,
        SessionState.REVIEW_STORY_DESC: 2,
        SessionState.CREATING_SDLC: 3,
        SessionState.REVIEW_SDLC: 3,
        SessionState.CREATING_STORY_TASKS: 4,
        SessionState.REVIEW_STORY_TASKS: 4,
        SessionState.CREATING_TEST_CASES: 5,
        SessionState.REVIEW_TEST_CASES: 5,
        SessionState.CREATING_JIRA: 6,
        SessionState.COMPLETED: 6,
        SessionState.ERROR: 0,
    }
    return step_mapping.get(state, 0)


def get_state_message(state: SessionState) -> str:
    """Get a human-readable message for each state."""
    messages = {
        SessionState.AWAITING_PROBLEM: "Please submit your problem statement.",
        SessionState.ANALYZING: "Analyzing your problem statement...",
        SessionState.REVIEW_SUMMARY: "Please review the summary. Approve or edit.",
        SessionState.CREATING_STORY_DESC: "Creating story description...",
        SessionState.REVIEW_STORY_DESC: "Please review the story description. Approve or edit.",
        SessionState.CREATING_SDLC: "Creating SDLC phases and test plan...",
        SessionState.REVIEW_SDLC: "Please review SDLC and test plan. Approve or edit.",
        SessionState.CREATING_STORY_TASKS: "Creating story, sub-tasks, and acceptance criteria...",
        SessionState.REVIEW_STORY_TASKS: "Please review story details. Approve or edit.",
        SessionState.CREATING_TEST_CASES: "Creating manual test cases...",
        SessionState.REVIEW_TEST_CASES: "Please review test cases. Approve or create Jira.",
        SessionState.CREATING_JIRA: "Creating Jira tickets...",
        SessionState.COMPLETED: "All Jira tickets created successfully!",
        SessionState.ERROR: "An error occurred. Please try again."
    }
    return messages.get(state, "")
