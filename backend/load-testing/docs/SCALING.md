# Scaling guide

## Capacity per process

httpx is CPU-bound. Measure your host with:

```bash
python tools/throughput_probe.py --concurrency 64
```

Typical sustained open-model rates per client process (with CO-safe accuracy intact):

| Platform | Guide |
|---|---|
| Linux + uvloop, modern x86/ARM core | 1,500–2,500 RPS |
| macOS + uvloop | 1,200–2,000 RPS |
| Windows (Proactor, no uvloop) | 700–1,100 RPS |

`lt run` logs a warning when `peak_rate / processes` exceeds the platform guide.

## Reaching 10k RPS (8+ cores)

1. Use multiprocessing sharding: `processes ≈ ceil(peak / per-process guide)`, leaving one
   core for the parent aggregator and one for the OS. For 10k on 8 cores:
   `processes: 6–8`, `workers: 16` (shards must be ≥ processes; use a multiple).
2. Connections: per process, in-flight ≈ `rate_per_process × p99_latency`.
   For HTTP/1.1 set `max_connections` ≥ that (e.g. 1,250 RPS × 50 ms ≈ 64). For HTTP/2
   `max_connections × max_streams` must exceed it; fewer connections are fine.
3. `concurrency` (workers per process) ≥ in-flight target; the default 512 is plenty.
4. Keep `events_sample_rate` at 0 or ≤ 0.01 for high rates.
5. Verify with `summary.json → scheduler`: `mean_abs_window_error_pct` < 5 and
   `lag_p99_ms` small relative to the latency you care about. Check
   `metrics.json → execution.snapshot_backpressure` stays low and `dropped` is 0.

Example: [examples/step-to-10k.yaml](../examples/step-to-10k.yaml).

## OS / network tuning

Linux:

```bash
ulimit -n 1048576                               # file descriptors (connections)
sudo sysctl -w net.ipv4.ip_local_port_range="1024 65535"
sudo sysctl -w net.ipv4.tcp_tw_reuse=1          # reuse TIME_WAIT for new outbound conns
sudo sysctl -w net.core.somaxconn=65535         # if also running the demo server
sudo sysctl -w net.ipv4.tcp_fin_timeout=15
```

macOS:

```bash
ulimit -n 65536
sudo sysctl -w kern.ipc.somaxconn=4096
sudo sysctl -w net.inet.ip.portrange.first=16384
```

Windows: ephemeral ports (`netsh int ipv4 set dynamicport tcp start=10000 num=55535`);
security/EDR software that hooks sockets can cost several hundred µs per request —
measure with the probe and prefer Linux runners for large tests.

General:

- Keep connections persistent (default); connection churn exhausts ephemeral ports.
- Run the load generator close to the target (same region/VPC) so network RTT doesn't
  dominate `max_connections` sizing.
- Pin CPU frequency / disable power saving on dedicated load hosts.
- Do not co-locate the demo server with a high-rate client: a single-process Python
  server tops out around 1–3k RPS.

## Beyond one host

Run `lt run` on several hosts with the same profile scaled by `1/hosts` and a synchronized
start (e.g. `at`/cron on NTP-synced machines), then compare per-host `metrics.csv`.
Aggregating across hosts is out of scope for Stage 1.
