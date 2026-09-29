"""Turning finished runs into something a human reads.

Three consumers share one summary shape: the consolidated batch report, the
Jira comment, and the JSON the dashboard downloads. Building the summary once
keeps the three of them from drifting apart.
"""

import html
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from app.config import settings
from app.models.models import StatusEnum

logger = logging.getLogger(__name__)

# Evidence worth attaching to a Jira issue, in the order a reader wants them.
JIRA_EVIDENCE_ORDER = ("screenshot", "console_log", "network_log", "video", "trace")

STATUS_COLOURS = {
    "passed": "#16a34a",
    "failed": "#dc2626",
    "error": "#d97706",
    "running": "#0284c7",
    "pending": "#64748b",
}


def _value(v) -> str:
    return v.value if hasattr(v, "value") else str(v or "")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _duration_ms(started, finished) -> Optional[int]:
    start, end = _utc(started), _utc(finished)
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def format_duration(ms: Optional[int]) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms} ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} s"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


@dataclass
class StepSummary:
    order: int
    action: str
    selector: str
    value: str
    status: str
    duration_ms: Optional[int]
    error: str
    screenshot: str
    is_exit_criteria: bool
    check: str


@dataclass
class RunSummary:
    """One replayed test case, flattened for reporting."""

    run_id: str
    test_case_id: str
    test_case_name: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error: str
    steps: list[StepSummary] = field(default_factory=list)
    evidence: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == "passed")

    @property
    def dashboard_url(self) -> str:
        return f"{settings.dashboard_url.rstrip('/')}/runs/{self.run_id}"

    def evidence_paths(self) -> list[str]:
        """Absolute paths to this run's artefacts, best evidence first."""
        artifacts_root = Path(settings.artifacts_dir).resolve().parent
        ordered: list[str] = []
        for kind in JIRA_EVIDENCE_ORDER:
            for rel in self.evidence.get(kind, []):
                ordered.append(str((artifacts_root / rel).resolve()))
        return ordered

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "test_case_id": self.test_case_id,
            "test_case": self.test_case_name,
            "status": self.status,
            "started_at": _utc(self.started_at).isoformat()
            if self.started_at
            else None,
            "finished_at": _utc(self.finished_at).isoformat()
            if self.finished_at
            else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "steps_passed": self.passed_steps,
            "steps_total": len(self.steps),
            "url": self.dashboard_url,
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "selector": s.selector,
                    "value": s.value,
                    "check": s.check,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                    "screenshot": s.screenshot,
                    "is_exit_criteria": s.is_exit_criteria,
                }
                for s in self.steps
            ],
            "evidence": self.evidence,
        }


def summarise_run(run, test_case) -> RunSummary:
    """Flatten a TestRun plus its test case into a reporting summary.

    Both must already be loaded - this is called from background tasks where a
    lazy load would hit a closed session.
    """
    steps_by_id = {s.id: s for s in (getattr(test_case, "steps", None) or [])}

    steps: list[StepSummary] = []
    for result in getattr(run, "step_results", None) or []:
        step = steps_by_id.get(result.step_id)
        check = ""
        if step is not None and _value(step.action) == "assert":
            check = " ".join(
                part for part in (step.assertion_type, step.expected_value) if part
            )
        steps.append(
            StepSummary(
                order=(step.order_index + 1) if step else len(steps) + 1,
                action=_value(step.action) if step else "step",
                selector=(step.selector if step else "") or "",
                value=(step.value if step else "") or "",
                status=_value(result.status),
                duration_ms=result.duration_ms,
                error=result.error_message or "",
                screenshot=result.screenshot_path or "",
                is_exit_criteria=bool(getattr(step, "is_exit_criteria", False))
                if step
                else False,
                check=check,
            )
        )
    steps.sort(key=lambda s: (s.is_exit_criteria, s.order))

    evidence: dict[str, list[str]] = {}
    for ev in getattr(run, "evidences", None) or []:
        evidence.setdefault(_value(ev.type), []).append(ev.file_path)

    return RunSummary(
        run_id=run.id,
        test_case_id=run.test_case_id,
        test_case_name=getattr(test_case, "name", None) or "Test case",
        status=_value(run.status),
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=_duration_ms(run.started_at, run.finished_at),
        error=run.error_message or "",
        steps=steps,
        evidence=evidence,
    )


