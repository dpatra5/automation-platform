import type { GeneratedTestScript } from './testScript.types'

export interface RewindExecutionRequest {
  correlationId: string
  scriptId: string
  testCaseId: string
  requirementId?: string
  suiteName: string
  script: GeneratedTestScript
  submittedAt: string
}

export interface RewindExecutionReference {
  executionId: string
  testCaseId: string
  scriptId: string
  submittedAt?: string
}

export type RewindExecutionState =
  | 'queued'
  | 'running'
  | 'passed'
  | 'failed'
  | 'cancelled'

export interface SprintGuardExecutionResult {
  executionId: string
  testCaseId: string
  status: RewindExecutionState
  startedAt?: string
  completedAt?: string
  durationMs?: number
  logs: string[]
  screenshots: string[]
  artifacts: string[]
  error?: string
}
