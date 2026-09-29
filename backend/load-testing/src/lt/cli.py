"""Command-line interface: ``lt run | validate | analyze | report | demo-server | serve |
discover | scan``."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

import click

from lt import __version__
from lt.config import (
    Config,
    ConfigError,
    SafetyError,
    apply_overrides,
    check_safety,
    load_config,
    parse_config,
)
from lt.logging import setup_logging
from lt.utils.time import format_duration, parse_duration

if TYPE_CHECKING:
    from lt.discover import DiscoveryResult, Endpoint, LoadPlan

EXIT_INVALID = 2
EXIT_THRESHOLDS = 3
EXIT_INTERRUPTED = 130

F = TypeVar("F", bound=Callable[..., Any])


def _load(path: str, **overrides: Any) -> Config:
    try:
        cfg = load_config(path)
        if any(v is not None for v in overrides.values()):
            cfg = apply_overrides(cfg, **overrides)
    except ConfigError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    return cfg


def _duration(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parse_duration(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    return value


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="lt")
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
)
def main(log_level: str) -> None:
    """Open-model HTTP load generator and API rate-limit verifier."""
    setup_logging(log_level)


@main.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(dir_okay=False))
@click.option("--rps", type=click.FloatRange(min=0, min_open=True), help="Constant rate override.")
@click.option("--duration", callback=_duration, help="Duration override, e.g. 30s, 5m.")
@click.option("--workers", type=click.IntRange(min=1), help="Scheduler shards (total).")
@click.option("--processes", type=click.IntRange(min=1), help="Worker processes (sharding).")
@click.option("--max-rps-cap", type=click.IntRange(min=1), help="Lower the configured RPS cap.")
@click.option("--http2/--no-http2", default=None, help="Enable/disable HTTP/2.")
@click.option("--connections", type=click.IntRange(min=1), help="Max pooled connections.")
@click.option("--streams", type=click.IntRange(min=1), help="HTTP/2 streams per connection.")
@click.option("--concurrency", type=click.IntRange(min=1), help="Request workers per process.")
@click.option("--events-sample-rate", type=click.FloatRange(0, 1), help="Sample raw events.")
@click.option("--output-dir", default="runs", show_default=True, type=click.Path(file_okay=False))
@click.option("--run-id", help="Explicit run id (default: timestamp + random suffix).")
def run(
    config_path: str,
    rps: float | None,
    duration: str | None,
    workers: int | None,
    processes: int | None,
    max_rps_cap: int | None,
    http2: bool | None,
    connections: int | None,
    streams: int | None,
    concurrency: int | None,
    events_sample_rate: float | None,
    output_dir: str,
    run_id: str | None,
) -> None:
    """Execute a load profile and write artifacts to runs/<run_id>/."""
    from lt.engine import run_load
    from lt.report import format_summary

    cfg = _load(
        config_path,
        rps=rps,
        duration=duration,
        workers=workers,
        processes=processes,
        max_rps_cap=max_rps_cap,
        http2=http2,
        connections=connections,
        streams=streams,
        concurrency=concurrency,
        events_sample_rate=events_sample_rate,
    )
    try:
        result = run_load(cfg, output_dir=Path(output_dir), run_id=run_id)
    except SafetyError as exc:
        click.echo(f"safety check failed: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    except FileExistsError as exc:
        click.echo(f"error: run directory already exists: {exc.filename}", err=True)
        sys.exit(EXIT_INVALID)
    click.echo(format_summary({**result.summary, "aggregate": _aggregate(result.run_dir)}))
    click.echo(f"\nartifacts: {result.run_dir}")
    if result.interrupted:
        sys.exit(EXIT_INTERRUPTED)
    if (result.summary.get("thresholds") or {}).get("pass") is False:
        sys.exit(EXIT_THRESHOLDS)


def _aggregate(run_dir: Path) -> list[dict[str, Any]]:
    try:
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows: list[dict[str, Any]] = metrics.get("aggregate") or []
    return rows


@main.command("import-jmx")
@click.argument("jmx_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write YAML here.")
def import_jmx(jmx_path: str, output: str | None) -> None:
    """Convert an Apache JMeter .jmx test plan into an lt config (CSV files are inlined)."""
    from lt.jmx import JmxError, jmx_to_yaml

    path = Path(jmx_path)
    try:
        text, warnings = jmx_to_yaml(path.read_text(encoding="utf-8"), data_dir=path.parent)
    except JmxError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    for warning in warnings:
        click.echo(f"warning: {warning}", err=True)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"wrote {output}")
    else:
        click.echo(text, nl=False)


@main.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(dir_okay=False))
@click.option("--max-rps-cap", type=click.IntRange(min=1), help="Validate against a lower cap.")
def validate(config_path: str, max_rps_cap: int | None) -> None:
    """Validate the config schema and safety guardrails (non-zero exit on failure)."""
    cfg = _load(config_path)
    try:
        report = check_safety(cfg, max_rps_cap)
    except SafetyError as exc:
        click.echo(f"safety check failed: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    for warning in report.warnings:
        click.echo(f"warning: {warning}", err=True)
    click.echo(f"OK  {config_path}")
    click.echo(f"  target      {cfg.base_url} (host {report.host!r} allowed)")
    if cfg.model.is_closed:
        stages = ", ".join(f"{format_duration(s.duration)}->{s.users}" for s in cfg.model.stages)
        click.echo(f"  users       {cfg.model.peak_users} peak (stages {stages})")
        click.echo(f"  duration    {format_duration(cfg.model.total_duration)}")
        if cfg.model.iterations:
            click.echo(f"  iterations  {cfg.model.iterations} per user")
        click.echo(f"  pacing      <= {cfg.model.max_rps or report.effective_cap:g} RPS total")
        click.echo(f"  scenario    {' -> '.join(r.name for r in cfg.routes)}")
        return
    steps = ", ".join(
        f"{format_duration(s.duration)}@{s.rate:g}"
        + (f"->{s.end_rate:g}" if s.end_rate is not None else "")
        for s in cfg.model.profile
    )
    click.echo(f"  profile     {steps}")
    click.echo(f"  peak rate   {report.peak_rate:g} RPS (cap {report.effective_cap})")
    click.echo(f"  duration    {format_duration(cfg.model.total_duration)}")
    click.echo(f"  requests    ~{cfg.model.expected_events:,.0f}")
    click.echo(f"  routes      {', '.join(r.name for r in cfg.routes)}")
    click.echo(
        f"  execution   {cfg.model.processes} process(es), {cfg.model.workers} shard(s), "
        f"{cfg.http.effective_concurrency} workers/process, http2={cfg.http.http2}"
    )


@main.command()
@click.argument("run_dir", type=click.Path(file_okay=False, exists=True))
@click.option("--expected-limit", type=click.FloatRange(min=0, min_open=True))
@click.option("--expected-burst", type=click.FloatRange(min=0))
@click.option("--tolerance", type=click.FloatRange(0, 1, min_open=True, max_open=True))
@click.option("--fairness-threshold", type=click.FloatRange(min=1))
@click.option("--json", "as_json", is_flag=True, help="Print analysis.json instead of text.")
@click.option("--strict", is_flag=True, help="Exit 1 if any check fails (CI gate).")
def analyze(
    run_dir: str,
    expected_limit: float | None,
    expected_burst: float | None,
    tolerance: float | None,
    fairness_threshold: float | None,
    as_json: bool,
    strict: bool,
) -> None:
    """Analyze a run: capacity curve, burst, fairness, headers, window semantics."""
    from lt.analyze import AnalysisError, analyze_run
    from lt.report import format_analysis

    try:
        result = analyze_run(
            run_dir,
            {
                "expected_limit_rps": expected_limit,
                "expected_burst": expected_burst,
                "tolerance": tolerance,
                "fairness_threshold": fairness_threshold,
            },
        )
    except AnalysisError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    click.echo(json.dumps(result, indent=2) if as_json else format_analysis(result))
    if strict and not result["pass"]:
        sys.exit(1)


@main.command()
@click.argument("run_dir", type=click.Path(file_okay=False, exists=True))
@click.option("--json", "as_json", is_flag=True, help="Print summary.json as JSON.")
def report(run_dir: str, as_json: bool) -> None:
    """Print the run summary (and analysis verdicts if available)."""
    from lt.report import ReportError, format_summary, load_summary

    try:
        summary, analysis = load_summary(run_dir)
    except ReportError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    if as_json:
        click.echo(json.dumps(summary, indent=2))
    else:
        click.echo(format_summary(summary, analysis))


@main.command("demo-server")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8080, show_default=True, type=click.IntRange(0, 65535))
@click.option(
    "--rate",
    default=1000.0,
    show_default=True,
    type=click.FloatRange(min=0, min_open=True),
    help="Requests per window.",
)
@click.option("--burst", type=click.IntRange(min=1), help="Token-bucket capacity (default: rate).")
@click.option("--window", default="1s", show_default=True, callback=_duration)
@click.option(
    "--algo",
    default="token-bucket",
    show_default=True,
    type=click.Choice(["token-bucket", "fixed-window", "sliding-window"]),
)
@click.option(
    "--scope", default="global", show_default=True, type=click.Choice(["global", "per-key"])
)
@click.option("--key-header", default="X-API-Key", show_default=True)
@click.option("--latency-ms", default=0.0, show_default=True, type=click.FloatRange(min=0))
def demo_server(
    host: str,
    port: int,
    rate: float,
    burst: int | None,
    window: str,
    algo: str,
    scope: str,
    key_header: str,
    latency_ms: float,
) -> None:
    """Start a local rate-limited API (for examples and integration tests)."""
    from lt.demo_server import Algo, DemoSettings, Scope, run_demo_server

    settings = DemoSettings(
        rate=rate,
        burst=burst,
        window_s=parse_duration(window),
        algo=cast(Algo, algo),
        scope=cast(Scope, scope),
        key_header=key_header,
        latency_ms=latency_ms,
    )
    click.echo(
        f"demo server on http://{host}:{port}  algo={algo} rate={rate:g}/{window} "
        f"burst={burst if burst is not None else int(rate)} scope={scope}",
        err=True,
    )
    run_demo_server(settings, host, port)


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=click.IntRange(0, 65535))
@click.option("--runs-dir", type=click.Path(file_okay=False), help="[env: LT_API_RUNS_DIR]")
@click.option(
    "--static-dir",
    type=click.Path(file_okay=False, exists=True),
    help="Serve the built frontend from this directory. [env: LT_API_STATIC_DIR]",
)
@click.option(
    "--allow-no-auth",
    is_flag=True,
    help="Permit binding a non-loopback host without LT_API_TOKEN (not recommended).",
)
@click.option(
    "--allowed-hosts",
    help="Comma-separated hosts the server may scan/load ('*' = any). [env: LT_API_ALLOWED_HOSTS]",
)
def serve(
    host: str,
    port: int,
    runs_dir: str | None,
    static_dir: str | None,
    allow_no_auth: bool,
    allowed_hosts: str | None,
) -> None:
    """Start the REST API (and optionally the web UI)."""
    import uvicorn

    from lt.api.app import create_app
    from lt.api.settings import ApiSettings

    settings = ApiSettings.from_env(
        runs_dir=Path(runs_dir) if runs_dir else None,
        static_dir=Path(static_dir) if static_dir else None,
        allowed_hosts=(
            [h.strip() for h in allowed_hosts.split(",") if h.strip()] if allowed_hosts else None
        ),
    )
    if host not in _LOOPBACK and settings.token is None and not allow_no_auth:
        click.echo(
            f"error: refusing to expose the API on {host} without authentication; "
            "set LT_API_TOKEN (or pass --allow-no-auth)",
            err=True,
        )
        sys.exit(EXIT_INVALID)
    click.echo(f"lt API on http://{host}:{port}  (docs: /api/docs)", err=True)
    if settings.any_host:
        click.echo("warning: any target host is allowed; only test systems you own", err=True)
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info", proxy_headers=True)


def _discovery_options(fn: F) -> F:
    options = [
        click.argument("url"),
        click.option("--max-pages", default=10, show_default=True, type=click.IntRange(1, 200)),
        click.option("--max-depth", default=2, show_default=True, type=click.IntRange(0, 10)),
        click.option("--wait-ms", default=1500, show_default=True, type=click.IntRange(0, 30_000)),
        click.option("--scope", multiple=True, help="Extra in-scope API hosts (x.com, *.x.com)."),
        click.option(
            "-H", "--header", "headers", multiple=True, help="'Name: value' sent while crawling "
            "and in generated load (e.g. Authorization)."
        ),
        click.option("--ignore-https-errors", is_flag=True),
        click.option("--include-unsafe", is_flag=True, help="Include POST/PUT/PATCH/DELETE calls."),
        click.option(
            "--mode", default="per-endpoint", show_default=True,
            type=click.Choice(["per-endpoint", "combined"]),
            help="One run per API, or one mixed run per API host.",
        ),
        click.option(
            "--rate", default=10.0, show_default=True, type=click.FloatRange(0, min_open=True),
            help="Requests per second offered to each run.",
        ),
        click.option("--duration", default="30s", show_default=True, callback=_duration),
        click.option("--expected-limit", type=click.FloatRange(min=0, min_open=True)),
    ]  # fmt: skip
    for option in reversed(options):
        fn = option(fn)
    return fn


def _parse_headers(values: tuple[str, ...]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values:
        name, sep, value = raw.partition(":")
        if not sep or not name.strip():
            raise click.BadParameter(f"expected 'Name: value', got {raw!r}", param_hint="--header")
        headers[name.strip()] = value.strip()
    return headers


def _run_discovery(
    url: str, max_pages: int, max_depth: int, wait_ms: int, scope: tuple[str, ...],
    headers: dict[str, str], ignore_https_errors: bool,
) -> DiscoveryResult:  # fmt: skip
    from pydantic import ValidationError

    from lt.discover import DiscoveryError, DiscoveryOptions, discover

    try:
        opts = DiscoveryOptions(
            url=url, max_pages=max_pages, max_depth=max_depth, wait_ms=wait_ms,
            scope=list(scope), headers=headers, ignore_https_errors=ignore_https_errors,
        )  # fmt: skip
    except ValidationError as exc:
        raise click.BadParameter(exc.errors()[0]["msg"], param_hint="URL") from exc
    click.echo(f"discovering APIs on {url} (up to {max_pages} pages)…", err=True)
    try:
        result = discover(opts)
    except DiscoveryError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_INVALID)
    for err in result.errors:
        click.echo(f"warning: {err}", err=True)
    return result


def _select(result: DiscoveryResult, include_unsafe: bool) -> list[Endpoint]:
    click.echo(f"\n{len(result.pages)} page(s) crawled, {len(result.endpoints)} API call(s) seen")
    chosen = []
    for ep in result.endpoints:
        use = ep.in_scope and not ep.sensitive and (ep.safe or include_unsafe)
        flag = "+" if use else "-"
        why = "" if use else (
            " (out of scope)" if not ep.in_scope
            else " (auth-related)" if ep.sensitive
            else " (unsafe method; --include-unsafe)"
        )  # fmt: skip
        click.echo(f"  {flag} {ep.method:<7} {ep.base_url}{ep.template}  x{ep.count}{why}")
        if use:
            chosen.append(ep)
    if result.out_of_scope_hosts:
        hosts = ", ".join(result.out_of_scope_hosts)
        click.echo(f"  out-of-scope hosts ignored: {hosts} (add with --scope)")
    return chosen


def _plan(mode: str, rate: float, duration: str, expected_limit: float | None) -> LoadPlan:
    from lt.discover import LoadPlan

    return LoadPlan(
        mode=cast(Any, mode), rate=rate, duration=duration, expected_limit_rps=expected_limit
    )


def _env_name(header: str) -> str:
    return "LT_HEADER_" + re.sub(r"[^A-Z0-9]", "_", header.upper())


@main.command("discover")
@_discovery_options
@click.option("--out-dir", default="scans", show_default=True, type=click.Path(file_okay=False))
def discover_cmd(
    url: str, max_pages: int, max_depth: int, wait_ms: int, scope: tuple[str, ...],
    headers: tuple[str, ...], ignore_https_errors: bool, include_unsafe: bool, mode: str,
    rate: float, duration: str, expected_limit: float | None, out_dir: str,
) -> None:  # fmt: skip
    """Crawl URL with a headless browser and write a load profile for each API it calls."""
    import yaml

    from lt.discover import build_configs

    hdrs = _parse_headers(headers)
    result = _run_discovery(url, max_pages, max_depth, wait_ms, scope, hdrs, ignore_https_errors)
    chosen = _select(result, include_unsafe)
    if not chosen:
        click.echo("no in-scope APIs found; nothing written", err=True)
        sys.exit(1)
    # Header values stay out of files; generated configs reference environment variables.
    refs = {name: f"${{{_env_name(name)}}}" for name in hdrs}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    click.echo("")
    for _, data in build_configs(
        chosen,
        _plan(mode, rate, duration, expected_limit),
        refs,
        verify_tls=not ignore_https_errors,
    ):
        path = out / f"{re.sub(r'[^a-z0-9]+', '-', str(data['name']).lower()).strip('-')}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        click.echo(f"wrote {path}")
    if refs:
        names = ", ".join(_env_name(n) for n in hdrs)
        click.echo(f"\nexport {names} before `lt run -c <file>`")


@main.command("scan")
@_discovery_options
@click.option("--output-dir", default="runs", show_default=True, type=click.Path(file_okay=False))
@click.option("--strict", is_flag=True, help="Exit 1 if any run's analysis fails (CI gate).")
def scan_cmd(
    url: str, max_pages: int, max_depth: int, wait_ms: int, scope: tuple[str, ...],
    headers: tuple[str, ...], ignore_https_errors: bool, include_unsafe: bool, mode: str,
    rate: float, duration: str, expected_limit: float | None, output_dir: str, strict: bool,
) -> None:  # fmt: skip
    """Discover every API behind URL, then load-test and analyze each one."""
    from lt.analyze import AnalysisError, analyze_run
    from lt.discover import build_configs
    from lt.engine import run_load

    hdrs = _parse_headers(headers)
    result = _run_discovery(url, max_pages, max_depth, wait_ms, scope, hdrs, ignore_https_errors)
    chosen = _select(result, include_unsafe)
    if not chosen:
        click.echo("no in-scope APIs found; nothing to run", err=True)
        sys.exit(1)
    rows: list[tuple[str, str, str]] = []
    failed = False
    for _, data in build_configs(
        chosen,
        _plan(mode, rate, duration, expected_limit),
        hdrs,
        verify_tls=not ignore_https_errors,
    ):
        name = str(data["name"])
        click.echo(f"\n== {name}")
        try:
            cfg = parse_config(data, expand_env=False)
            res = run_load(cfg, output_dir=Path(output_dir))
        except (ConfigError, SafetyError) as exc:
            click.echo(f"skipped: {exc}", err=True)
            rows.append((name, "skipped", "-"))
            continue
        if res.interrupted:
            rows.append((name, "interrupted", str(res.run_dir)))
            break
        try:
            verdict = "PASS" if analyze_run(res.run_dir)["pass"] else "FAIL"
        except AnalysisError:
            verdict = "n/a"
        failed |= verdict == "FAIL"
        m = res.summary["means"]
        click.echo(
            f"accepted {m['accepted_rps']:.1f} rps, 429 {m['429_rps']:.1f} rps, "
            f"p99 {res.summary['latency_ms']['p99']} ms -> {verdict}"
        )
        rows.append((name, verdict, str(res.run_dir)))
    click.echo("\nscan summary")
    for name, verdict, where in rows:
        click.echo(f"  [{verdict:^11}] {name}  {where}")
    if strict and failed:
        sys.exit(1)
