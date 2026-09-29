"""Run reports: JUnit XML (for CI) and a self-contained HTML page."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET

from apitest.schemas import Assertion, AssertionResult, RunDetail


def describe(a: Assertion) -> str:
    subject = {
        "status": "status",
        "response_time": "response time (ms)",
        "body": "body",
        "header": f"header {a.property}",
        "json": a.property or "$",
        "json_schema": "body matches JSON Schema",
    }[a.source]
    if a.source == "json_schema":
        return subject
    op = a.operator.replace("_", " ")
    return f"{subject} {op}" + ("" if a.operator in ("exists", "not_exists") else f" {a.expected}")


def _failure_text(results: list[AssertionResult]) -> str:
    return "\n".join(f"{describe(r.assertion)}: {r.message or 'failed'}" for r in results if not r.passed)


def junit(run: RunDetail) -> str:
    t = run.totals
    root = ET.Element("testsuites", name="API Testing Tool", tests=str(t.requests))
    suite = ET.SubElement(
        root,
        "testsuite",
        name=run.collection_name,
        tests=str(t.requests),
        failures=str(t.failed - t.errors),
        errors=str(t.errors),
        time=f"{t.duration_ms / 1000:.3f}",
        timestamp=run.started_at.isoformat(),
    )
    for step in run.steps:
        r = step.result
        elapsed = r.response.elapsed_ms if r.response else 0.0
        case = ET.SubElement(
            suite,
            "testcase",
            classname=f"{run.collection_name}.iteration-{step.iteration}",
            name=step.request_name,
            time=f"{elapsed / 1000:.3f}",
        )
        if r.error:
            ET.SubElement(case, "error", message=r.error).text = f"{r.request.method} {r.request.url}"
        elif not r.passed:
            failed = [a for a in r.assertions if not a.passed]
            el = ET.SubElement(case, "failure", message=f"{len(failed)} assertion(s) failed")
            el.text = _failure_text(r.assertions)
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


_CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;margin:24px;color:#0f172a}
h1{margin:0 0 4px}.muted{color:#64748b}.cards{display:flex;gap:12px;margin:16px 0;flex-wrap:wrap}
.card{border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:120px}
.card b{display:block;font-size:20px}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}
.pass{color:#15803d;font-weight:600}.fail{color:#b91c1c;font-weight:600}
ul{margin:4px 0;padding-left:18px}code{font-size:12px}
"""


def html_report(run: RunDetail) -> str:
    e = html.escape
    t = run.totals
    avg = f"{t.avg_response_ms:.0f} ms" if t.avg_response_ms is not None else "-"
    rows = []
    for step in run.steps:
        r = step.result
        status = str(r.response.status) if r.response else "-"
        elapsed = f"{r.response.elapsed_ms:.0f} ms" if r.response else "-"
        checks = "".join(
            f"<li class='{'pass' if a.passed else 'fail'}'>{'✔' if a.passed else '✘'} "
            f"{e(describe(a.assertion))}{'' if a.passed else ' — ' + e(a.message)}</li>"
            for a in r.assertions
        )
        if r.error:
            checks = f"<li class='fail'>{e(r.error)}</li>" + checks
        rows.append(
            f"<tr><td>{step.iteration}</td><td>{e(step.request_name)}</td>"
            f"<td><code>{e(r.request.method)} {e(r.request.url)}</code></td>"
            f"<td>{status}</td><td>{elapsed}</td>"
            f"<td class='{'pass' if r.passed else 'fail'}'>{'PASS' if r.passed else 'FAIL'}</td>"
            f"<td><ul>{checks}</ul></td></tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Run #{run.id} — {e(run.collection_name)}</title>
<style>{_CSS}</style></head><body>
<h1>{e(run.collection_name)} <span class="{'pass' if run.status == 'passed' else 'fail'}">{run.status.upper()}</span></h1>
<div class="muted">Run #{run.id} · environment: {e(run.environment_name or 'none')} · {e(run.started_at.isoformat())}</div>
<div class="cards">
<div class="card">Requests<b>{t.passed}/{t.requests}</b></div>
<div class="card">Assertions<b>{t.assertions_passed}/{t.assertions_total}</b></div>
<div class="card">Iterations<b>{t.iterations}</b></div>
<div class="card">Avg response<b>{avg}</b></div>
<div class="card">Duration<b>{t.duration_ms / 1000:.2f} s</b></div>
</div>
<table><thead><tr><th>#</th><th>Request</th><th>URL</th><th>Status</th><th>Time</th><th>Result</th><th>Checks</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>
"""
