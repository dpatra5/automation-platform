"""Minimal JSONPath: ``$.a.b[0]['key with space'].length``."""

from __future__ import annotations

import re
from typing import Any

_SEGMENT = re.compile(
    r"""
      \[\s*(?P<index>-?\d+)\s*\]
    | \[\s*(?P<quote>['"])(?P<qkey>.*?)(?P=quote)\s*\]
    | \.?(?P<key>[^.\[\]]+)
    """,
    re.VERBOSE,
)


def parse(path: str) -> list[str | int]:
    path = path.strip()
    if not path.startswith("$"):
        raise ValueError(f"JSON path must start with '$': {path!r}")
    path = path[1:]
    segments: list[str | int] = []
    pos = 0
    while pos < len(path):
        match = _SEGMENT.match(path, pos)
        if not match or match.end() == pos:
            raise ValueError(f"invalid JSON path near {path[pos:]!r}")
        if match.group("index") is not None:
            segments.append(int(match.group("index")))
        elif match.group("qkey") is not None:
            segments.append(match.group("qkey"))
        else:
            segments.append(match.group("key").strip())
        pos = match.end()
    return segments


def get(data: Any, segments: list[str | int]) -> tuple[bool, Any]:
    """Return ``(found, value)``; ``length`` yields the size of arrays, objects and strings."""
    current = data
    for segment in segments:
        if isinstance(current, list):
            if isinstance(segment, str):
                if segment == "length":
                    current = len(current)
                    continue
                if not segment.lstrip("-").isdigit():
                    return False, None
                segment = int(segment)
            if -len(current) <= segment < len(current):
                current = current[segment]
            else:
                return False, None
        elif isinstance(current, dict):
            key = str(segment)
            if key in current:
                current = current[key]
            elif key == "length":
                current = len(current)
            else:
                return False, None
        elif isinstance(current, str) and segment == "length":
            current = len(current)
        else:
            return False, None
    return True, current
