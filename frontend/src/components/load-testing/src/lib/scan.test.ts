import { describe, expect, it } from 'vitest';

import { endpointFlags, isDefaultSelected, parseHeaders, splitList } from './scan';
import type { DiscoveredEndpoint } from './types';

const ep = (over: Partial<DiscoveredEndpoint> = {}): DiscoveredEndpoint => ({
  id: 'a',
  method: 'GET',
  base_url: 'http://127.0.0.1:1',
  path: '/api/x',
  template: '/api/x',
  resource_type: 'fetch',
  in_scope: true,
  sensitive: false,
  safe: true,
  count: 1,
  status: 200,
  content_type: 'application/json',
  has_body: false,
  pages: [],
  ...over,
});

describe('parseHeaders', () => {
  it('parses name/value lines and keeps colons in values', () => {
    expect(parseHeaders('Authorization: Bearer a:b\n\n X-Key : 1 ')).toEqual({
      headers: { Authorization: 'Bearer a:b', 'X-Key': '1' },
      error: null,
    });
  });

  it('rejects malformed lines', () => {
    expect(parseHeaders('no colon').error).toContain('no colon');
    expect(parseHeaders('Bad Name: x').error).toContain('Bad Name');
  });
});

describe('selection helpers', () => {
  it('preselects only safe, in-scope, non-auth endpoints', () => {
    expect(isDefaultSelected(ep())).toBe(true);
    expect(isDefaultSelected(ep({ in_scope: false }))).toBe(false);
    expect(isDefaultSelected(ep({ sensitive: true }))).toBe(false);
    expect(isDefaultSelected(ep({ safe: false, method: 'POST' }))).toBe(false);
    expect(isDefaultSelected(ep({ safe: false, method: 'POST' }), true)).toBe(true);
  });

  it('describes why an endpoint needs attention', () => {
    expect(endpointFlags(ep())).toEqual([]);
    expect(endpointFlags(ep({ safe: false, status: 500 }))).toEqual(['modifies data', 'HTTP 500']);
    expect(endpointFlags(ep({ status: null, in_scope: false }))).toEqual([
      'out of scope',
      'no response',
    ]);
  });

  it('splits host lists', () => {
    expect(splitList(' a.com, *.b.com\nc.com ')).toEqual(['a.com', '*.b.com', 'c.com']);
  });
});
