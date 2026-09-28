import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    Enum,
    Text,
    Boolean,
)
from sqlalchemy.orm import relationship
from app.models.base import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ActionEnum(str, enum.Enum):
    # Navigation
    navigate = "navigate"
    reload = "reload"
    go_back = "go_back"
    go_forward = "go_forward"
    # Pointer
    click = "click"
    dblclick = "dblclick"
    right_click = "right_click"
    hover = "hover"
    drag = "drag"
    scroll = "scroll"
    # Input
    fill = "fill"
    type = "type"
    press_key = "press_key"
    select = "select"
    check = "check"
    uncheck = "uncheck"
    upload = "upload"
    # Synchronisation
    wait = "wait"
    wait_for_selector = "wait_for_selector"
    wait_for_url = "wait_for_url"
    # The flow continued in another tab. `value` holds that tab's URL.
    switch_tab = "switch_tab"
    # Verification
    assert_ = "assert"


class SelectorStrategyEnum(str, enum.Enum):
    test_id = "test_id"
    role = "role"
    text = "text"
    css = "css"
    xpath = "xpath"


class StatusEnum(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    error = "error"


class EvidenceTypeEnum(str, enum.Enum):
    screenshot = "screenshot"
    video = "video"
    trace = "trace"
    console_log = "console_log"
    network_log = "network_log"
    report = "report"


class JiraSyncEnum(str, enum.Enum):
    """Outcome of pushing a finished run to Jira. Never blocks the run."""

    skipped = "skipped"
    posted = "posted"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    description = Column(String, nullable=True)
    # Optional Jira "Test Execution" issue, e.g. JGQE-23122. Verified against
    # Jira before it is stored; finished runs comment on it.
    jira_key = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    test_cases = relationship("TestCase", back_populates="project")
    auth_profiles = relationship("AuthProfile", back_populates="project")


class AuthProfile(Base):
    __tablename__ = "auth_profiles"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    storage_state_json = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="auth_profiles")


class TestCase(Base):
    __tablename__ = "test_cases"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="test_cases")
    # lazy="selectin": these are always serialised by the API, and lazy loading
    # them during response serialisation blows up with MissingGreenlet on async sessions.
    # Exit criteria sort last: they check the state the flow was meant to reach.
    steps = relationship(
        "Step",
        back_populates="test_case",
        order_by="(Step.is_exit_criteria, Step.order_index)",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    # Runs are never serialised with the test case; let the DB cascade them
    # instead of loading them (a lazy load here would raise MissingGreenlet).
    runs = relationship("TestRun", back_populates="test_case", passive_deletes=True)


class Step(Base):
    __tablename__ = "steps"
    id = Column(String, primary_key=True, default=generate_uuid)
    test_case_id = Column(String, ForeignKey("test_cases.id", ondelete="CASCADE"))
    order_index = Column(Integer, nullable=False)
    action = Column(Enum(ActionEnum), nullable=False)
    selector = Column(String, nullable=False)
    selector_strategy = Column(Enum(SelectorStrategyEnum), nullable=False)
    value = Column(String, nullable=True)
    assertion_type = Column(String, nullable=True)
    expected_value = Column(String, nullable=True)
    # Set when the element lives inside an iframe rather than the main page.
    # Apps that stream their whole UI into a frame - Windchill, Veeva Vault -
    # are otherwise unreplayable, because the selector never resolves.
    frame_url = Column(String, nullable=True)
    # What the element was, as JSON: tag, role, label, text and other ways to
    # reach it. A selector says where an element sat, which the next release
    # can change; this says what it is, so replay can find it again.
    element_meta = Column(Text, nullable=True)
    # Exit criteria are checks that decide whether the flow finished in the
    # state it should. They run after every ordinary step, in their own order.
    is_exit_criteria = Column(Boolean, nullable=False, default=False)

    test_case = relationship("TestCase", back_populates="steps")


class RunBatch(Base):
    """Several test cases replayed one after another, reported as one result."""

    __tablename__ = "run_batches"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    name = Column(String, nullable=False)
    status = Column(Enum(StatusEnum), default=StatusEnum.pending)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    trigger_source = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    # Consolidated HTML report, written once every run in the batch is done.
    report_path = Column(String, nullable=True)
    jira_issue_key = Column(String, nullable=True)
    jira_status = Column(Enum(JiraSyncEnum), nullable=True)
    jira_error = Column(Text, nullable=True)

    runs = relationship(
        "TestRun",
        back_populates="batch",
        order_by="TestRun.batch_order",
        lazy="selectin",
        passive_deletes=True,
    )


class TestRun(Base):
    __tablename__ = "test_runs"
    id = Column(String, primary_key=True, default=generate_uuid)
    test_case_id = Column(String, ForeignKey("test_cases.id", ondelete="CASCADE"))
    status = Column(Enum(StatusEnum), default=StatusEnum.pending)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    trigger_source = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    # Set when the run is part of a sequential batch.
    batch_id = Column(
        String, ForeignKey("run_batches.id", ondelete="SET NULL"), nullable=True
    )
    batch_order = Column(Integer, nullable=True)
    # Result of reporting this run to Jira, kept so the dashboard can show a
    # failed push without the run itself being marked as failed.
    jira_issue_key = Column(String, nullable=True)
    jira_status = Column(Enum(JiraSyncEnum), nullable=True)
    jira_error = Column(Text, nullable=True)

    test_case = relationship("TestCase", back_populates="runs")
    batch = relationship("RunBatch", back_populates="runs")
    # Always serialised by RunResponse -> must be eager, see TestCase.steps.
    step_results = relationship(
        "StepResult",
        back_populates="test_run",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    evidences = relationship(
        "Evidence",
        back_populates="test_run",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class StepResult(Base):
    __tablename__ = "step_results"
    id = Column(String, primary_key=True, default=generate_uuid)
    test_run_id = Column(String, ForeignKey("test_runs.id", ondelete="CASCADE"))
    step_id = Column(String, ForeignKey("steps.id", ondelete="CASCADE"))
    status = Column(Enum(StatusEnum), nullable=False)
    duration_ms = Column(Integer, nullable=False)
    screenshot_path = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    test_run = relationship("TestRun", back_populates="step_results")
    step = relationship("Step")


class Evidence(Base):
    __tablename__ = "evidences"
    id = Column(String, primary_key=True, default=generate_uuid)
    test_run_id = Column(String, ForeignKey("test_runs.id", ondelete="CASCADE"))
    type = Column(Enum(EvidenceTypeEnum), nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    test_run = relationship("TestRun", back_populates="evidences")
