import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { RunDetail } from '@/lib/types';
import { mockFetch, renderRoute } from '@/test/utils';
import { RunDetailPage } from './RunDetailPage';

const completed: RunDetail = {
  run_id: 'r-1',
  status: 'completed',
  error: null,
  progress: null,
  config: { name: 'demo', base_url: 'http://127.0.0.1:8080' },
  summary: {
    run_id: 'r-1',
    name: 'demo',
    base_url: 'http://127.0.0.1:8080',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:00:10Z',
    interrupted: false,
    duration_s: 10,
    totals: { attempted: 1000, accepted: 800, '429': 200, errors: 0 },
    means: { attempted_rps: 100, accepted_rps: 80, '429_rps': 20, error_rps: 0 },
    ratios: { accepted: 0.8, '429': 0.2, errors: 0 },
    latency_ms: { p50: 1.2, p90: 2, p95: 3, p99: 4.5, max: 9, mean: 1.5 },
    scheduler: { rate_error_pct: 0.1, mean_abs_window_error_pct: 0.5, lag_p99_ms: 0.8 },
    status_codes: { '200': 800, '429': 200 },
  },
  metrics: null,
  analysis: null,
  artifacts: [{ name: 'summary.json', size: 512 }],
};

const emptySeries = { metrics: [], live: [], routes: [] };

describe('RunDetailPage', () => {
  it('shows summary stats and artifacts for a completed run', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /runs/r-1': () => completed, 'GET /runs/r-1/timeseries': () => emptySeries });
    renderRoute([{ path: '/runs/:runId', element: <RunDetailPage /> }], '/runs/r-1');

    expect(await screen.findByRole('heading', { name: 'demo' })).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('80.0')).toBeInTheDocument();
    expect(screen.getByText('20.0%')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /artifacts/i }));
    expect(screen.getByText('summary.json')).toBeInTheDocument();
  });

  it('offers a graceful stop for running runs', async () => {
    const running: RunDetail = {
      ...completed,
      status: 'running',
      summary: null,
      progress: { elapsed_s: 5, planned_duration_s: 10 },
    };
    mockFetch({ 'GET /runs/r-1': () => running, 'GET /runs/r-1/timeseries': () => emptySeries });
    renderRoute([{ path: '/runs/:runId', element: <RunDetailPage /> }], '/runs/r-1');

    expect(await screen.findByRole('button', { name: /stop gracefully/i })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /run progress/i })).toHaveAttribute(
      'aria-valuenow',
      '50',
    );
  });

  it('renders a not-found state', async () => {
    mockFetch({});
    renderRoute([{ path: '/runs/:runId', element: <RunDetailPage /> }], '/runs/missing');
    expect(await screen.findByText('Run not found')).toBeInTheDocument();
  });
});
