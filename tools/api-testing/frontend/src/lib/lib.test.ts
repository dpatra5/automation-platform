import { describe, expect, it } from 'vitest';

import { formatBytes, formatDate, formatMs, prettyBody } from './format';
import { inferSchema, newRequestSpec, toCurl } from './request';

describe('toCurl', () => {
  it('renders method, query, headers, auth and body with shell quoting', () => {
    const spec = {
      ...newRequestSpec(),
      method: 'POST' as const,
      url: 'https://api.test/items',
      params: [{ key: 'q', value: 'a b', enabled: true }],
      headers: [{ key: 'X-Note', value: "it's", enabled: true }],
      auth: { ...newRequestSpec().auth, type: 'bearer' as const, token: '{{token}}' },
      body: { mode: 'json' as const, content: '{"a":1}', form: [] },
    };
    const curl = toCurl(spec);
    expect(curl).toContain("curl -X POST 'https://api.test/items?q=a%20b'");
    expect(curl).toContain(`-H 'X-Note: it'\\''s'`);
    expect(curl).toContain("-H 'Authorization: Bearer {{token}}'");
    expect(curl).toContain("-H 'Content-Type: application/json'");
    expect(curl).toContain(`--data-raw '{"a":1}'`);
  });
});

describe('inferSchema', () => {
  it('infers nested objects and arrays', () => {
    expect(inferSchema({ id: 1, tags: ['x'], price: 1.5, meta: null })).toEqual({
      type: 'object',
      required: ['id', 'tags', 'price', 'meta'],
      properties: {
        id: { type: 'integer' },
        tags: { type: 'array', items: { type: 'string' } },
        price: { type: 'number' },
        meta: { type: 'null' },
      },
    });
  });
});

describe('format helpers', () => {
  it('formats sizes, durations and bodies', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatMs(12.4)).toBe('12 ms');
    expect(formatMs(1500)).toBe('1.50 s');
    expect(prettyBody('{"a":1}', 'application/json')).toBe('{\n  "a": 1\n}');
    expect(prettyBody('plain', 'text/plain')).toBe('plain');
    expect(formatDate('2024-01-01T00:00:00')).toBe(new Date('2024-01-01T00:00:00Z').toLocaleString());
  });
});
