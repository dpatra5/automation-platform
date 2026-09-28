"""Server settings, read from ``APIT_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_url: str = "sqlite:///data/apitest.db"
    port: int = 8002
    # Empty token disables auth; only acceptable when bound to loopback.
    token: str | None = None
    # Hosts requests may target: "*" = any, "*.corp.com" = subdomains, else exact match.
    allowed_hosts: list[str] = field(default_factory=lambda: ["*"])
    max_response_bytes: int = 5 * 1024 * 1024
    stored_body_chars: int = 20_000
    max_iterations: int = 100
    seed_demo: bool = True
    static_dir: Path | None = None

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        env = os.environ
        static = env.get("APIT_STATIC_DIR")
        values: dict[str, object] = {
            "db_url": env.get("APIT_DB_URL", cls.db_url),
            "port": int(env.get("APIT_PORT", cls.port)),
            "token": env.get("APIT_TOKEN") or None,
            "allowed_hosts": _csv(env.get("APIT_ALLOWED_HOSTS"), ["*"]),
            "max_response_bytes": int(env.get("APIT_MAX_RESPONSE_BYTES", cls.max_response_bytes)),
            "seed_demo": _bool(env.get("APIT_SEED_DEMO"), True),
            "static_dir": Path(static) if static else None,
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)  # type: ignore[arg-type]
