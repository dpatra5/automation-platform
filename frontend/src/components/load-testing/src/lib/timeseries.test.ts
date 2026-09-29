import { describe, expect, it } from 'vitest';

import { mergeTimeseries, profilePoints, routeTotals } from './timeseries';
import type { Timeseries } from './types';

const row = (second: number, accepted: number, p99: number | null) => ({
  second,
  attempted_rps: 10,
  accepted_rps: accepted,
  '429_rps': 10 - accepted,
  error_rps: 0,
  p50_ms: p99 === null ? null : 1,
  p90_ms: p99 === null ? null : 2,
  p95_ms: null,
  p99_ms: p99,
  dropped: 0,
});

describe('mergeTimeseries', () => {
  it('prefers finalized metrics and fills the tail from live progress', () => {
    const ts: Timeseries = {
      metrics: [row(0, 8, 3), row(1, 7, 4)],
      live: [
        { second: 0, attempted: 10, accepted: 9, rate_limited: 1, errors: 0 },
        { second: 2, attempted: 10, accepted: 6, rate_limited: 4, errors: 0 },
      ],
      routes: [],
    };
    const points = mergeTimeseries(ts);
    expect(points.map((p) => p.second)).toEqual([0, 1, 2]);
    expect(points[0]).toMatchObject({ accepted: 8, p99: 3 });
    expect(points[2]).toMatchObject({ accepted: 6, rateLimited: 4, p99: null });
  });

  it('handles missing data', () => {
    expect(mergeTimeseries(undefined)).toEqual([]);
  });
});

describe('routeTotals', () => {
  it('aggregates per route and sorts by volume', () => {
    const ts: Timeseries = {
      metrics: [],
      live: [],
      routes: [
        { second: 0, route: 'a', attempted: 1, accepted: 1, '429': 0, errors: 0 },
        { second: 0, route: 'b', attempted: 5, accepted: 3, '429': 2, errors: 0 },
        { second: 1, route: 'a', attempted: 2, accepted: 1, '429': 1, errors: 0 },
      ],
    };
    expect(routeTotals(ts)).toEqual([
      { route: 'b', attempted: 5, accepted: 3, rateLimited: 2, errors: 0 },
      { route: 'a', attempted: 3, accepted: 2, rateLimited: 1, errors: 0 },
    ]);
  });
});

describe('profilePoints', () => {
  it('builds step and ramp boundaries', () => {
    expect(
      profilePoints([
        { duration_s: 5, rate: 100, end_rate: null, name: null },
        { duration_s: 10, rate: 100, end_rate: 500, name: 'ramp' },
      ]),
    ).toEqual([
      { t: 0, rate: 100 },
      { t: 5, rate: 100 },
      { t: 5, rate: 100 },
      { t: 15, rate: 500 },
    ]);
  });
});
