"""Pydantic models shared by the API, executor, runner and importers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
BodyMode = Literal["none", "json", "text", "xml", "form"]
AuthType = Literal["none", "bearer", "basic", "api_key"]
AssertionSource = Literal["status", "response_time", "header", "json", "body", "json_schema"]
Operator = Literal[
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "exists",
    "not_exists",
    "lt",
    "lte",
    "gt",
    "gte",
    "matches",
    "type_is",
]
ExtractionSource = Literal["json", "header", "regex", "status"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class KeyValue(BaseModel):
    key: str = ""
    value: str = ""
    enabled: bool = True


class Variable(KeyValue):
    secret: bool = False


class Body(BaseModel):
    mode: BodyMode = "none"
    content: str = ""
    form: list[KeyValue] = Field(default_factory=list)


class Auth(BaseModel):
    type: AuthType = "none"
    token: str = ""
    username: str = ""
    password: str = ""
    key: str = ""
    value: str = ""
    location: Literal["header", "query"] = "header"


class Assertion(BaseModel):
    source: AssertionSource = "status"
    property: str = ""
    operator: Operator = "equals"
    expected: str = ""
    enabled: bool = True


class Extraction(BaseModel):
    variable: str = ""
    source: ExtractionSource = "json"
    property: str = ""
    enabled: bool = True


class RequestSettings(BaseModel):
    timeout_ms: int = Field(30_000, ge=100, le=300_000)
    follow_redirects: bool = True
    verify_tls: bool = True


class RequestSpec(BaseModel):
    method: Method = "GET"
    url: str = Field("", max_length=8192)
    params: list[KeyValue] = Field(default_factory=list)
    headers: list[KeyValue] = Field(default_factory=list)
    body: Body = Field(default_factory=Body)
    auth: Auth = Field(default_factory=Auth)
    assertions: list[Assertion] = Field(default_factory=list)
    extractions: list[Extraction] = Field(default_factory=list)
    settings: RequestSettings = Field(default_factory=RequestSettings)
    description: str = ""


# --- collections & environments -------------------------------------------------


class RequestItemIn(RequestSpec):
    name: Name


class RequestItemOut(RequestItemIn):
    id: int
    collection_id: int
    position: int
    updated_at: datetime


class CollectionIn(BaseModel):
    name: Name
    description: str = ""
    variables: list[Variable] = Field(default_factory=list)


class CollectionSummary(BaseModel):
    id: int
    name: str
    description: str
    request_count: int
    updated_at: datetime


class CollectionOut(CollectionIn):
    id: int
    updated_at: datetime
    requests: list[RequestItemOut]


class ReorderIn(BaseModel):
    request_ids: list[int]


class EnvironmentIn(BaseModel):
    name: Name
    variables: list[Variable] = Field(default_factory=list)


class EnvironmentOut(EnvironmentIn):
    id: int
    updated_at: datetime


class CollectionExport(BaseModel):
    format: Literal["apitest-collection"] = "apitest-collection"
    version: int = 1
    name: Name
    description: str = ""
    variables: list[Variable] = Field(default_factory=list)
    requests: list[RequestItemIn] = Field(default_factory=list)


# --- execution ------------------------------------------------------------------


class ExecuteIn(BaseModel):
    request: RequestSpec
    collection_id: int | None = None
    environment_id: int | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class ResolvedRequest(BaseModel):
    method: str
    url: str
    headers: list[tuple[str, str]] = Field(default_factory=list)
    body: str | None = None


class ResponseData(BaseModel):
    status: int
    reason: str = ""
    http_version: str = ""
    headers: list[tuple[str, str]] = Field(default_factory=list)
    body: str = ""
    body_truncated: bool = False
    is_binary: bool = False
    size_bytes: int = 0
    elapsed_ms: float = 0.0
    content_type: str = ""


class AssertionResult(BaseModel):
    assertion: Assertion
    passed: bool
    actual: str | None = None
    message: str = ""


class ExtractionResult(BaseModel):
    variable: str
    value: str | None = None
    ok: bool
    message: str = ""


class ExecutionResult(BaseModel):
    request: ResolvedRequest
    response: ResponseData | None = None
    error: str | None = None
    assertions: list[AssertionResult] = Field(default_factory=list)
    extractions: list[ExtractionResult] = Field(default_factory=list)
    extracted: dict[str, str] = Field(default_factory=dict)
    unresolved: list[str] = Field(default_factory=list)
    passed: bool


# --- runs -----------------------------------------------------------------------


class RunIn(BaseModel):
    collection_id: int
    environment_id: int | None = None
    request_ids: list[int] | None = None
    iterations: int = Field(1, ge=1, le=100)
    data: str = Field("", max_length=1_000_000)
    stop_on_failure: bool = False
    delay_ms: int = Field(0, ge=0, le=60_000)


class RunStep(BaseModel):
    iteration: int
    request_id: int | None
    request_name: str
    result: ExecutionResult


class RunTotals(BaseModel):
    iterations: int
    requests: int
    passed: int
    failed: int
    errors: int
    assertions_total: int
    assertions_passed: int
    assertions_failed: int
    avg_response_ms: float | None
    duration_ms: float


class RunSummary(BaseModel):
    id: int
    collection_id: int | None
    collection_name: str
    environment_name: str | None
    status: Literal["passed", "failed"]
    started_at: datetime
    finished_at: datetime
    totals: RunTotals


class RunDetail(RunSummary):
    steps: list[RunStep]


# --- import & misc --------------------------------------------------------------


class ImportIn(BaseModel):
    content: str = Field(min_length=1, max_length=10_000_000)
    format: Literal["auto", "curl", "openapi", "postman", "native"] = "auto"
    name: str | None = Field(None, max_length=200)


class ImportOut(BaseModel):
    collection: CollectionSummary
    format: str
    request_count: int
    warnings: list[str]


class Health(BaseModel):
    status: str
    version: str
    auth_required: bool
