"""Configuration schema (pydantic), YAML loading, overrides, and safety guardrails."""

from __future__ import annotations

import csv
import io
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from lt.utils import jsonpath
from lt.utils.time import parse_duration, parse_think_time

ABSOLUTE_MAX_RPS = 100_000
ABSOLUTE_MAX_USERS = 100_000
MAX_DATA_BYTES = 50 * 1024 * 1024

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
Duration = Annotated[float, BeforeValidator(parse_duration)]

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigError(ValueError):
    """Raised when a configuration file cannot be loaded or is invalid."""


class SafetyError(ValueError):
    """Raised when a configuration violates safety guardrails."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileStep(_Base):
    duration: Duration
    rate: float = Field(ge=0)
    end_rate: float | None = Field(default=None, ge=0)
    name: str | None = None

    @field_validator("duration")
    @classmethod
    def _positive_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration must be > 0")
        return v

    @property
    def final_rate(self) -> float:
        return self.rate if self.end_rate is None else self.end_rate

    @property
    def peak_rate(self) -> float:
        return max(self.rate, self.final_rate)

    @property
    def expected_events(self) -> float:
        return (self.rate + self.final_rate) / 2.0 * self.duration


class SafetyConfig(_Base):
    allowlist: list[str] = Field(default_factory=list)
    max_rps_cap: int = Field(default=1000, gt=0, le=ABSOLUTE_MAX_RPS)
    max_users_cap: int = Field(default=1000, gt=0, le=ABSOLUTE_MAX_USERS)
    require_allowlist: bool = True


class StageConfig(_Base):
    """Ramp linearly from the previous stage's users to ``users`` over ``duration`` (0 = jump)."""

    duration: Duration
    users: int = Field(ge=0, le=ABSOLUTE_MAX_USERS)


def _think_time_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    parse_think_time(text)
    return text


ThinkTime = Annotated[str | None, BeforeValidator(_think_time_value)]


class ModelConfig(_Base):
    type: Literal["open", "closed"] = "open"
    workers: int = Field(default=4, ge=1, le=1024, description="scheduler shards (open model)")
    processes: int = Field(default=1, ge=1, le=256)
    seed: int = 0
    use_uvloop: bool = True
    # Open model: arrival-rate profile (requests/second).
    profile: list[ProfileStep] = Field(default_factory=list)
    # Closed model: virtual users like a JMeter Thread Group. users/ramp_up/duration/ramp_down
    # are shorthand that is expanded into ``stages``.
    users: int | None = Field(default=None, ge=1, le=ABSOLUTE_MAX_USERS)
    ramp_up: Duration | None = None
    duration: Duration | None = None
    ramp_down: Duration | None = None
    stages: list[StageConfig] = Field(default_factory=list)
    iterations: int | None = Field(default=None, ge=1, description="per virtual user (loop count)")
    max_rps: float | None = Field(default=None, gt=0, description="throughput shaping, all users")
    think_time: ThinkTime = None

    @model_validator(mode="after")
    def _check(self) -> ModelConfig:
        if self.type == "open":
            closed_only = [
                name
                for name in ("users", "ramp_up", "duration", "ramp_down", "iterations")
                + ("max_rps", "think_time")
                if getattr(self, name) is not None
            ] + (["stages"] if self.stages else [])
            if closed_only:
                raise ValueError(f"{', '.join(closed_only)} require model.type: closed")
            if not self.profile:
                raise ValueError("profile must contain at least one step")
            if not any(step.peak_rate > 0 for step in self.profile):
                raise ValueError("profile must contain at least one step with rate > 0")
            if self.processes > self.workers:
                raise ValueError("workers (total shards) must be >= processes")
            return self

        if self.profile:
            raise ValueError("profile is for model.type: open; use users + duration or stages")
        if self.users is not None:
            if self.stages:
                raise ValueError("use either users/ramp_up/duration or stages, not both")
            if not self.duration:
                raise ValueError("duration is required with users (how long to hold the load)")
            stages = [StageConfig(duration=self.ramp_up or 0.0, users=self.users)]
            stages.append(StageConfig(duration=self.duration, users=self.users))
            if self.ramp_down:
                stages.append(StageConfig(duration=self.ramp_down, users=0))
            # Normalised so a dumped config re-validates to the same plan.
            self.stages = stages
            self.users = self.ramp_up = self.duration = self.ramp_down = None
        elif any(v is not None for v in (self.ramp_up, self.duration, self.ramp_down)):
            raise ValueError("ramp_up/duration/ramp_down need users")
        if not self.stages:
            raise ValueError("closed model needs users + duration, or stages")
        if not any(s.users > 0 for s in self.stages):
            raise ValueError("at least one stage needs users > 0")
        if self.total_duration <= 0:
            raise ValueError("stages must add up to a duration > 0")
        return self

    @property
    def is_closed(self) -> bool:
        return self.type == "closed"

    @property
    def total_duration(self) -> float:
        steps = self.stages if self.is_closed else self.profile
        return sum(step.duration for step in steps)

    @property
    def peak_rate(self) -> float:
        if self.is_closed:
            return self.max_rps or 0.0
        return max(step.peak_rate for step in self.profile)

    @property
    def expected_events(self) -> float:
        if self.is_closed:
            return 0.0
        return sum(step.expected_events for step in self.profile)

    @property
    def peak_users(self) -> int:
        return max((s.users for s in self.stages), default=0)

    def users_at(self, t: float) -> int:
        """Target virtual users at ``t`` seconds (users start like JMeter: first one at t=0)."""
        previous, start = 0, 0.0
        for stage in self.stages:
            end = start + stage.duration
            if t < end:
                frac = (t - start) / stage.duration if stage.duration > 0 else 1.0
                value = previous + (stage.users - previous) * frac
                return max(0, math.ceil(value - 1e-9))
            previous, start = stage.users, end
        return self.stages[-1].users if self.stages else 0


