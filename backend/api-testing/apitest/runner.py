"""Collection runner: iterations, data-driven rows, chaining and totals."""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import httpx

from apitest.config import Settings
from apitest.executor import execute
from apitest.schemas import ExecutionResult, RequestSpec, RunStep, RunTotals


@dataclass
class PlanItem:
    request_id: int | None
    name: str
    spec: RequestSpec


def parse_data(text: str, limit: int) -> list[dict[str, str]]:
    """Parse CSV (with header row) or a JSON array of objects into iteration rows."""
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"data is not valid JSON: {exc}") from exc
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ValueError("JSON data must be an array of objects")
        out = [
            {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in row.items()}
            for row in rows
        ]
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV data needs a header row")
        out = [
            {k.strip(): (v or "") for k, v in row.items() if isinstance(k, str) and k.strip()}
            for row in reader
        ]
    if not out:
        raise ValueError("data has no rows")
    if len(out) > limit:
        raise ValueError(f"data has {len(out)} rows; the maximum is {limit}")
    return out


def _trim(result: ExecutionResult, limit: int) -> ExecutionResult:
    response = result.response
    if response is None or len(response.body) <= limit:
        return result
    trimmed = response.model_copy(update={"body": response.body[:limit], "body_truncated": True})
    return result.model_copy(update={"response": trimmed})


def totals(steps: list[RunStep], duration_ms: float) -> RunTotals:
    times = [s.result.response.elapsed_ms for s in steps if s.result.response]
    assertions = [a for s in steps for a in s.result.assertions]
    passed = sum(1 for s in steps if s.result.passed)
    assertions_passed = sum(1 for a in assertions if a.passed)
    return RunTotals(
        iterations=max((s.iteration for s in steps), default=0),
        requests=len(steps),
        passed=passed,
        failed=len(steps) - passed,
        errors=sum(1 for s in steps if s.result.error),
        assertions_total=len(assertions),
        assertions_passed=assertions_passed,
        assertions_failed=len(assertions) - assertions_passed,
        avg_response_ms=round(sum(times) / len(times), 2) if times else None,
        duration_ms=round(duration_ms, 2),
    )


def run_plan(
    items: list[PlanItem],
    base_variables: Mapping[str, str],
    settings: Settings,
    *,
    secrets: Iterable[str] = (),
    iterations: int = 1,
    data_rows: list[dict[str, str]] | None = None,
    stop_on_failure: bool = False,
    delay_ms: int = 0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[list[RunStep], RunTotals, str]:
    secrets = list(secrets)
    rows = data_rows or []
    count = len(rows) or iterations
    started = time.perf_counter()
    steps: list[RunStep] = []

    for index in range(count):
        # Each iteration starts fresh so extracted values never leak between data rows.
        scope = {**base_variables, **(rows[index] if rows else {})}
        stop = False
        for item in items:
            if delay_ms and steps:
                time.sleep(delay_ms / 1000)
            result = execute(item.spec, scope, settings, secrets=secrets, transport=transport)
            scope.update(result.extracted)
            steps.append(
                RunStep(
                    iteration=index + 1,
                    request_id=item.request_id,
                    request_name=item.name,
                    result=_trim(result, settings.stored_body_chars),
                )
            )
            if stop_on_failure and not result.passed:
                stop = True
                break
        if stop:
            break

    summary = totals(steps, (time.perf_counter() - started) * 1000)
    status = "passed" if steps and summary.failed == 0 else "failed"
    return steps, summary, status
