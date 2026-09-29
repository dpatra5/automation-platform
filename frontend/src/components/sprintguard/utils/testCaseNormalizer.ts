import type { TestCase } from '../models/sprintGuard.types'
import type { AutomationReadyTestCase } from '../models/testCase.types'

// Normalizes a case to a canonical shape used for duplicate detection.
export function normalizeForDedup(tc: TestCase | AutomationReadyTestCase): string {
  const parts = [
    (tc.title ?? '').trim().toLowerCase(),
    (tc.preCondition ?? '').trim().toLowerCase(),
    (tc.steps ?? []).map((s) => String(s).trim().toLowerCase()).join('|'),
    (tc.expectedResult ?? '').trim().toLowerCase(),
  ]
  return parts.join('||').replace(/\s+/g, ' ')
}

export function dedupeTestCases<T extends TestCase>(cases: T[]): T[] {
  const seen = new Map<string, T>()
  for (const tc of cases) {
    const key = normalizeForDedup(tc)
    if (!seen.has(key)) seen.set(key, tc)
  }
  return Array.from(seen.values())
}
