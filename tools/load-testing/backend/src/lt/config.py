"""Configuration schema (pydantic), YAML loading, overrides, and safety guardrails."""

from __future__ import annotations

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

from lt.utils.time import parse_duration

ABSOLUTE_MAX_RPS = 100_000

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
Duration = Annotated[float, BeforeValidator(parse_duration)]

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


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
    require_allowlist: bool = True


class ModelConfig(_Base):
    type: Literal["open"] = "open"
    workers: int = Field(default=4, ge=1, le=1024, description="scheduler shards")
    processes: int = Field(default=1, ge=1, le=256)
    seed: int = 0
    use_uvloop: bool = True
    profile: list[ProfileStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> ModelConfig:
        if not any(step.peak_rate > 0 for step in self.profile):
            raise ValueError("profile must contain at least one step with rate > 0")
        if self.processes > self.workers:
            raise ValueError("workers (total shards) must be >= processes")
        return self

    @property
    def total_duration(self) -> float:
        return sum(step.duration for step in self.profile)

    @property
    def peak_rate(self) -> float:
        return max(step.peak_rate for step in self.profile)

    @property
    def expected_events(self) -> float:
        return sum(step.expected_events for step in self.profile)


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


class RouteConfig(_Base):
    name: str = Field(min_length=1)
    method: HttpMethod = "GET"
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | list[Any] | str | None = None
    expect_status: list[int] = Field(default_factory=lambda: [200, 429])
    weight: float = Field(default=1.0, gt=0)
    tenant: str | None = None

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

    @property
    def tenant_key(self) -> str:
        return self.tenant or self.name


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
    output: OutputConfig = Field(default_factory=OutputConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)

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
    return parse_config(raw)


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
    if errors:
        raise SafetyError("; ".join(errors))
    return SafetyReport(host=host, effective_cap=cap, peak_rate=peak, warnings=warnings)