# ------------------------------------------------------------- Jira comment


def _jira_status_icon(status: str) -> str:
    return {
        "passed": "(/)",
        "failed": "(x)",
        "error": "(!)",
    }.get(status, "(?)")


def jira_comment_for_run(summary: RunSummary, project_name: str) -> str:
    """Jira wiki markup describing one run. Evidence is attached separately."""
    lines = [
        f"h3. {_jira_status_icon(summary.status)} Rewind regression run — "
        f"{summary.test_case_name}",
        "",
        f"*Project:* {project_name}",
        f"*Result:* *{summary.status.upper()}* "
        f"({summary.passed_steps}/{len(summary.steps)} steps passed)",
        f"*Duration:* {format_duration(summary.duration_ms)}",
        f"*Started:* {_utc(summary.started_at).isoformat() if summary.started_at else 'unknown'}",
        f"*Full evidence:* [Open in Rewind|{summary.dashboard_url}]",
        "",
    ]

    if summary.error:
        lines += [
            "{panel:title=Why it stopped|borderColor=#dc2626}",
            summary.error.strip(),
            "{panel}",
            "",
        ]

    lines += ["||#||Step||Target||Check||Result||Time||"]
    for step in summary.steps:
        label = f"{step.action}{' _(exit criteria)_' if step.is_exit_criteria else ''}"
        target = step.selector or step.value or "—"
        lines.append(
            f"|{step.order}|{label}|{{{{{_jira_cell(target)}}}}}"
            f"|{_jira_cell(step.check or step.value) or '—'}"
            f"|{_jira_status_icon(step.status)} {step.status}"
            f"|{format_duration(step.duration_ms)}|"
        )

    failures = [s for s in summary.steps if s.status in ("failed", "error") and s.error]
    if failures:
        lines += ["", "h4. Failures"]
        for step in failures:
            lines.append(
                f"* *Step {step.order} ({step.action})*: {{code}}{step.error.strip()}{{code}}"
            )

    attached = sum(len(v) for v in summary.evidence.values())
    if attached:
        lines += [
            "",
            f"_Evidence attached to this issue: screenshots, console and network "
            f"logs, video and Playwright trace ({attached} files captured)._",
        ]
    return "\n".join(lines)


def jira_comment_for_batch(
    batch_name: str, summaries: list[RunSummary], project_name: str, status: str
) -> str:
    """One comment covering a sequential batch, so the issue gets a single update."""
    passed = sum(1 for s in summaries if s.status == "passed")
    lines = [
        f"h3. {_jira_status_icon(status)} Rewind regression suite — {batch_name}",
        "",
        f"*Project:* {project_name}",
        f"*Result:* *{status.upper()}* ({passed}/{len(summaries)} test cases passed)",
        f"*Total duration:* "
        f"{format_duration(sum(s.duration_ms or 0 for s in summaries) or None)}",
        "",
        "||#||Test case||Result||Steps||Time||Evidence||",
    ]
    for index, summary in enumerate(summaries, start=1):
        lines.append(
            f"|{index}|{summary.test_case_name}"
            f"|{_jira_status_icon(summary.status)} {summary.status}"
            f"|{summary.passed_steps}/{len(summary.steps)}"
            f"|{format_duration(summary.duration_ms)}"
            f"|[Open|{summary.dashboard_url}]|"
        )

    failed = [s for s in summaries if s.status != "passed"]
    if failed:
        lines += ["", "h4. What failed"]
        for summary in failed:
            reason = (
                (summary.error or "See the run for details.").strip().splitlines()[0]
            )
            lines.append(f"* *{summary.test_case_name}*: {reason}")
    return "\n".join(lines)


