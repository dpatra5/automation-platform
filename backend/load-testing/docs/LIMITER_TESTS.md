# Testing rate limiters

All tests follow the same loop: run → analyze → gate.

```bash
lt run -c my-test.yaml
lt analyze runs/<run_id> --strict        # exit 1 if any expectation fails
```

Set expectations in the config's `analysis:` block or on the CLI
(`--expected-limit`, `--expected-burst`, `--tolerance`, `--fairness-threshold`).

## 1. Sustained capacity

Goal: the limiter admits its configured rate under steady overload.

```yaml
model:
  profile: [{ duration: 60s, rate: 1200 }]   # ~1.2-1.5x the expected limit
analysis: { expected_limit_rps: 1000, tolerance: 0.05 }
```

Pass: `sustained.mean_accepted_rps` within ±5 % of 1000, `mean_429_rps ≈ 200`.
Local: `lt demo-server --rate 1000 --burst 100`.

## 2. Burst capacity

Goal: infer token-bucket capacity `b` and refill rate `r`.

```yaml
model:
  profile:
    - { duration: 5s,  rate: 0 }       # idle long enough to refill: > b / r
    - { duration: 15s, rate: 3000 }    # >> r so the bucket drains in well under 1 s
http: { warmup_requests: 64, warmup_path: /healthz }
analysis: { expected_burst: 500 }
```

The analyzer fits `C(t) = b + r·t` to cumulative acceptances (100 ms bins) after the
bucket drains; the intercept is `b` and the slope is `r`. Accuracy is typically within a
few percent; connection establishment during the burst wastes refill (hence warm-up).
Example: [burst-test.yaml](../examples/burst-test.yaml).

## 3. Step test (capacity discovery)

```yaml
model:
  profile:
    - { duration: 60s, rate: 2000 }
    - { duration: 60s, rate: 4000 }
    - { duration: 60s, rate: 6000 }
    - { duration: 60s, rate: 8000 }
    - { duration: 60s, rate: 10000 }
analysis: { warmup_windows: 2 }
```

Output: `step.capacity_curve` (asked, accepted, 429 rate per step), `knee_point`, and
`estimated_capacity_rps`. Example: [step-to-10k.yaml](../examples/step-to-10k.yaml).
For finer resolution use more, shorter steps, or a ramp (`end_rate`) and inspect
`metrics.csv`.

## 4. Fairness across keys/tenants

Define one route per key with a `tenant` label and equal (or intended) weights:

```yaml
routes:
  - { name: a, tenant: key-a, path: /api/items, headers: { X-API-Key: "${KEY_A}" } }
  - { name: b, tenant: key-b, path: /api/items, headers: { X-API-Key: "${KEY_B}" } }
analysis: { fairness_threshold: 1.2 }
```

`fairness.fair_share_ratio` compares each tenant's accepted RPS with its max-min fair
share of the total accepted capacity. With equal demand this equals max/min accepted.
A proportional global limiter under unequal demand fails this check (heavy tenants
crowd out light ones); per-key limiters pass. Example:
[fairness-two-keys.yaml](../examples/fairness-two-keys.yaml).

## 5. Headers

Every analysis reports header presence and distributions. Recommended gates:
`headers.retry_after_on_429_ratio == 1.0` and `headers.style != "none"`.

## Window semantics

Run a constant overload (≈2× the limit) for ≥ 10 s from a quiet start. The classifier
uses 100 ms bins after the first 429:

| Class | Signal |
|---|---|
| `fixed-window` | Acceptance fraction folded over the window period (1/2/5/10 s) is strongly phase-dependent (CV ≥ 0.5) **and** acceptance resumes at a phase unrelated to traffic onset (clock-aligned boundaries) |
| `sliding-window` (log) | Same periodic pattern, but aligned with traffic onset (the log replays the first window as entries expire) |
| `token-bucket` | Uniform 429s (low phase CV) plus a burst allowance: first window ≥ 15 % above steady, or regression intercept `b ≥ 5 %` of `r` |
| `sliding-window` (counter) | Uniform 429s and no burst allowance (also consistent with GCRA / tiny-burst buckets; confidence 0.5) |
| `not-triggered` | < 1 % of requests were limited |

Caveats: a fixed window whose boundary coincides with the run start (±100 ms) looks
like a sliding log; repeat the run. Heavy client saturation smears arrivals and
invalidates classification — check the scheduler section first.

## Local verification matrix

```bash
python tools/perf_harness.py            # token-bucket burst, fixed-window, sliding-window
python tools/perf_harness.py --scale 5  # same at 5x the rates
pytest tests/integration -q             # scaled-down CI versions
pytest --run-slow -k accuracy           # 1000 RPS, ±2 % scheduler, ±5 % limiter
```
