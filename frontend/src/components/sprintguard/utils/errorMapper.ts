export type SprintGuardStage =
  | 'requirement_analysis'
  | 'acceptance_criteria'
  | 'test_case_generation'
  | 'test_case_validation'
  | 'script_generation'
  | 'script_validation'
  | 'rewind_submission'
  | 'execution'
  | 'result_retrieval'

export interface StagedError {
  stage: SprintGuardStage
  message: string
  cause?: unknown
  retryable: boolean
}

export function toStagedError(
  stage: SprintGuardStage,
  err: unknown,
  retryable = false,
): StagedError {
  const message =
    err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error'
  return { stage, message, cause: err, retryable }
}
