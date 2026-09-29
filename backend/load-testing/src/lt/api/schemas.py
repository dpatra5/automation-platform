"""Request and response models for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lt.discover import DiscoveryOptions, LoadPlan

RunStatus = Literal["running", "stopping", "completed", "interrupted", "failed"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Overrides(_Model):
    rps: float | None = Field(default=None, gt=0)
    duration: str | None = Field(default=None, max_length=32)
    workers: int | None = Field(default=None, ge=1, le=1024)
    processes: int | None = Field(default=None, ge=1, le=256)
    max_rps_cap: int | None = Field(default=None, ge=1)
    http2: bool | None = None
    connections: int | None = Field(default=None, ge=1)
    streams: int | None = Field(default=None, ge=1)
    concurrency: int | None = Field(default=None, ge=1)
    events_sample_rate: float | None = Field(default=None, ge=0, le=1)


class ConfigRequest(_Model):
    yaml: str = Field(min_length=1)
    overrides: Overrides = Field(default_factory=Overrides)


class ProfileStepOut(BaseModel):
    duration_s: float
    rate: float
    end_rate: float | None
    name: str | None


class RouteOut(BaseModel):
    name: str
    method: str
    path: str
    weight: float
    tenant: str | None
    checks: int = 0
    extracts: list[str] = Field(default_factory=list)
    think_time: str | None = None


class StageOut(BaseModel):
    duration_s: float
    users: int


class ConfigSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str | None
    base_url: str
    host: str
    model_type: Literal["open", "closed"] = "open"
    peak_rps: float
    effective_cap: int
    duration_s: float
    expected_requests: float
    processes: int
    workers: int
    concurrency_per_process: int
    http2: bool
    profile: list[ProfileStepOut]
    routes: list[RouteOut]
    stages: list[StageOut] = Field(default_factory=list)
    peak_users: int = 0
    iterations: int | None = None
    max_rps: float | None = None
    data_rows: int = 0
    thresholds: int = 0


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: ConfigSummary | None = None


class RunListItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    status: RunStatus
    name: str | None = None
    base_url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    totals: dict[str, int] | None = None
    means: dict[str, float] | None = None
    ratios: dict[str, float] | None = None
    latency_ms: dict[str, float | None] | None = None
    analysis_pass: bool | None = None
    thresholds_pass: bool | None = None
    model_type: str | None = None
    aggregate_total: dict[str, Any] | None = None


class Artifact(BaseModel):
    name: str
    size: int


class Progress(BaseModel):
    elapsed_s: float
    planned_duration_s: float | None


class RunDetail(BaseModel):
    run_id: str
    status: RunStatus
    error: str | None = None
    progress: Progress | None = None
    config: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    artifacts: list[Artifact] = Field(default_factory=list)


class LivePoint(BaseModel):
    second: int
    attempted: int
    accepted: int
    rate_limited: int
    errors: int
    failed: int | None = None
    vus: int | None = None


class Timeseries(BaseModel):
    metrics: list[dict[str, float | None]]
    live: list[LivePoint]
    routes: list[dict[str, Any]]


class LogLine(BaseModel):
    model_config = ConfigDict(extra="allow")
    ts: str | None = None
    level: str | None = None
    msg: str | None = None


class AnalyzeRequest(_Model):
    expected_limit_rps: float | None = Field(default=None, gt=0)
    expected_burst: float | None = Field(default=None, ge=0)
    tolerance: float | None = Field(default=None, gt=0, lt=1)
    fairness_threshold: float | None = Field(default=None, ge=1)


class StopRequest(_Model):
    force: bool = False


class Example(BaseModel):
    name: str
    filename: str
    yaml: str


class JmxImportRequest(_Model):
    jmx: str = Field(min_length=1, max_length=5 * 1024 * 1024)


class JmxImportResult(BaseModel):
    yaml: str
    warnings: list[str]


class DemoServerRequest(_Model):
    port: int = Field(default=8080, ge=0, le=65535)
    rate: float = Field(default=1000.0, gt=0)
    burst: int | None = Field(default=None, ge=1)
    window: str = Field(default="1s", max_length=32)
    algo: Literal["token-bucket", "fixed-window", "sliding-window"] = "token-bucket"
    scope: Literal["global", "per-key"] = "global"
    key_header: str = Field(default="X-API-Key", pattern=r"^[A-Za-z0-9-]{1,64}$")
    latency_ms: float = Field(default=0.0, ge=0, le=60_000)


class DemoServerState(BaseModel):
    running: bool
    base_url: str | None = None
    settings: DemoServerRequest | None = None


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    auth_required: bool


ScanStatus = Literal["discovering", "discovered", "running", "completed", "cancelled", "failed"]
ScanItemStatus = Literal[
    "pending", "running", "completed", "interrupted", "failed", "skipped", "cancelled"
]


class ScanRequest(_Model):
    discovery: DiscoveryOptions
    plan: LoadPlan = Field(default_factory=LoadPlan)
    auto_run: bool = True
    include_unsafe_methods: bool = False


class ScanRunRequest(_Model):
    endpoint_ids: list[str] = Field(min_length=1, max_length=500)
    plan: LoadPlan = Field(default_factory=LoadPlan)


class DiscoveredEndpoint(BaseModel):
    id: str
    method: str
    base_url: str
    path: str
    template: str
    resource_type: str
    in_scope: bool
    sensitive: bool
    safe: bool
    count: int
    status: int | None
    content_type: str | None
    has_body: bool
    pages: list[str]


class ScanItem(BaseModel):
    name: str
    endpoint_ids: list[str]
    status: ScanItemStatus = "pending"
    run_id: str | None = None
    error: str | None = None
    accepted_rps: float | None = None
    ratio_429: float | None = None
    p99_ms: float | None = None
    analysis_pass: bool | None = None


class ScanSummary(BaseModel):
    id: str
    url: str
    status: ScanStatus
    created_at: str
    error: str | None = None
    endpoints_found: int = 0
    items_total: int = 0
    items_done: int = 0


class ScanOptionsOut(BaseModel):
    max_pages: int
    max_depth: int
    wait_ms: int
    scope: list[str]
    header_names: list[str]


class ScanDetail(ScanSummary):
    options: ScanOptionsOut
    pages: list[str] = Field(default_factory=list)
    discovery_errors: list[str] = Field(default_factory=list)
    out_of_scope_hosts: dict[str, int] = Field(default_factory=dict)
    endpoints: list[DiscoveredEndpoint] = Field(default_factory=list)
    plan: LoadPlan | None = None
    items: list[ScanItem] = Field(default_factory=list)
