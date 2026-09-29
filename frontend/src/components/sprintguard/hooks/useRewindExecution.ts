import { useCallback, useEffect, useRef, useState } from 'react'
import type { TestCase } from '../models/sprintGuard.types'
import type { AutomationReadyTestCase, TestCaseValidationResult } from '../models/testCase.types'
import type { GeneratedTestScript, ScriptValidationResult } from '../models/testScript.types'
import type {
  RewindExecutionReference,
  SprintGuardExecutionResult,
} from '../models/rewindExecution.types'
import { buildScriptFromTestCase } from '../adapters/testCaseToScriptAdapter'
import { buildRewindRequest } from '../adapters/rewindRequestAdapter'
import { rewindExecutionGateway } from '../services/rewindExecutionGateway'
import { validateTestCase } from '../validation/testCase.schemas'
import { validateScript } from '../validation/testScript.schemas'

export interface UseRewindExecutionState {
  script: GeneratedTestScript | null
  testCaseValidation: TestCaseValidationResult | null
  scriptValidation: ScriptValidationResult | null
  executionRef: RewindExecutionReference | null
  result: SprintGuardExecutionResult | null
  error: string | null
  isBusy: boolean
}

// Orchestrates: quality gate → script generation → script validation → Rewind
// submission → live result stream. Enforces the state-machine transitions
// required by the SprintGuard spec (no script without a valid case, no
// execution without a valid script).
export function useRewindExecution() {
  const [state, setState] = useState<UseRewindExecutionState>({
    script: null,
    testCaseValidation: null,
    scriptValidation: null,
    executionRef: null,
    result: null,
    error: null,
    isBusy: false,
  })
  const unsubRef = useRef<null | (() => void)>(null)

  useEffect(() => () => unsubRef.current?.(), [])

  const runPipeline = useCallback(
    async (
      testCase: TestCase | AutomationReadyTestCase,
      opts: {
        suiteName: string
        targetUrl?: string
        requirementId?: string
        correlationId?: string
      },
    ) => {
      setState((p) => ({ ...p, isBusy: true, error: null }))

      const tcResult = validateTestCase(testCase)
      if (!tcResult.automationReady) {
        setState((p) => ({
          ...p,
          testCaseValidation: tcResult,
          error: 'Test case failed the quality gate',
          isBusy: false,
        }))
        return
      }

      const script = buildScriptFromTestCase(testCase, {
        targetUrl: opts.targetUrl,
        requirementId: opts.requirementId,
      })
      const scriptResult = validateScript(script)
      if (!scriptResult.valid) {
        setState((p) => ({
          ...p,
          testCaseValidation: tcResult,
          script,
          scriptValidation: scriptResult,
          error: 'Generated script failed validation',
          isBusy: false,
        }))
        return
      }
      script.validationStatus = 'valid'

      const request = buildRewindRequest(script, {
        correlationId: opts.correlationId ?? `corr-${Date.now()}`,
        suiteName: opts.suiteName,
      })
      const ref = rewindExecutionGateway.submit(request)

      unsubRef.current?.()
      unsubRef.current = rewindExecutionGateway.onStatus(
        (result) =>
          setState((p) => ({
            ...p,
            result,
            isBusy: result.status === 'queued' || result.status === 'running',
          })),
        { executionId: ref.executionId, testCaseId: ref.testCaseId },
      )

      setState((p) => ({
        ...p,
        testCaseValidation: tcResult,
        script,
        scriptValidation: scriptResult,
        executionRef: ref,
        isBusy: true,
      }))
    },
    [],
  )

  const reset = useCallback(() => {
    unsubRef.current?.()
    unsubRef.current = null
    setState({
      script: null,
      testCaseValidation: null,
      scriptValidation: null,
      executionRef: null,
      result: null,
      error: null,
      isBusy: false,
    })
  }, [])

  return { ...state, runPipeline, reset }
}
