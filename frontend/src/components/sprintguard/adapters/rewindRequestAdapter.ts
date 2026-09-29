import type { GeneratedTestScript } from '../models/testScript.types'
import type { RewindExecutionRequest } from '../models/rewindExecution.types'

// Maps a validated SprintGuard script into the exact request payload accepted
// by the Rewind integration boundary. This is the ONLY module that knows both
// SprintGuard and Rewind shapes — the rest of SprintGuard stays isolated.
export function buildRewindRequest(
  script: GeneratedTestScript,
  opts: { correlationId: string; suiteName: string },
): RewindExecutionRequest {
  return {
    correlationId: opts.correlationId,
    scriptId: script.id,
    testCaseId: script.testCaseId,
    requirementId: script.requirementId,
    suiteName: opts.suiteName,
    script,
    submittedAt: new Date().toISOString(),
  }
}
