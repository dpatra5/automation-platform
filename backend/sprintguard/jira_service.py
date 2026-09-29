"""
Jira integration service for creating stories and subtasks.
Connects to Jira Server using personal access token authentication.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from jira import JIRA
from jira.exceptions import JIRAError

from .config import JIRA_SERVER, JIRA_TOKEN, JIRA_PROJECT_KEY

logger = logging.getLogger(__name__)


@dataclass
class JiraTicketResult:
    """Result of a Jira ticket creation."""
    key: str
    summary: str
    issue_type: str
    status: str
    url: str
    parent_key: Optional[str] = None


class JiraService:
    """Service for creating Jira stories and subtasks."""
    
    def __init__(self):
        self._jira: Optional[JIRA] = None
        self._connected = False
    
    def connect(self) -> bool:
        """Establish connection to Jira server."""
        try:
            self._jira = JIRA(
                server=JIRA_SERVER,
                token_auth=JIRA_TOKEN
            )
            # Test connection
            user = self._jira.myself()
            logger.info(f"Connected to Jira as: {user.get('displayName', 'Unknown')}")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Jira: {e}")
            self._connected = False
            return False
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Jira."""
        return self._connected and self._jira is not None
    
    def _ensure_connected(self):
        """Ensure connection is established."""
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Unable to connect to Jira server")
    
    def _format_description_with_acceptance_criteria(
        self, 
        description: str, 
        acceptance_criteria: List[str]
    ) -> str:
        """Format description with acceptance criteria in Jira wiki markup."""
        if not acceptance_criteria:
            return description
        
        ac_text = "\n\n*Acceptance Criteria:*\n"
        for ac in acceptance_criteria:
            ac_text += f"* {ac}\n"
        
        return description + ac_text
    
    def create_story(
        self,
        summary: str,
        description: str,
        acceptance_criteria: List[str] = None,
        project_key: str = None
    ) -> JiraTicketResult:
        """
        Create a Story in Jira.
        
        Args:
            summary: Story title/summary
            description: Story description
            acceptance_criteria: List of acceptance criteria
            project_key: Jira project key (defaults to JIRA_PROJECT_KEY from config)
        
        Returns:
            JiraTicketResult with the created story details
        """
        self._ensure_connected()
        
        project = project_key or JIRA_PROJECT_KEY
        
        # Format description with acceptance criteria
        full_description = self._format_description_with_acceptance_criteria(
            description,
            acceptance_criteria or []
        )
        
        logger.info(f"Creating Story in project {project}: {summary}")
        
        try:
            story = self._jira.create_issue(
                project=project,
                summary=summary,
                description=full_description,
                issuetype={"name": "Story"}
            )
            
            result = JiraTicketResult(
                key=story.key,
                summary=summary,
                issue_type="Story",
                status="To Do",
                url=f"{JIRA_SERVER}/browse/{story.key}"
            )
            
            logger.info(f"Story created: {story.key}")
            return result
            
        except JIRAError as e:
            logger.error(f"Failed to create story: {e}")
            raise
    
    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: str,
        project_key: str = None
    ) -> JiraTicketResult:
        """
        Create a Sub-task under a parent story.
        
        Args:
            parent_key: The key of the parent story (e.g., "JGQE-123")
            summary: Sub-task title/summary
            description: Sub-task description
            project_key: Jira project key (defaults to JIRA_PROJECT_KEY from config)
        
        Returns:
            JiraTicketResult with the created sub-task details
        """
        self._ensure_connected()
        
        project = project_key or JIRA_PROJECT_KEY
        
        logger.info(f"Creating Sub-task under {parent_key}: {summary}")
        
        try:
            subtask = self._jira.create_issue(
                project=project,
                summary=summary,
                description=description,
                issuetype={"name": "Sub-task"},
                parent={"key": parent_key}
            )
            
            result = JiraTicketResult(
                key=subtask.key,
                summary=summary,
                issue_type="Sub-task",
                status="To Do",
                url=f"{JIRA_SERVER}/browse/{subtask.key}",
                parent_key=parent_key
            )
            
            logger.info(f"Sub-task created: {subtask.key}")
            return result
            
        except JIRAError as e:
            logger.error(f"Failed to create sub-task: {e}")
            raise
    
    def create_story_with_subtasks(
        self,
        story_data: Dict[str, Any],
        subtasks_data: List[Dict[str, Any]],
        project_key: str = None
    ) -> Dict[str, Any]:
        """
        Create a complete story with all its subtasks.
        
        Args:
            story_data: Dictionary with story details:
                - summary: Story title
                - description: Story description
                - acceptance_criteria: List of acceptance criteria
            subtasks_data: List of dictionaries with subtask details:
                - summary: Subtask title
                - description: Subtask description
        
        Returns:
            Dictionary with created tickets info
        """
        self._ensure_connected()
        
        project = project_key or JIRA_PROJECT_KEY
        created_tickets = []
        
        # Create the main story
        story_result = self.create_story(
            summary=story_data.get("summary", story_data.get("title", "")),
            description=story_data.get("description", ""),
            acceptance_criteria=story_data.get("acceptance_criteria", []),
            project_key=project
        )
        
        created_tickets.append({
            "key": story_result.key,
            "type": story_result.issue_type,
            "title": story_result.summary,
            "status": story_result.status,
            "url": story_result.url,
            "parent_key": None
        })
        
        # Create all subtasks
        for subtask_data in subtasks_data:
            try:
                subtask_result = self.create_subtask(
                    parent_key=story_result.key,
                    summary=subtask_data.get("summary", subtask_data.get("title", "")),
                    description=subtask_data.get("description", ""),
                    project_key=project
                )
                
                created_tickets.append({
                    "key": subtask_result.key,
                    "type": subtask_result.issue_type,
                    "title": subtask_result.summary,
                    "status": subtask_result.status,
                    "url": subtask_result.url,
                    "parent_key": subtask_result.parent_key
                })
            except Exception as e:
                logger.error(f"Failed to create subtask '{subtask_data.get('summary', '')}': {e}")
                # Continue with remaining subtasks even if one fails
        
        return {
            "story_key": story_result.key,
            "story_url": story_result.url,
            "created_tickets": created_tickets,
            "subtask_count": len(created_tickets) - 1  # Exclude the story itself
        }


