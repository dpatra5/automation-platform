import { describe, expect, it, vi } from 'vitest';

import { mockFetch } from '@/test/utils';
import { api, ApiError, errorMessage, onUnauthorized, tokenStore } from './api';

describe('errorMessage', () => {
  it('reads string details', () => {
    expect(errorMessage({ detail: 'boom' }, 'x')).toBe('boom');
  });

  it('flattens FastAPI validation errors', () => {
    const body = { detail: [{ loc: ['body', 'rate'], msg: 'must be > 0' }] };
    expect(errorMessage(body, 'x')).toBe('rate: must be > 0');
  });

  it('falls back when shape is unknown', () => {
    expect(errorMessage('nope', 'fallback')).toBe('fallback');
  });
});

describe('api client', () => {
  it('sends the bearer token when one is stored', async () => {
    tokenStore.set('secret');
    const fetch = mockFetch({ 'GET /runs': () => [] });
    await api.listRuns();
    const init = fetch.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer secret');
  });

  it('raises ApiError with the server detail', async () => {
    mockFetch({
      'POST /runs': () =>
        new Response(JSON.stringify({ detail: 'already running' }), { status: 409 }),
    });
    await expect(api.startRun({ yaml: 'x' })).rejects.toMatchObject({
      status: 409,
      message: 'already running',
    });
  });

  it('notifies listeners on 401', async () => {
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    mockFetch({ 'GET /runs': () => new Response('{}', { status: 401 }) });
    await expect(api.listRuns()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledOnce();
    off();
  });

  it('reports network failures clearly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(api.health()).rejects.toMatchObject({ status: 0 });
  });

  it('encodes run ids in paths', async () => {
    const fetch = mockFetch({});
    await api.getRun('a/b').catch(() => undefined);
    expect(String(fetch.mock.calls[0]?.[0])).toContain('/runs/a%2Fb');
  });
});
