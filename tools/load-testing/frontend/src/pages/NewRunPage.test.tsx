import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { RunDetail, ValidationResult } from '@/lib/types';
import { mockFetch, renderRoute } from '@/test/utils';
import { NewRunPage } from './NewRunPage';

const valid: ValidationResult = {
  valid: true,
  errors: [],
  warnings: ['safety.require_allowlist is disabled'],
  summary: {
    name: 'test',
    base_url: 'http://127.0.0.1:8080',
    host: '127.0.0.1',
    peak_rps: 100,
    effective_cap: 1000,
    duration_s: 10,
    expected_requests: 1000,
    processes: 1,
    workers: 4,
    concurrency_per_process: 512,
    http2: true,
    profile: [{ duration_s: 10, rate: 100, end_rate: null, name: null }],
    routes: [{ name: 'items', method: 'GET', path: '/api/items', weight: 1, tenant: null }],
  },
};

const started = { run_id: 'r-1', status: 'running' } as RunDetail;

function setup(validation: ValidationResult) {
  const fetch = mockFetch({
    'GET /examples': () => [{ name: 'burst', filename: 'burst.yaml', yaml: 'name: burst\n' }],
    'POST /configs/validate': () => validation,
    'POST /runs': () => started,
  });
  const utils = renderRoute(
    [
      { path: '/runs/new', element: <NewRunPage /> },
      { path: '/runs/:id', element: <div>run page</div> },
    ],
    '/runs/new',
  );
  return { fetch, ...utils };
}

describe('NewRunPage', () => {
  it('validates the config and starts a run after confirmation', async () => {
    const user = userEvent.setup();
    const { fetch, router } = setup(valid);

    expect(await screen.findByText('Valid')).toBeInTheDocument();
    expect(screen.getByText('safety.require_allowlist is disabled')).toBeInTheDocument();
    expect(screen.getByText('/api/items')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /start run/i }));
    const dialog = await screen.findByRole('dialog', { hidden: true });
    expect(within(dialog).getByText(/Only test systems you are authorized/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /start run/i, hidden: true }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/runs/r-1'));
    const startCall = fetch.mock.calls.find(
      ([url, init]) => String(url).endsWith('/api/v1/runs') && init?.method === 'POST',
    );
    expect(JSON.parse(String(startCall?.[1]?.body))).toMatchObject({ yaml: expect.any(String) });
  });

  it('lists validation errors and keeps start disabled', async () => {
    setup({ valid: false, errors: ['model: Field required'], warnings: [], summary: null });
    expect(await screen.findByText('model: Field required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start run/i })).toBeDisabled();
  });

  it('loads an example into the editor', async () => {
    const user = userEvent.setup();
    setup(valid);
    const select = await screen.findByRole('combobox', { name: /load example/i });
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, 'burst.yaml');
    expect(screen.getByRole('textbox', { name: /load profile yaml/i })).toHaveValue(
      'name: burst\n',
    );
  });
});