class HttpConfig(_Base):
    http2: bool = True
    max_connections: int = Field(default=100, ge=1)
    max_keepalive: int = Field(default=100, ge=0)
    max_streams: int = Field(default=100, ge=1, description="HTTP/2 streams per connection")
    client_shards: int | None = Field(
        default=None, ge=1, description="independent client pools (default: connections/4)"
    )
    concurrency: int = Field(default=512, ge=1, description="request workers per process")
    queue_size: int = Field(default=20_000, ge=1)
    connect_timeout: Duration = 5.0
    read_timeout: Duration = 10.0
    keepalive_expiry: Duration = 30.0
    verify_tls: bool = True
    trust_env: bool = Field(default=False, description="honour HTTP(S)_PROXY / SSL_CERT_* env")
    follow_redirects: bool = False
    cookies: bool = Field(default=True, description="per-virtual-user cookie jar (closed model)")
    warmup_requests: int = Field(default=0, ge=0)
    warmup_path: str | None = None

    @property
    def effective_concurrency(self) -> int:
        per_conn = self.max_streams if self.http2 else 1
        return max(1, min(self.concurrency, self.max_connections * per_conn))

    @property
    def effective_client_shards(self) -> int:
        shards = self.client_shards or -(-self.max_connections // 4)
        return max(1, min(shards, self.max_connections))


class AssertionsConfig(_Base):
    """Response checks; a failing check marks the sample as failed (JMeter assertions)."""

    max_ms: float | None = Field(default=None, gt=0, description="duration assertion")
    body_contains: list[str] = Field(default_factory=list)
    body_not_contains: list[str] = Field(default_factory=list)
    jsonpath: dict[str, Any] = Field(
        default_factory=dict, description='JSON path -> expected value; "*" = must exist'
    )

    @field_validator("jsonpath")
    @classmethod
    def _paths(cls, v: dict[str, Any]) -> dict[str, Any]:
        for path in v:
            jsonpath.parse(path)
        return v


class RouteConfig(_Base):
    name: str = Field(min_length=1)
    method: HttpMethod = "GET"
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | list[Any] | str | None = None
    # None: 2xx/3xx succeed (plus 429 in the open model, where limits are under test).
    expect_status: list[int] | None = None
    weight: float = Field(default=1.0, gt=0)
    tenant: str | None = None
    assertions: AssertionsConfig = Field(default_factory=AssertionsConfig)
    # variable -> "$.json.path" | "regex:pattern(with group)" | "header:Name" (closed model)
    extract: dict[str, str] = Field(default_factory=dict)
    think_time: ThinkTime = None

    @field_validator("method", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return v.upper() if isinstance(v, str) else v

    @field_validator("path")
    @classmethod
    def _relative_path(cls, v: str) -> str:
        # Absolute or protocol-relative paths would bypass the base_url allowlist.
        if not v.startswith("/") or v.startswith("//") or "://" in v:
            raise ValueError("path must be relative to base_url and start with a single '/'")
        return v

    @field_validator("extract")
    @classmethod
    def _extractors(cls, v: dict[str, str]) -> dict[str, str]:
        for name, source in v.items():
            if not _VAR_NAME_RE.fullmatch(name):
                raise ValueError(f"extract variable {name!r} must be a plain identifier")
            if source.startswith("regex:"):
                try:
                    re.compile(source[6:])
                except re.error as exc:
                    raise ValueError(f"extract {name}: invalid regex: {exc}") from exc
            elif source.startswith("header:"):
                if not source[7:].strip():
                    raise ValueError(f"extract {name}: header name is empty")
            else:
                jsonpath.parse(source)
        return v

    @property
    def tenant_key(self) -> str:
        return self.tenant or self.name


class DataConfig(_Base):
    """Test data rows (JMeter CSV Data Set Config); each iteration takes the next row."""

    csv: str | None = Field(default=None, description="inline CSV with a header row")
    file: str | None = Field(default=None, description="CSV path (CLI only)")
    rows: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] | None = Field(default=None, description="names when the CSV has no header")
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    mode: Literal["sequential", "random"] = "sequential"
    recycle: bool = Field(default=True, description="restart at EOF; false stops the user")

    @model_validator(mode="after")
    def _one_source(self) -> DataConfig:
        sources = [s for s in (self.csv, self.file) if s is not None] + (
            [self.rows] if self.rows else []
        )
        if len(sources) != 1:
            raise ValueError("data needs exactly one of csv, file or rows")
        if self.csv is not None:
            if len(self.csv.encode()) > MAX_DATA_BYTES:
                raise ValueError("data.csv is too large")
            if not self.records():
                raise ValueError("data.csv needs a header row (or columns) and at least one row")
        return self

    def records(self) -> list[dict[str, str]]:
        if self.file is not None:
            raise ConfigError("data.file must be loaded before the run (use the CLI)")
        if self.csv is not None:
            reader = csv.DictReader(
                io.StringIO(self.csv.strip()), fieldnames=self.columns, delimiter=self.delimiter
            )
            return [
                {k.strip(): (v or "") for k, v in row.items() if isinstance(k, str) and k.strip()}
                for row in reader
            ]
        return [{str(k): "" if v is None else str(v) for k, v in r.items()} for r in self.rows]


class ThresholdSet(_Base):
    avg_ms: float | None = Field(default=None, gt=0)
    p50_ms: float | None = Field(default=None, gt=0)
    p90_ms: float | None = Field(default=None, gt=0)
    p95_ms: float | None = Field(default=None, gt=0)
    p99_ms: float | None = Field(default=None, gt=0)
    max_ms: float | None = Field(default=None, gt=0)
    error_rate: float | None = Field(default=None, ge=0, le=1)
    min_rps: float | None = Field(default=None, gt=0)
    min_apdex: float | None = Field(default=None, ge=0, le=1)


class ThresholdsConfig(ThresholdSet):
    """Pass/fail criteria (SLA) evaluated on the whole run and per request."""

    apdex_satisfied_ms: float = Field(default=500, gt=0)
    apdex_tolerated_ms: float = Field(default=1500, gt=0)
    routes: dict[str, ThresholdSet] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _apdex(self) -> ThresholdsConfig:
        if self.apdex_tolerated_ms < self.apdex_satisfied_ms:
            raise ValueError("apdex_tolerated_ms must be >= apdex_satisfied_ms")
        return self


class OutputConfig(_Base):
    events_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    flush_interval: Duration = 1.0


class AnalysisConfig(_Base):
    expected_limit_rps: float | None = Field(default=None, gt=0)
    expected_burst: float | None = Field(default=None, ge=0)
    tolerance: float = Field(default=0.05, gt=0, lt=1)
    burst_tolerance: float = Field(default=0.10, gt=0, lt=1)
    fairness_threshold: float = Field(default=1.2, ge=1.0)
    knee_marginal_threshold: float = Field(default=0.5, gt=0, le=1)
    knee_429_threshold: float = Field(default=0.02, ge=0, lt=1)
    warmup_windows: int = Field(default=1, ge=0)


class Config(_Base):
    version: Literal[1] = 1
    name: str | None = None
    base_url: str
    default_headers: dict[str, str] = Field(default_factory=dict)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    model: ModelConfig
    http: HttpConfig = Field(default_factory=HttpConfig)
    routes: list[RouteConfig] = Field(min_length=1)
    variables: dict[str, str] = Field(default_factory=dict, description="user defined variables")
    data: DataConfig | None = None
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)

    @field_validator("variables", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return {str(k): "" if val is None else str(val) for k, val in v.items()}
        return v

    @field_validator("base_url")
    @classmethod
    def _valid_url(cls, v: str) -> str:
        parts = urlsplit(v)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("base_url must be an absolute http(s) URL with a host")
        return v.rstrip("/")

    @model_validator(mode="after")
    def _unique_routes(self) -> Config:
        names = [r.name for r in self.routes]
        if len(names) != len(set(names)):
            raise ValueError("route names must be unique")
        unknown = sorted(set(self.thresholds.routes) - set(names))
        if unknown:
            raise ValueError(f"thresholds.routes refers to unknown routes: {', '.join(unknown)}")
        if not self.model.is_closed:
            stateful = [r.name for r in self.routes if r.extract or r.think_time]
            if stateful:
                raise ValueError(
                    "extract and think_time need model.type: closed (virtual users); "
                    f"used by: {', '.join(stateful)}"
                )
        return self

    @property
    def host(self) -> str:
        return (urlsplit(self.base_url).hostname or "").lower()


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2)
            env = os.environ.get(name)
            if env is not None:
                return env
            if default is not None:
                return default
            raise ConfigError(f"environment variable {name!r} is not set")

        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  {loc}: {err['msg']}")
    return "invalid configuration:\n" + "\n".join(lines)


