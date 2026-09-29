# Design decisions (ADRs)

## ADR-1: Open (arrival-rate) model with deterministic schedules

**Decision.** Arrival times are computed from the profile (`Λ⁻¹(k)`), not from a
per-iteration sleep or from response completion.
**Why.** Rate-limit verification needs the *offered* rate to be exact and independent of
the system under test; closed-loop generators self-throttle (coordinated omission).
Deterministic schedules make runs reproducible and let the analyzer compute expected
counts per window.
**Trade-off.** No Poisson jitter by default; perfectly periodic arrivals can alias with
limiter refill periods. Multi-route selection uses a seeded RNG to avoid tenant aliasing.

## ADR-2: Interleaved sharding instead of per-shard staggering

**Decision.** Shard `s` owns global events `k ≡ s (mod N)`.
**Why.** This is exactly equivalent to one global schedule, so staggering is perfect for
any `N` and any profile (including ramps), and processes can own disjoint shard sets
with no coordination beyond a common start time.

## ADR-3: httpx with sharded client pools

**Decision.** httpx (HTTP/1.1 and HTTP/2, one API) with several small `AsyncClient`
pools; workers are pinned round-robin.
**Why.** httpx gives HTTP/2 and a well-typed async API. httpcore's pool assignment scans
all connections for every queued request, so throughput collapses with one large pool
(measured: 64 connections in one pool ~140 req/s vs ~1,100 req/s with 16×4). One shared
`SSLContext` avoids ~0.1–0.5 s of CA loading per client.
**Trade-off.** httpx is CPU-heavier than aiohttp; we scale with processes.

## ADR-4: HDR histograms, portable merge

**Decision.** `hdrhistogram` for latency; merge via sparse `(index, count)` pairs.
**Why.** Constant-memory, bounded relative error percentiles. The library's C-backed
`encode`/`add` overflow on 64-bit Windows (`OverflowError: C long`); index-based transfer
is exact for same-precision histograms and fast (~1 ms per 3-sig-fig histogram).

## ADR-5: Loss-free backpressure between processes

**Decision.** Children send delta snapshots through a bounded queue with `put_nowait`; on
`Full` they keep accumulating.
**Why.** Dropping metrics would bias results; blocking would stall the scheduler.
Deltas are additive (counters and histograms), so retrying later is exact. Sampled raw
events use a separate bounded buffer and are the only thing dropped (counted).

## ADR-6: Guardrails on by default

**Decision.** `require_allowlist: true`, hard RPS cap, relative route paths, redirect
re-checking, `trust_env: false`, redaction in logs and artifacts.
**Why.** A load generator is a traffic weapon; accidents (wrong URL, copy-pasted prod
key, corporate proxy) should fail closed.

## ADR-7: Offline analysis from artifacts

**Decision.** `lt analyze` works only from files in the run directory.
**Why.** Analysis can be re-run with different expectations (`--expected-limit`) without
re-generating load, and CI can archive and gate on artifacts.

## ADR-8: Demo server fast path

**Decision.** FastAPI hosts management endpoints (`/healthz`, `/__stats`); limited routes
use a raw ASGI handler inside the same app.
**Why.** FastAPI routing/response overhead dominated at ~1k RPS on laptops; the raw path
keeps the server from becoming the bottleneck while staying deterministic (clock
injection, lazily created limiters).
