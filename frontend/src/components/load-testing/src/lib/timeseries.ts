import type { ConfigSummary, Timeseries } from './types';

/** Target-rate polyline for a load profile (ramps are linear between step boundaries). */
export function profilePoints(steps: ConfigSummary['profile']): { t: number; rate: number }[] {
  const points: { t: number; rate: number }[] = [];
  let t = 0;
  for (const s of steps) {
    points.push({ t, rate: s.rate });
    t += s.duration_s;
    points.push({ t, rate: s.end_rate ?? s.rate });
  }
  return points;
}

export interface ChartPoint {
  second: number;
  attempted: number | null;
  accepted: number | null;
  rateLimited: number | null;
  errors: number | null;
  p50: number | null;
  p90: number | null;
  p99: number | null;
}

/**
 * Finalized per-second rows (metrics.csv) lag the run by the request-timeout grace period, so
 * seconds not yet finalized are filled from the live progress log (throughput only).
 */
export function mergeTimeseries(ts: Timeseries | undefined): ChartPoint[] {
  if (!ts) return [];
  const bySecond = new Map<number, ChartPoint>();
  for (const p of ts.live) {
    bySecond.set(p.second, {
      second: p.second,
      attempted: p.attempted,
      accepted: p.accepted,
      rateLimited: p.rate_limited,
      errors: p.errors,
      p50: null,
      p90: null,
      p99: null,
    });
  }
  for (const r of ts.metrics) {
    bySecond.set(r.second, {
      second: r.second,
      attempted: r.attempted_rps,
      accepted: r.accepted_rps,
      rateLimited: r['429_rps'],
      errors: r.error_rps,
      p50: r.p50_ms,
      p90: r.p90_ms,
      p99: r.p99_ms,
    });
  }
  return [...bySecond.values()].sort((a, b) => a.second - b.second);
}

export interface RouteTotals {
  route: string;
  attempted: number;
  accepted: number;
  rateLimited: number;
  errors: number;
}

export function routeTotals(ts: Timeseries | undefined): RouteTotals[] {
  if (!ts) return [];
  const totals = new Map<string, RouteTotals>();
  for (const r of ts.routes) {
    const t = totals.get(r.route) ?? {
      route: r.route,
      attempted: 0,
      accepted: 0,
      rateLimited: 0,
      errors: 0,
    };
    t.attempted += r.attempted;
    t.accepted += r.accepted;
    t.rateLimited += r['429'];
    t.errors += r.errors;
    totals.set(r.route, t);
  }
  return [...totals.values()].sort((a, b) => b.attempted - a.attempted);
}