def parse_config(data: Any, *, expand_env: bool = True) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("configuration root must be a mapping")
    try:
        return Config.model_validate(_expand_env(data) if expand_env else data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def parse_config_text(text: str, *, expand_env: bool = True) -> Config:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}") from exc
    return parse_config(raw, expand_env=expand_env)


def load_config(path: str | Path) -> Config:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {p}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc
    cfg = parse_config(raw)
    if cfg.data is not None and cfg.data.file is not None:
        data_path = (p.parent / cfg.data.file).resolve()
        try:
            if data_path.stat().st_size > MAX_DATA_BYTES:
                raise ConfigError(f"data file {data_path} is larger than 50 MiB")
            text = data_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ConfigError(f"cannot read data file {data_path}: {exc}") from exc
        dumped = cfg.model_dump(mode="python")
        dumped["data"].update(csv=text, file=None)
        cfg = parse_config(dumped, expand_env=False)
    return cfg


def apply_overrides(
    cfg: Config,
    *,
    rps: float | None = None,
    duration: str | float | None = None,
    workers: int | None = None,
    processes: int | None = None,
    max_rps_cap: int | None = None,
    http2: bool | None = None,
    connections: int | None = None,
    streams: int | None = None,
    concurrency: int | None = None,
    events_sample_rate: float | None = None,
) -> Config:
    """Return a re-validated copy of ``cfg`` with CLI overrides applied.

    ``--rps``/``--duration`` replace the profile with a single constant step.
    ``--max-rps-cap`` can only lower the configured cap.
    """
    data = cfg.model_dump(mode="python")
    if cfg.model.is_closed and (rps is not None or duration is not None or workers is not None):
        raise ConfigError("rps/duration/workers overrides apply to open-model (RPS) configs only")
    if rps is not None or duration is not None:
        first = cfg.model.profile[0]
        seconds = parse_duration(duration) if duration is not None else cfg.model.total_duration
        data["model"]["profile"] = [
            {"duration": seconds, "rate": rps if rps is not None else first.rate}
        ]
    if workers is not None:
        data["model"]["workers"] = workers
    if processes is not None:
        data["model"]["processes"] = processes
        data["model"]["workers"] = max(data["model"]["workers"], processes)
    if max_rps_cap is not None:
        data["safety"]["max_rps_cap"] = min(cfg.safety.max_rps_cap, max_rps_cap)
    if http2 is not None:
        data["http"]["http2"] = http2
    if connections is not None:
        data["http"]["max_connections"] = connections
        data["http"]["max_keepalive"] = connections
    if streams is not None:
        data["http"]["max_streams"] = streams
    if concurrency is not None:
        data["http"]["concurrency"] = concurrency
    if events_sample_rate is not None:
        data["output"]["events_sample_rate"] = events_sample_rate
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def host_allowed(host: str, allowlist: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for entry in allowlist:
        pattern = entry.lower().strip().rstrip(".")
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]) and host != pattern[2:]:
                return True
        elif host == pattern:
            return True
    return False


