# lt — open-model load generator and API rate-limit verifier

`lt` is a cross-platform Python CLI that generates **coordinated-omission-safe** HTTP load
using an **open (arrival-rate) model** and **verifies API rate limiters**: sustained
capacity, burst size, step capacity curve, multi-tenant fairness, rate-limit headers and
window semantics (token bucket vs fixed window vs sliding window). Results are
reproducible CSV/JSON artifacts suitable for CI/CD gates. No Docker required.

## Features

- Open-model scheduler: arrivals are a pure function of the profile (constant, step,
  ramp, idle phases), sharded and interleaved across N shards; never waits for responses,
  never skips events when late.
- Latency measured from the **scheduled** time (CO-safe) into HDR histograms, per second
  and per status family (`2xx`, `3xx`, `4xx`, `429`, `5xx`, `error`).
- httpx engine, HTTP/2 by default (ALPN over TLS; plain `http://` uses HTTP/1.1), sharded
  connection pools, optional warm-up, full body reads for connection reuse.
- Multiprocessing sharding for 10k+ RPS with a parent aggregator and loss-free
  backpressure.
- Rate-limit analysis: `sustained`, `burst` (b and refill rate via regression),
  `step` (capacity curve + knee), `fairness` (max-min fair share), `headers`
  (`Retry-After`, `RateLimit-*`, `X-RateLimit-*`), `window_semantics` classification.
- Guardrails: domain allowlist (on by default), hard RPS cap, Ctrl-C kill switch,
  redaction of `Authorization`, `X-API-Key`, `Cookie`, … in logs and artifacts.
- Deterministic local demo server with pluggable limiter for tests and experiments.

## Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Python 3.11+ on Linux, macOS or Windows. `uvloop` is installed automatically where
supported (not on Windows).

## Quickstart

```bash
# 1. start a local limiter: token bucket, 800 req/s, burst 100
lt demo-server --rate 800 --burst 100

# 2. in another shell
lt validate -c examples/constant-1000rps.yaml
lt run      -c examples/constant-1000rps.yaml          # prints summary + run dir
lt analyze  runs/<run_id>
lt report   runs/<run_id>
```

Sample `lt analyze` output:

```
analysis
  sustained  [PASS] accepted 800.0 rps vs target 800.0 (+0.00%, tol +/-5%), 429 200.0 rps
  burst      [info] inferred b=98.3, refill~800.0/s, first window 898
  headers    style=both, Retry-After on 429s 100.0%
  semantics  token-bucket (confidence 0.62)
  overall    PASS
```

## Commands

| Command | Purpose |
|---|---|
| `lt run -c cfg.yaml [--rps --duration --workers --processes --max-rps-cap --http2/--no-http2 --connections --streams --concurrency --events-sample-rate --output-dir --run-id]` | Execute a profile; write artifacts to `runs/<run_id>/` |
| `lt validate -c cfg.yaml [--max-rps-cap]` | Schema + guardrail check; exit 2 on failure |
| `lt analyze <run_dir> [--expected-limit --expected-burst --tolerance --fairness-threshold --json --strict]` | Write `analysis.json`; `--strict` exits 1 if any check fails |
| `lt report <run_dir> [--json]` | Human-readable summary (+ analysis verdicts if present) |
| `lt demo-server [--rate --burst --window --algo token-bucket\|fixed-window\|sliding-window --scope global\|per-key --latency-ms]` | Local rate-limited API |
| `lt serve [--host --port --runs-dir --static-dir --allow-no-auth]` | REST API for the web UI ([../frontend](../frontend)) |
| `lt discover URL [--max-pages --max-depth --scope -H 'Name: value' --include-unsafe --mode --rate --duration --out-dir]` | Crawl a web app with headless Chromium and write a load profile for every API it calls |
| `lt scan URL [same options] [--output-dir --strict]` | Discover, then load-test and analyze every API in turn (`--strict` = CI gate) |

### Automatic API discovery