def _jira_cell(text: str) -> str:
    """Pipes break a Jira table row, and newlines break the whole table."""
    return (text or "").replace("|", "\\|").replace("\n", " ")[:120]


# ------------------------------------------------------ consolidated report


def _row_status(status: str) -> str:
    return STATUS_COLOURS.get(status, STATUS_COLOURS["pending"])


def _step_rows(summary: RunSummary, artifacts_base: str) -> str:
    rows = []
    exit_tag = '<span class="tag">exit criteria</span>'
    for step in summary.steps:
        shot = ""
        if step.screenshot:
            url = f"{artifacts_base}/{step.screenshot}"
            shot = f'<a href="{html.escape(url)}" target="_blank">screenshot</a>'
        label = html.escape(step.action) + (
            f" {exit_tag}" if step.is_exit_criteria else ""
        )
        rows.append(
            "<tr>"
            f"<td>{step.order}</td>"
            f"<td>{label}</td>"
            f'<td class="mono">{html.escape(step.selector or step.value or "—")}</td>'
            f"<td>{html.escape(step.check or '—')}</td>"
            f'<td><span class="pill" style="background:{_row_status(step.status)}">'
            f"{html.escape(step.status)}</span></td>"
            f"<td>{format_duration(step.duration_ms)}</td>"
            f"<td>{shot}</td>"
            "</tr>"
        )
        if step.error:
            rows.append(
                f'<tr class="err"><td colspan="7"><pre>{html.escape(step.error)}</pre></td></tr>'
            )
    return "\n".join(rows)


def _evidence_links(summary: RunSummary, artifacts_base: str) -> str:
    links = []
    for kind, paths in sorted(summary.evidence.items()):
        for path in paths:
            url = f"{artifacts_base}/{path}"
            links.append(
                f'<a class="chip" href="{html.escape(url)}" target="_blank">'
                f"{html.escape(kind.replace('_', ' '))}</a>"
            )
    return "".join(links) or '<span class="muted">no files captured</span>'


REPORT_CSS = """
:root { color-scheme: light; }
body { margin:0; padding:32px; font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       color:#0f172a; background:#f8fafc; }
h1 { font-size:24px; margin:0 0 4px; }
h2 { font-size:17px; margin:0; }
.muted { color:#64748b; font-size:13px; }
.card { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:20px; margin:16px 0;
        box-shadow:0 1px 2px rgba(15,23,42,.04); }
.summary { display:flex; flex-wrap:wrap; gap:24px; margin-top:12px; }
.metric b { display:block; font-size:22px; font-variant-numeric:tabular-nums; }
.metric span { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#64748b; }
table { width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }
th { text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#64748b;
     border-bottom:1px solid #e2e8f0; padding:8px 10px; }
td { padding:8px 10px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; word-break:break-all; }
.pill { color:#fff; border-radius:999px; padding:2px 9px; font-size:11px; font-weight:600; }
.tag { background:#ede9fe; color:#6d28d9; border-radius:999px; padding:1px 7px; font-size:10px; font-weight:600; }
.chip { display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:999px;
        padding:3px 10px; margin:2px 6px 2px 0; font-size:12px; color:#334155; text-decoration:none; }
.chip:hover { background:#e2e8f0; }
.err pre { margin:0; white-space:pre-wrap; background:#fef2f2; border:1px solid #fecaca; color:#b91c1c;
           border-radius:8px; padding:10px; font-size:12px; }
a { color:#4f46e5; }
"""


