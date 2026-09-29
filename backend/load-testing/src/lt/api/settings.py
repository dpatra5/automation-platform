"""API server settings, read from ``LT_API_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from lt.config import ABSOLUTE_MAX_RPS

_DEFAULT_EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def _csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class ApiSettings:
    runs_dir: Path = Path("runs")
    examples_dir: Path = _DEFAULT_EXAMPLES
    static_dir: Path | None = None
    # Empty token disables auth; only acceptable when bound to loopback.
    token: str | None = None
    cors_origins: list[str] = field(default_factory=list)
    # Server-side target allowlist enforced on top of each config's own allowlist; "*" = any.
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    max_rps_cap: int = ABSOLUTE_MAX_RPS
    max_config_bytes: int = 256 * 1024

    @property
    def any_host(self) -> bool:
        return "*" in self.allowed_hosts

    @classmethod
    def from_env(cls, **overrides: object) -> ApiSettings:
        env = os.environ
        static = env.get("LT_API_STATIC_DIR")
        values: dict[str, object] = {
            "runs_dir": Path(env.get("LT_API_RUNS_DIR", "runs")),
            "examples_dir": Path(env.get("LT_API_EXAMPLES_DIR", str(_DEFAULT_EXAMPLES))),
            "static_dir": Path(static) if static else None,
            "token": env.get("LT_API_TOKEN") or None,
            "cors_origins": _csv(env.get("LT_API_CORS_ORIGINS"), []),
            "allowed_hosts": _csv(env.get("LT_API_ALLOWED_HOSTS"), ["127.0.0.1", "localhost"]),
            "max_rps_cap": min(
                int(env.get("LT_API_MAX_RPS_CAP", ABSOLUTE_MAX_RPS)), ABSOLUTE_MAX_RPS
            ),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)  # type: ignore[arg-type]
