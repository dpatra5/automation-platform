import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ScanDetail } from '@/lib/types';
import { mockFetch, renderRoute } from '@/test/utils';
import { ScanDetailPage } from './ScanDetailPage';
import { ScansPage } from './ScansPage';

const scan: ScanDetail = {
  id: 'scan-1',
  url: 'http://127.0.0.1:3000/',
  status: 'completed',
  created_at: '2026-01-01T00:00:00Z',
  error: null,
  endpoints_found: 3,
  items_total: 1,
  items_done: 1,
  options: { max_pages: 10, max_depth: 2, wait_ms: 1500, scope: ['127.0.0.1'], header_names: [] },
  pages: ['http://127.0.0.1:3000/'],
  discovery_errors: [],
  out_of_scope_hosts: { 'cdn.example': 2 },
  plan: { mode: 'per-endpoint', rate: 10, duration: '30s' },
  items: [
    {
      name: 'scan GET /api/items @ 127.0.0.1',
      endpoint_ids: ['a'],
      status: 'completed',
      run_id: 'r-1',
      error: null,
      accepted_rps: 10,
      ratio_429: 0,
      p99_ms: 4.2,
      analysis_pass: true,
    },
  ],
  endpoints: [
    {
      id: 'a',
      method: 'GET',
      base_url: 'http://127.0.0.1:3000',
      path: '/api/items',
      template: '/api/items',
      resource_type: 'fetch',
      in_scope: true,
      sensitive: false,
      safe: true,
      count: 2,
      status: 200,
      content_type: 'application/json',
      has_body: false,
      pages: [],
    },
    {
      id: 'b',
      method: 'POST',
      base_url: 'http://127.0.0.1:3000',
      path: '/api/cart',
      template: '/api/cart',
      resource_type: 'fetch',
      in_scope: true,
      sensitive: false,
      safe: false,
      count: 1,
      status: 201,
      content_type: 'application/json',
      has_body: true,
      pages: [],
    },
    {
      id: 'c',
      method: 'GET',
      base_url: 'https://cdn.example',
      path: '/x',
      template: '/x',
      resource_type: 'fetch',
      in_scope: false,
      sensitive: false,
      safe: true,
      count: 2,
      status: 200,
      content_type: null,
      has_body: false,
      pages: [],
    },
  ],
};

describe('ScansPage', () => {
  it('submits the URL and navigates to the scan', async () => {
    const user = userEvent.setup();
    const fetch = mockFetch({
      'GET /scans': () => [],
      'POST /scans': () => ({ ...scan, status: 'discovering' }),
    });
    const { router } = renderRoute(
      [
        { path: '/scans', element: <ScansPage /> },
        { path: '/scans/:id', element: <div>detail</div> },
      ],
      '/scans',
    );
    await user.type(
      screen.getByRole('textbox', { name: /web app url/i }),
      'http://127.0.0.1:3000/',
    );
    await user.click(screen.getByRole('button', { name: /scan & load test/i }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/scans/scan-1'));
    const call = fetch.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      discovery: { url: 'http://127.0.0.1:3000/', max_pages: 10 },
      plan: { mode: 'per-endpoint', rate: 10, duration: '30s' },
      auto_run: true,
      include_unsafe_methods: false,
    });
  });
});

describe('ScanDetailPage', () => {
  it('shows results and re-runs the selected endpoints', async () => {
    const user = userEvent.setup();
    const fetch = mockFetch({
      'GET /scans/scan-1': () => scan,
      'POST /scans/scan-1/run': () => ({ ...scan, status: 'running' }),
    });
    renderRoute([{ path: '/scans/:scanId', element: <ScanDetailPage /> }], '/scans/scan-1');

    expect(await screen.findByText('scan GET /api/items @ 127.0.0.1')).toBeInTheDocument();
    expect(screen.getByText('Pass')).toBeInTheDocument();
    expect(screen.queryByText('/x')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select GET /api/items' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Select POST /api/cart' })).not.toBeChecked();

    await user.click(screen.getByRole('checkbox', { name: 'Select POST /api/cart' }));
    await user.click(screen.getByRole('button', { name: 'Run 2 load tests' }));
    const dialog = await screen.findByRole('dialog', { name: 'Start load tests?', hidden: true });
    expect(dialog).toHaveTextContent('modify data');
    await user.click(screen.getByRole('button', { name: 'Run 2 tests', hidden: true }));

    await waitFor(() =>
      expect(fetch.mock.calls.some(([u]) => String(u).endsWith('/scans/scan-1/run'))).toBe(true),
    );
    const call = fetch.mock.calls.find(([u]) => String(u).endsWith('/run'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ endpoint_ids: ['a', 'b'] });
  });

  it('reveals out-of-scope endpoints on demand', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /scans/scan-1': () => scan });
    renderRoute([{ path: '/scans/:scanId', element: <ScanDetailPage /> }], '/scans/scan-1');
    await user.click(await screen.findByRole('button', { name: /show 1 out-of-scope/i }));
    expect(screen.getByText('/x')).toBeInTheDocument();
  });
});