```bash
playwright install chromium            # once
lt scan https://app.staging.example.com --rate 20 --duration 30s \
        -H "Authorization: Bearer $TOKEN"
```

`lt` opens the URL in headless Chromium, follows same-site links (skipping logout/delete
links and downloads), and records every XHR/fetch call. Calls are grouped by method and
path template (`/users/123` → `/users/{id}`). By default only **GET/HEAD/OPTIONS** calls to
the page's own site (`app.x.com`, `x.com`, `*.x.com`) are load-tested; auth-related calls
(login, token, session, …) are never replayed with their payload. Use `--scope` to add API
hosts and `--include-unsafe` to replay data-modifying calls against disposable
environments. `lt discover` writes the generated YAML instead of running it, with header
values replaced by `${LT_HEADER_*}` references so secrets never land on disk.

`--rps`/`--duration` replace the profile with a single constant step. `--max-rps-cap`
can only lower the configured cap.

## Configuration

```yaml
version: 1
name: my-test
base_url: https://api.staging.example.com
default_headers: { X-API-Key: "${API_KEY}" }     # ${VAR} / ${VAR:-default} expansion
safety:
  allowlist: [api.staging.example.com, "*.internal.example.com"]
  max_rps_cap: 2000
  require_allowlist: true
model:
  type: open
  workers: 4           # scheduler shards (total, across processes)
  processes: 1         # >1 enables multiprocessing sharding
  seed: 0
  profile:
    - { duration: 5s,  rate: 0 }                  # idle (lets token buckets refill)
    - { duration: 60s, rate: 1000 }               # constant
    - { duration: 60s, rate: 1000, end_rate: 3000 }  # linear ramp
http:
  http2: true
  max_connections: 100
  max_streams: 100
  concurrency: 512       # request workers per process
  connect_timeout: 5s
  read_timeout: 10s
  warmup_requests: 0     # e.g. 64 with warmup_path: /healthz
routes:
  - name: list-items
    method: GET
    path: /api/items
    headers: {}
    body: null
    expect_status: [200, 429]
    weight: 1.0
    tenant: key-a        # fairness grouping (defaults to route name)
output:
  events_sample_rate: 0.0   # >0 writes sampled raw events to events.jsonl
analysis:
  expected_limit_rps: 1000
  expected_burst: 500
  tolerance: 0.05
  fairness_threshold: 1.2
```

A `rate: 0` step is an explicit idle phase; every profile must contain a step with a
positive rate. Route `path` must be relative (absolute/protocol-relative URLs are rejected
so the allowlist cannot be bypassed).

## Run artifacts

| File | Content |
|---|---|
| `metrics.csv` | per second: `second, attempted_rps, accepted_rps, 429_rps, error_rps, p50_ms, p90_ms, p95_ms, p99_ms, dropped` |
| `routes.csv` | per second and route: attempted / accepted / 429 / errors |
| `fine.csv` | 100 ms bins (attempted / accepted / 429) for burst and window analysis |
| `metrics.json` | totals, means, latency (overall and per family), status codes, error types, headers, scheduler accuracy, profile |
| `summary.json` | high-level rollup used by `lt report` |
| `analysis.json` | written by `lt analyze` |
| `config.json` | the effective config, **redacted** |
| `run.log` | structured JSON log |
| `events*.jsonl` | optional sampled raw events |

Accepted = 2xx/3xx; errors = 4xx (≠429) + 5xx + client errors (timeouts, connection
errors, client queue overflow).

## Safety guardrails

- The `base_url` host must match `safety.allowlist` (exact or `*.suffix`); with
  `require_allowlist: true` (default) an empty allowlist is an error.
- The profile peak rate must be ≤ `min(safety.max_rps_cap, --max-rps-cap)`
  (absolute ceiling 100k).
- Redirects are off by default; when enabled, every hop is re-checked against the
  allowlist.
- Proxy environment variables are ignored unless `http.trust_env: true`.
- Ctrl-C (or SIGTERM) stops scheduling immediately, cancels in-flight requests and
  flushes artifacts; a second Ctrl-C aborts.
