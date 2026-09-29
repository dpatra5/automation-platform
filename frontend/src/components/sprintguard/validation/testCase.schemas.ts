import type { TestCase } from '../models/sprintGuard.types'
import type {
  AutomationReadyTestCase,
  TestCaseValidationResult,
  ValidationIssue,
} from '../models/testCase.types'
import { VAGUE_STEP_PATTERNS } from '../constants/sprintGuard.constants'

// Applies the SprintGuard test-case quality gate. A case is only automationReady
// when it has traceability, concrete steps, and an observable expected result.
export function validateTestCase(
  testCase: TestCase | AutomationReadyTestCase,
  opts: { requireTraceability?: boolean } = {},
): TestCaseValidationResult {
  const errors: ValidationIssue[] = []
  const warnings: ValidationIssue[] = []
  const tc = testCase as AutomationReadyTestCase

  if (!tc.testCaseId) {
    errors.push({ field: 'testCaseId', message: 'Missing stable identifier', code: 'ID_MISSING' })
  }
  if (!tc.title || tc.title.trim().length < 5) {
    errors.push({ field: 'title', message: 'Title is missing or too short', code: 'TITLE_INVALID' })
  }
  if (opts.requireTraceability && !tc.requirementId) {
    warnings.push({
      field: 'requirementId',
      message: 'No requirement traceability set',
      code: 'TRACEABILITY_MISSING',
    })
  }
  if (!tc.steps || tc.steps.length === 0) {
    errors.push({ field: 'steps', message: 'At least one step required', code: 'STEPS_EMPTY' })
  } else {
    tc.steps.forEach((step, i) => {
      const s = typeof step === 'string' ? step : String(step)
      if (!s || s.trim().length < 4) {
        errors.push({
          field: `steps[${i}]`,
          message: 'Step is empty or too short',
          code: 'STEP_EMPTY',
        })
      }
      if (VAGUE_STEP_PATTERNS.some((r) => r.test(s.trim()))) {
        errors.push({
          field: `steps[${i}]`,
          message: `Step is vague or non-actionable: "${s}"`,
          code: 'STEP_VAGUE',
        })
      }
      if (/\{\{.*\}\}/.test(s)) {
        errors.push({
          field: `steps[${i}]`,
          message: 'Unresolved placeholder in step',
          code: 'STEP_PLACEHOLDER',
        })
      }
    })
  }
  if (!tc.expectedResult || tc.expectedResult.trim().length < 4) {
    errors.push({
      field: 'expectedResult',
      message: 'Expected result is missing or not observable',
      code: 'EXPECTED_MISSING',
    })
  }

  const valid = errors.length === 0
  const automationReady = valid && !!tc.expectedResult && (tc.steps?.length ?? 0) > 0
  return {
    testCaseId: tc.testCaseId ?? 'unknown',
    valid,
    errors,
    warnings,
    automationReady,
  }
}
