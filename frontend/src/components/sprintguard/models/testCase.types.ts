// Additive augmentation of the existing SprintGuard TestCase model with
// automation-ready fields required by the SprintGuard→Rewind pipeline.
// Backwards compatible: every automation field is optional.

import type { TestCase as BaseTestCase } from './sprintGuard.types'

export type TestCaseCategory =
  | 'Positive'
  | 'Negative'
  | 'Boundary'
  | 'Validation'
  | 'Authorization'
  | 'ErrorHandling'
  | 'UI'

export type TestCasePriority = 'High' | 'Medium' | 'Low'
export type TestCaseSeverity = 'Critical' | 'Major' | 'Minor' | 'Trivial'

export type ValidationStatus = 'pending' | 'valid' | 'invalid'
export type ScriptStatus =
  | 'not_generated'
  | 'generating'
  | 'generated'
  | 'invalid'
  | 'ready'
export type ExecutionStatus =
  | 'not_started'
  | 'queued'
  | 'running'
  | 'passed'
  | 'failed'
  | 'cancelled'

export interface AutomationTestStep {
  sequence: number
  action: string
  input?: unknown
  expectedResult?: string
}

export interface AutomationReadyTestCase extends BaseTestCase {
  requirementId?: string
  acceptanceCriteriaIds?: string[]
  objective?: string
  category?: TestCaseCategory
  severity?: TestCaseSeverity
  preconditions?: string[]
  testData?: Record<string, unknown>
  automationSteps?: AutomationTestStep[]
  postconditions?: string[]
  cleanup?: string[]
  tags?: string[]
  automationEligible?: boolean
  automationNotes?: string[]
  dependencies?: string[]
  validationStatus?: ValidationStatus
  scriptStatus?: ScriptStatus
  executionStatus?: ExecutionStatus
  executionId?: string
}

export interface ValidationIssue {
  field: string
  message: string
  code: string
}

export interface TestCaseValidationResult {
  testCaseId: string
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  automationReady: boolean
}