- Sensitive headers/fields are redacted in logs, `config.json` and summaries.

## REST API (`lt serve`)

`lt serve` exposes the engine over HTTP for the React console in [../frontend](../frontend).
Interactive docs are at `/api/docs`. Runs execute in a dedicated worker subprocess (one
active run at a time); stopping a run is graceful, like a single Ctrl-C.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Version and whether a token is required (public) |
| `GET /api/v1/examples` | Bundled example configs |
| `POST /api/v1/configs/validate` | Schema + guardrail check with a plan summary |
| `GET/POST /api/v1/runs` | List runs / start a run (`{yaml, overrides}`) |
| `GET/DELETE /api/v1/runs/{id}` | Run detail (summary, metrics, analysis, artifacts) / delete |
| `GET /api/v1/runs/{id}/timeseries` | Per-second metrics plus live progress |
| `GET /api/v1/runs/{id}/logs?tail=N` | Parsed `run.log` records |
| `POST /api/v1/runs/{id}/stop` | Graceful stop (`{"force": true}` kills) |
| `POST /api/v1/runs/{id}/analyze` | Run the limiter analysis with optional overrides |
| `GET /api/v1/runs/{id}/artifacts/{name}` | Download an artifact |
| `GET/POST/DELETE /api/v1/demo-server`, `GET …/stats` | Manage the local demo server |
| `GET/POST /api/v1/scans` | List scans / start one (`{discovery: {url, …}, plan, auto_run}`) |
| `GET/DELETE /api/v1/scans/{id}` | Discovered endpoints and per-API results / delete |
| `POST /api/v1/scans/{id}/run` | Load-test selected endpoints (`{endpoint_ids, plan}`) |
| `POST /api/v1/scans/{id}/cancel` | Stop discovery or the remaining runs |

Server-side settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `LT_API_TOKEN` | unset | Bearer token required on every `/api/v1` call except health. Required when binding a non-loopback host. |
| `LT_API_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Server-side target allowlist, enforced **in addition to** each config's own allowlist (`*` disables it). |
| `LT_API_MAX_RPS_CAP` | `100000` | Server-side RPS ceiling applied to every run. |
| `LT_API_RUNS_DIR` | `runs` | Artifact directory. |
| `LT_API_STATIC_DIR` | unset | Serve a built frontend (`frontend/dist`) from the same origin. |
| `LT_API_CORS_ORIGINS` | unset | Comma-separated origins, only if the UI is on another origin. |
| `LT_API_EXAMPLES_DIR` | `examples/` | Example configs offered in the UI. |

Configs submitted through the API never expand `${VAR}` references (to avoid leaking the
server's environment); they are rejected with a clear error instead.

## Tuning tips

- httpx is CPU-bound: plan for roughly 1–2k RPS per process on Linux/macOS and
  ~0.7–1k on Windows. Use `processes` for more (see [docs/SCALING.md](docs/SCALING.md)).
- Watch `scheduler.lag_p99_ms` and `rate_error_pct` in the summary; growing lag means
  the client host is saturated and results are not trustworthy.
- Warm connections on an unlimited path (`warmup_path: /healthz`) before burst tests.
- For HTTP/1.1 targets, in-flight requests ≤ `max_connections`; size it to
  `rate × p99 latency`.

## Development

```bash
pip install -e ".[dev]"
pre-commit install
tools/check.sh            # ruff, black --check, mypy, pytest + coverage (>= 85%)
pytest --run-slow         # includes the 1000 RPS accuracy test
python tools/perf_harness.py --scale 5   # limiter accuracy harness
python tools/throughput_probe.py         # host client+server capacity probe
```

Documentation: [architecture](docs/ARCHITECTURE.md) ·
[design decisions](docs/DESIGN_DECISIONS.md) · [scaling](docs/SCALING.md) ·
[runbook](docs/RUNBOOK.md) · [limiter tests](docs/LIMITER_TESTS.md).

## License

Apache-2.0 — see [LICENSE](../LICENSE).
