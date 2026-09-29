import type { TestCase } from '../models/sprintGuard.types'
import type { AutomationReadyTestCase } from '../models/testCase.types'
import type {
  GeneratedTestScript,
  RewindStep,
} from '../models/testScript.types'
import { SCRIPT_FORMAT_VERSION } from '../constants/sprintGuard.constants'

const NAV_RE = /^(?:navigate|go to|open|visit) ([^\n]{1,500})$/i
const CLICK_RE = /^(?:click|tap|press)(?: on)? ([^\n]{1,500})$/i
const TYPE_RE = /^(?:enter|type|input|fill) ["']?([^"'\n]{1,200})["']? (?:in|into) ([^\n]{1,200})$/i
const ASSERT_RE = /^(?:verify|assert|expect|check) ([^\n]{1,200}) (?:is|shows|displays|contains) ["']?([^"'\n]{1,200})["']?$/i

// Converts free-text test-case steps into a structured Rewind step sequence.
// Uses conservative heuristics; unknown steps become `wait_for` with note.
export function convertStepToRewind(raw: string, seq: number): RewindStep {
  const text = raw.trim()
  let m = NAV_RE.exec(text)
  if (m) return { sequence: seq, action: 'navigate', target: m[1].trim() }
  m = CLICK_RE.exec(text)
  if (m) return { sequence: seq, action: 'click', target: m[1].trim() }
  m = TYPE_RE.exec(text)
  if (m) return { sequence: seq, action: 'type', target: m[2].trim(), value: m[1].trim() }
  m = ASSERT_RE.exec(text)
  if (m) return { sequence: seq, action: 'assert_text', target: m[1].trim(), value: m[2].trim() }
  return { sequence: seq, action: 'wait_for', target: text }
}

export function buildScriptFromTestCase(
  testCase: TestCase | AutomationReadyTestCase,
  ctx: { targetUrl?: string; requirementId?: string } = {},
): GeneratedTestScript {
  const structured = (testCase as AutomationReadyTestCase).automationSteps
  const source: string[] = structured?.length
    ? structured.map((s) => s.action)
    : (testCase.steps ?? []).map(String)

  const steps: RewindStep[] = source.map((s, i) => {
    const step = convertStepToRewind(s, i + 1)
    const expected = structured?.[i]?.expectedResult
    return expected ? { ...step, expectedResult: expected } : step
  })

  if (testCase.expectedResult) {
    steps.push({
      sequence: steps.length + 1,
      action: 'assert_text',
      target: 'page',
      value: testCase.expectedResult,
      expectedResult: testCase.expectedResult,
    })
  }
  return {
    id: `script-${testCase.testCaseId}`,
    testCaseId: testCase.testCaseId,
    requirementId: ctx.requirementId ?? (testCase as AutomationReadyTestCase).requirementId,
    format: 'rewind.steps.v1',
    version: SCRIPT_FORMAT_VERSION,
    targetUrl: ctx.targetUrl,
    steps,
    metadata: {
      title: testCase.title,
      objective: (testCase as AutomationReadyTestCase).objective,
      category: (testCase as AutomationReadyTestCase).category ?? testCase.type,
      priority: testCase.priority,
      severity: (testCase as AutomationReadyTestCase).severity,
      preconditions:
        (testCase as AutomationReadyTestCase).preconditions ?? [testCase.preCondition],
      testData: (testCase as AutomationReadyTestCase).testData ?? {},
      tags: (testCase as AutomationReadyTestCase).tags ?? [],
      acceptanceCriteriaIds:
        (testCase as AutomationReadyTestCase).acceptanceCriteriaIds ?? [],
    },
    validationStatus: 'pending',
  }
}
