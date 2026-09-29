import { REWIND_EVENT } from '../constants/sprintGuard.constants'
import type {
  RewindExecutionReference,
  RewindExecutionRequest,
  SprintGuardExecutionResult,
} from '../models/rewindExecution.types'
import { toSprintGuardResult } from '../adapters/rewindResultAdapter'

// SprintGuard-side gateway to Rewind.
//
// This module NEVER imports Rewind internals. Instead it publishes a typed
// CustomEvent on `window` and lets the (unmodified) Rewind surface subscribe
// through its own listener. This preserves the read-only Rewind boundary.
//
// If/when Rewind exposes a real HTTP endpoint, swap `submit()` internals to
// fetch(REWIND_API_URL, ...) — the caller contract does not change.
export const rewindExecutionGateway = {
  submit(request: RewindExecutionRequest): RewindExecutionReference {
    const executionId = `exec-${request.scriptId}-${Date.now()}`
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent(REWIND_EVENT.submit, {
          detail: { ...request, executionId },
        }),
      )
    }
    return {
      executionId,
      testCaseId: request.testCaseId,
      scriptId: request.scriptId,
      submittedAt: request.submittedAt,
    }
  },

  onStatus(
    handler: (result: SprintGuardExecutionResult) => void,
    fallback: { executionId: string; testCaseId: string },
  ): () => void {
    if (typeof window === 'undefined') return () => undefined
    const listener = (e: Event) => {
      const detail = (e as CustomEvent).detail ?? {}
      handler(toSprintGuardResult(detail, fallback))
    }
    window.addEventListener(REWIND_EVENT.status, listener)
    window.addEventListener(REWIND_EVENT.result, listener)
    return () => {
      window.removeEventListener(REWIND_EVENT.status, listener)
      window.removeEventListener(REWIND_EVENT.result, listener)
    }
  },
}