@dataclass(frozen=True)
class SafetyReport:
    host: str
    effective_cap: int
    peak_rate: float
    warnings: list[str] = field(default_factory=list)


def check_safety(cfg: Config, cli_max_rps_cap: int | None = None) -> SafetyReport:
    """Fail fast if the target host is not allowlisted or the plan exceeds the RPS cap."""
    errors: list[str] = []
    warnings: list[str] = []
    host = cfg.host
    if cfg.safety.require_allowlist:
        if not cfg.safety.allowlist:
            errors.append("safety.require_allowlist is true but safety.allowlist is empty")
        elif not host_allowed(host, cfg.safety.allowlist):
            errors.append(f"host {host!r} is not in safety.allowlist {cfg.safety.allowlist}")
    else:
        warnings.append("safety.require_allowlist is disabled; target host is not verified")
    cap = cfg.safety.max_rps_cap
    if cli_max_rps_cap is not None:
        cap = min(cap, cli_max_rps_cap)
    cap = min(cap, ABSOLUTE_MAX_RPS)
    peak = cfg.model.peak_rate
    if peak > cap:
        errors.append(f"profile peak rate {peak:g} RPS exceeds max_rps_cap {cap}")
    if cfg.model.is_closed:
        users = cfg.model.peak_users
        if users > cfg.safety.max_users_cap:
            errors.append(
                f"{users} virtual users exceeds safety.max_users_cap {cfg.safety.max_users_cap}"
            )
        if cfg.model.max_rps is None:
            warnings.append(
                f"throughput is not shaped (model.max_rps); users are still held to "
                f"max_rps_cap {cap} RPS in total"
            )
        if cfg.model.processes > max(users, 1):
            warnings.append("more processes than virtual users; extra processes stay idle")
    if errors:
        raise SafetyError("; ".join(errors))
    return SafetyReport(host=host, effective_cap=cap, peak_rate=peak, warnings=warnings)
