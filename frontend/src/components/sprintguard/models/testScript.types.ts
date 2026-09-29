export type ScriptFormat = 'rewind.steps.v1'

export interface RewindStep {
  sequence: number
  action: string
  target?: string
  value?: string
  expectedResult?: string
}

export interface GeneratedTestScript {
  id: string
  testCaseId: string
  requirementId?: string
  format: ScriptFormat
  version: string
  targetUrl?: string
  steps: RewindStep[]
  metadata: Record<string, unknown>
  validationStatus: 'pending' | 'valid' | 'invalid'
}

export interface ScriptValidationIssue {
  field: string
  message: string
  code: string
}

export interface ScriptValidationResult {
  scriptId: string
  valid: boolean
  errors: ScriptValidationIssue[]
  warnings: ScriptValidationIssue[]
}
