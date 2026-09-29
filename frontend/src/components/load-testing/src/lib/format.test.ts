import { describe, expect, it } from 'vitest';

import {
  formatBytes,
  formatDuration,
  formatInt,
  formatMs,
  formatPct,
  formatRelative,
  formatRps,
  humanize,
} from './format';

describe('format helpers', () => {
  it('renders placeholders for missing values', () => {
    for (const fn of [formatInt, formatRps, formatMs, formatPct, formatDuration]) {
      expect(fn(null)).toBe('—');
      expect(fn(undefined)).toBe('—');
      expect(fn(Number.NaN)).toBe('—');
    }
  });

  it('formats numbers', () => {
    expect(formatInt(1234567)).toBe('1,234,567');
    expect(formatRps(799.96)).toBe('800.0');
    expect(formatPct(0.1234)).toBe('12.3%');
    expect(formatPct(0.5, 0)).toBe('50%');
  });

  it('formats latency with adaptive precision', () => {
    expect(formatMs(1.234)).toBe('1.23 ms');
    expect(formatMs(45.67)).toBe('45.7 ms');
    expect(formatMs(2500)).toBe('2.50 s');
  });

  it('formats durations', () => {
    expect(formatDuration(0.25)).toBe('250 ms');
    expect(formatDuration(30)).toBe('30 s');
    expect(formatDuration(125)).toBe('2m 5s');
    expect(formatDuration(3720)).toBe('1h 2m');
  });

  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('formats relative time', () => {
    const now = Date.parse('2026-01-01T00:10:00Z');
    expect(formatRelative('2026-01-01T00:05:00Z', now)).toBe('5 minutes ago');
    expect(formatRelative(null, now)).toBe('—');
  });

  it('humanizes keys', () => {
    expect(humanize('mean_accepted_rps')).toBe('mean accepted RPS');
    expect(humanize('deviation_pct')).toBe('deviation %');
  });
});
