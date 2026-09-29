import os
from dotenv import load_dotenv
from jira import JIRA

load_dotenv()

jira = JIRA(
    server=os.getenv("JIRA_SERVER", "https://jira.jnj.com"),
    token_auth=os.environ["JIRA_TOKEN"],
)

print("Connected as:", jira.myself()['displayName'])

# Payload data
tickets_data = {
    "tickets": [
        {
            "id": "JGQE-254",
            "summary": "Implement SQL Assistant",
            "description": "Develop a user-friendly SQL Assistant that simplifies data analysis for business users by converting natural language queries into optimized SQL queries, executing securely, and presenting results with explanations and visualizations.",
            "task": "Story",
            "acceptanceCriteria": [
                "AC 1: Business Analyst - The SQL Assistant should provide a user-friendly interface for querying and visualizing data - They can quickly identify trends and insights from their data",
                "AC 2: Data Scientist - The SQL Assistant should ensure secure execution of queries using AI-driven optimization techniques - Data scientists can focus on analyzing insights rather than debugging queries",
                "AC 3: DevOps Engineer - The SQL Assistant should offer real-time data updates and analytics capabilities - Real-time analytics enable faster decision-making",
                "AC 4: User Experience Designer - The SQL Assistant should improve data accuracy by providing clear explanations and visualizations - Clear explanations and visualizations enhance user engagement and satisfaction",
                "AC 5: Security Specialist - The SQL Assistant should reduce query time by up to 90% - Reduced query times lead to increased productivity and reduced costs"
            ]
        },
        {"id": "JGQE-254-1", "summary": "Design User Interface", "description": "Create a visually appealing and intuitive interface for querying and visualizing data", "task": "Sub-task", "parentId": "JGQE-254", "priority": "Medium", "estimate": "8"},
        {"id": "JGQE-254-2", "summary": "Implement Data Visualization", "description": "Develop interactive charts and graphs to present data in a clear and concise manner", "task": "Sub-task", "parentId": "JGQE-254", "priority": "Low", "estimate": "4"},
        {"id": "JGQE-254-3", "summary": "Optimize Query Execution", "description": "Use AI-driven optimization techniques to improve query performance and reduce latency", "task": "Sub-task", "parentId": "JGQE-254", "priority": "High", "estimate": "10"},
        {"id": "JGQE-254-4", "summary": "Integrate Real-Time Analytics", "description": "Develop APIs to fetch real-time data and update the dashboard in real-time", "task": "Sub-task", "parentId": "JGQE-254", "priority": "Medium", "estimate": "6"},
        {"id": "JGQE-254-5", "summary": "Enhance Security Features", "description": "Implement authentication and authorization mechanisms to protect sensitive data", "task": "Sub-task", "parentId": "JGQE-254", "priority": "High", "estimate": "12"},
        {"id": "JGQE-254-6", "summary": "Test and Validate", "description": "Conduct thorough testing and validation to ensure the SQL Assistant meets the required standards", "task": "Sub-task", "parentId": "JGQE-254", "priority": "Low", "estimate": "9"},
        {"id": "JGQE-254-7", "summary": "Document the API", "description": "Create comprehensive documentation for the SQL Assistant API", "task": "Sub-task", "parentId": "JGQE-254", "priority": "Low", "estimate": "5"},
    ]
}

PROJECT_KEY = "JGQE"

def format_description_with_acceptance_criteria(description, acceptance_criteria):
    """Format description with acceptance criteria included"""
    if not acceptance_criteria:
        return description
    
    ac_text = "\n\n*Acceptance Criteria:*\n"
    for ac in acceptance_criteria:
        ac_text += f"* {ac}\n"
    
    return description + ac_text

def create_story_and_subtasks():
    """Create the main story and all subtasks"""
    
    # Find the main story
    story_data = None
    subtasks_data = []
    
    for ticket in tickets_data["tickets"]:
        if ticket["task"] == "Story":
            story_data = ticket
        elif ticket["task"] == "Sub-task":
            subtasks_data.append(ticket)
    
    if not story_data:
        print("No story found in payload!")
        return
    
    # Create the main story with acceptance criteria in description
    story_description = format_description_with_acceptance_criteria(
        story_data["description"],
        story_data.get("acceptanceCriteria", [])
    )
    
    print(f"\nCreating Story: {story_data['summary']}")
    
    story = jira.create_issue(
        project=PROJECT_KEY,
        summary=story_data["summary"],
        description=story_description,
        issuetype={"name": "Story"}
    )
    
    print(f"✓ Story created: {story.key} - {story_data['summary']}")
    
    # Create subtasks under the story
    print(f"\nCreating {len(subtasks_data)} subtasks...")
    
    for subtask_data in subtasks_data:
        subtask = jira.create_issue(
            project=PROJECT_KEY,
            summary=subtask_data["summary"],
            description=subtask_data["description"],
            issuetype={"name": "Sub-task"},
            parent={"key": story.key}
        )
        print(f"  ✓ Sub-task created: {subtask.key} - {subtask_data['summary']}")
    
    print(f"\n✓ Done! Created story {story.key} with {len(subtasks_data)} subtasks")
    return story

if __name__ == "__main__":
    create_story_and_subtasks()