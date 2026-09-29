"""``{{variable}}`` substitution with scoped variables and dynamic values."""

from __future__ import annotations

import random
import re
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from apitest.schemas import KeyValue

_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
# Bounded so self-referencing variables cannot loop forever.
_MAX_PASSES = 5


def _dynamic(name: str) -> str | None:
    match name:
        case "$uuid" | "$guid":
            return str(uuid.uuid4())
        case "$timestamp":
            return str(int(time.time()))
        case "$isoTimestamp":
            return datetime.now(timezone.utc).isoformat()
        case "$randomInt":
            return str(random.randint(0, 1000))  # noqa: S311 - test data, not crypto
        case "$randomEmail":
            return f"user{random.randint(1000, 99999)}@example.com"  # noqa: S311
    return None


def resolve(text: str, variables: Mapping[str, str]) -> str:
    """Replace ``{{name}}`` placeholders; unknown names are left untouched."""
    if "{{" not in text:
        return text

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return variables[name]
        value = _dynamic(name)
        return value if value is not None else match.group(0)

    for _ in range(_MAX_PASSES):
        new = _PATTERN.sub(sub, text)
        if new == text:
            break
        text = new
    return text


def unresolved(text: str) -> list[str]:
    return [m.group(1) for m in _PATTERN.finditer(text)]


def scope(*layers: Iterable[KeyValue]) -> dict[str, str]:
    """Flatten variable layers; later layers win."""
    out: dict[str, str] = {}
    for layer in layers:
        for var in layer:
            key = var.key.strip()
            if var.enabled and key:
                out[key] = var.value
    return out
