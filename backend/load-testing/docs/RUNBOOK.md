# Runbook

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `safety check failed: host 'x' is not in safety.allowlist` | Target host not allowlisted | Add the exact host or `*.suffix` to `safety.allowlist` (only for systems you are authorized to test) |
| `profile peak rate N RPS exceeds max_rps_cap M` | Plan above cap | Lower the profile or raise `safety.max_rps_cap` deliberately |
| `environment variable 'X' is not set` | `${X}` in config | Export it or use `${X:-default}` |
| `run directory already exists` | `--run-id` reused | Pick a new id or omit it |
| `error_types.ConnectError` / `ConnectTimeout` | Target down, wrong port, firewall | `curl` the base URL; check `connect_timeout` |
| `error_types.PoolTimeout` | More in-flight than connections for too long | Raise `max_connections` (HTTP/1.1) or `max_streams` (HTTP/2) |
| `error_types.ClientQueueFull` / `dropped > 0` | Client cannot keep up | Add `processes`, raise `concurrency`/`queue_size` |
| `error_types.Cancelled` | Ctrl-C, or requests still in flight after the drain timeout | Expected on interrupt; otherwise raise `read_timeout` |
| `HostNotAllowedError` | Redirect to a non-allowlisted host | Intended; fix the target or allowlist |
| Exit code 130 | Run interrupted | Artifacts are still written for the elapsed part |
| `worker process(es) exited during startup` | Import/config error in a child | Run with `--processes 1` to see the error directly |

## Is the client saturated?

Check `lt report` / `summary.json`:

- `scheduler.lag_p99_ms` well above a few ms, or growing over the run.
- `mean_abs_window_error_pct` > 2 % (1k RPS) or > 5 % (10k RPS).
- `metrics.json → execution.snapshot_backpressure` large (multiprocess).
- Latency grows while the server reports low latency.

Then add processes, reduce `events_sample_rate`, or move to a bigger host.

## Interpreting `analysis.json`

- **sustained** — mean accepted RPS over steady windows of the longest constant step
  (first `warmup_windows` skipped). `target_rps = min(asked, expected_limit_rps)`. `pass`
  if within `tolerance`. `mean_429_rps` should be ≈ `expected_overflow_rps`.
- **burst** — for the first step after an idle phase (or the run start) that produced
  429s: `first_window_acceptances`, and a regression `C(t) = b + r·t` over cumulative
  acceptances after the bucket drains → `inferred_burst_b`, `refill_rate_estimate`.
  Connection set-up during the burst wastes refill; use `warmup_path`.
- **step** — `capacity_curve` of constant steps; `knee_point` is the first step where
  the 429 rate exceeds `knee_429_threshold` (from below) or the marginal accepted gain
  per extra asked RPS drops below `knee_marginal_threshold`. `estimated_capacity_rps` is
  the mean accepted at and after the knee.
- **fairness** — per tenant (route `tenant`, default route name) accepted/attempted RPS,
  `fairness_ratio` = max/min accepted, and `fair_share_ratio` comparing each tenant with
  its max-min fair share (identical under equal demand). `pass` uses `fair_share_ratio`.
- **headers** — presence ratios and value distributions of `Retry-After`,
  `RateLimit-*` and `X-RateLimit-*`; `style` is `ietf`, `x-ratelimit`, `both` or `none`.
- **window_semantics** — see [LIMITER_TESTS.md](LIMITER_TESTS.md#window-semantics).

## Operational checklist

1. `lt validate -c cfg.yaml` in CI before any run.
2. Get written authorization and coordinate with the target's owners/on-call.
3. Start low (`--rps` small, short `--duration`), inspect `lt report`, then ramp.
4. Keep a terminal ready: Ctrl-C stops scheduling immediately.
5. Archive `runs/<run_id>/` (no secrets are stored; verify `config.json` redaction if you
   added custom sensitive headers — extend `SENSITIVE_KEYS` if needed).