# Global Jira service instance
_jira_service: Optional[JiraService] = None


def get_jira_service() -> JiraService:
    """Get the global Jira service instance."""
    global _jira_service
    if _jira_service is None:
        _jira_service = JiraService()
    return _jira_service


def create_jira_tickets_from_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create Jira tickets from session data.
    
    This is the main entry point for creating Jira tickets from the workflow session.
    
    Args:
        session_data: Dictionary containing:
            - story_tasks: Dict with 'story' and 'tasks' keys
            - story_description: Dict with story description details
            - summary: Dict with problem analysis summary
            - test_cases: Dict with test cases (optional)
    
    Returns:
        Dictionary with Jira output in the expected format
    """
    from datetime import datetime
    
    jira_service = get_jira_service()
    
    story_tasks = session_data.get("story_tasks", {})
    story_desc = session_data.get("story_description", {})
    summary = session_data.get("summary", {})
    test_cases = session_data.get("test_cases", {})
    
    # Extract story data
    story = story_tasks.get("story", {})
    tasks = story_tasks.get("tasks", [])
    
    # Prepare story data for creation
    story_data = {
        "summary": story.get("title", story_desc.get("title", "")),
        "description": story.get("description", story_desc.get("description", "")),
        "acceptance_criteria": story.get("acceptance_criteria", [])
    }
    
    # Prepare subtasks data
    subtasks_data = [
        {
            "summary": task.get("title", ""),
            "description": task.get("description", "")
        }
        for task in tasks
    ]
    
    # Create the tickets in Jira
    result = jira_service.create_story_with_subtasks(story_data, subtasks_data)
    
    current_time = datetime.now().isoformat()
    story_key = result["story_key"]
    
    # Format acceptance criteria
    ac_list = story.get("acceptance_criteria", [])
    formatted_ac = [f"AC {i+1}: {ac}" for i, ac in enumerate(ac_list)]
    
    # Build tickets array in expected format (matching frontend expectations)
    tickets = []
    for ticket in result["created_tickets"]:
        ticket_data = {
            "id": ticket["key"],
            "summary": ticket["title"],
            "description": "",
            "task": ticket["type"],
            "squad": "Development Team",
            "owner": "Unassigned",
            "status": ticket["status"],
            "sprint": "PI01 Iteration 5",
            "acceptanceCriteria": formatted_ac if ticket["type"] == "Story" else [],
            "url": ticket["url"]
        }
        if ticket["parent_key"]:
            ticket_data["parentId"] = ticket["parent_key"]
        tickets.append(ticket_data)
    
    # Add additional details to subtask tickets
    for i, task in enumerate(tasks):
        if i + 1 < len(tickets):  # Skip story (index 0)
            tickets[i + 1]["description"] = task.get("description", "")
            tickets[i + 1]["type"] = task.get("type", "")
            tickets[i + 1]["priority"] = task.get("priority", "Medium")
            tickets[i + 1]["estimate"] = task.get("estimate", "")
    
    # Build complete Jira output
    jira_output = {
        "tickets": tickets,
        "notFound": [],
        # Legacy fields for backward compatibility
        "story_key": story_key,
        "story_title": story_data["summary"],
        "story_description": story_data["description"],
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
        "sub_task_keys": [t["key"] for t in result["created_tickets"] if t["type"] == "Sub-task"],
        "test_case_count": len(test_cases.get("test_cases", [])),
        "created_tickets": result["created_tickets"],
        "activities": [
            {"timestamp": current_time, "user": "System", "action": "Created", "details": f"Story {story_key} was created in Jira"},
            {"timestamp": current_time, "user": "System", "action": "Sub-tasks Created", "details": f"Created {result['subtask_count']} sub-tasks"},
        ],
        "comments": [],
        "jira_url": result["story_url"]
    }
    
    return jira_output