def render_batch_report(batch, summaries: list[RunSummary], project_name: str) -> str:
    """A self-contained HTML report; evidence stays as links to the backend."""
    artifacts_base = settings.base_url.rstrip("/")
    passed = sum(1 for s in summaries if s.status == "passed")
    total_ms = sum(s.duration_ms or 0 for s in summaries) or None
    status = _value(batch.status)

    sections = []
    for index, summary in enumerate(summaries, start=1):
        sections.append(f"""
<div class="card">
  <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:baseline">
    <h2>{index}. {html.escape(summary.test_case_name)}</h2>
    <span class="pill" style="background:{_row_status(summary.status)}">{html.escape(summary.status)}</span>
  </div>
  <p class="muted">{summary.passed_steps}/{len(summary.steps)} steps passed ·
     {format_duration(summary.duration_ms)} ·
     <a href="{html.escape(summary.dashboard_url)}">open in Rewind</a></p>
  {f'<div class="err"><pre>{html.escape(summary.error)}</pre></div>' if summary.error else ""}
  <div style="margin-top:10px">{_evidence_links(summary, artifacts_base)}</div>
  <table>
    <thead><tr><th>#</th><th>Action</th><th>Target</th><th>Check</th><th>Result</th><th>Time</th><th></th></tr></thead>
    <tbody>{_step_rows(summary, artifacts_base)}</tbody>
  </table>
</div>""")

    finished = _utc(batch.finished_at)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Rewind report — {html.escape(batch.name)}</title>
<style>{REPORT_CSS}</style></head>
<body>
<h1>{html.escape(batch.name)}</h1>
<p class="muted">{html.escape(project_name)} ·
   finished {html.escape(finished.strftime("%Y-%m-%d %H:%M UTC") if finished else "in progress")}</p>
<div class="card">
  <div class="summary">
    <div class="metric"><b style="color:{_row_status(status)}">{html.escape(status.upper())}</b><span>overall</span></div>
    <div class="metric"><b>{passed}/{len(summaries)}</b><span>test cases passed</span></div>
    <div class="metric"><b>{sum(s.passed_steps for s in summaries)}/{sum(len(s.steps) for s in summaries)}</b><span>steps passed</span></div>
    <div class="metric"><b>{format_duration(total_ms)}</b><span>total time</span></div>
  </div>
</div>
{"".join(sections)}
</body></html>"""


def write_batch_report(
    batch, summaries: list[RunSummary], project_name: str
) -> Optional[str]:
    """Write report.html + report.json for a batch; returns the HTML path.

    Reporting must never sink a batch that otherwise ran fine, so a write
    failure is logged and swallowed.
    """
    try:
        directory = Path(settings.artifacts_dir) / "batches" / batch.id
        directory.mkdir(parents=True, exist_ok=True)

        (directory / "report.html").write_text(
            render_batch_report(batch, summaries, project_name), encoding="utf-8"
        )
        (directory / "report.json").write_text(
            json.dumps(
                {
                    "batch_id": batch.id,
                    "name": batch.name,
                    "project": project_name,
                    "status": _value(batch.status),
                    "runs": [s.to_dict() for s in summaries],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return f"artifacts/batches/{batch.id}/report.html"
    except OSError as e:
        logger.error("Could not write the consolidated report for %s: %s", batch.id, e)
        return None


def collect_evidence_paths(
    summaries: Iterable[RunSummary], limit: int = 25
) -> list[str]:
    """Evidence for a whole batch, capped so an upload cannot run away."""
    paths: list[str] = []
    for summary in summaries:
        for path in summary.evidence_paths():
            if path not in paths:
                paths.append(path)
            if len(paths) >= limit:
                return paths
    return paths


def overall_status(summaries: Iterable[RunSummary]) -> StatusEnum:
    """A batch is only green when every run in it is."""
    statuses = {s.status for s in summaries}
    if not statuses:
        return StatusEnum.error
    if statuses == {"passed"}:
        return StatusEnum.passed
    if "failed" in statuses:
        return StatusEnum.failed
    if "error" in statuses:
        return StatusEnum.error
    return StatusEnum.failed
