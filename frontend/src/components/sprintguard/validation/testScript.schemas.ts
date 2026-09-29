import type {
  GeneratedTestScript,
  ScriptValidationResult,
  ScriptValidationIssue,
} from '../models/testScript.types'

const SUPPORTED_ACTIONS = new Set([
  'navigate',
  'click',
  'type',
  'select',
  'wait_for',
  'assert_visible',
  'assert_text',
  'assert_url',
  'screenshot',
])

const FORBIDDEN_PATTERNS: Array<{ re: RegExp; message: string }> = [
  { re: /password\s*=\s*['"][^'"]+['"]/i, message: 'Hardcoded credential detected' },
  { re: /token\s*=\s*['"][A-Za-z0-9]{10,}['"]/i, message: 'Hardcoded token detected' },
  { re: /(rm\s+-rf|del\s+\/s|format\s+c:)/i, message: 'Destructive OS command detected' },
]

// Validates a GeneratedTestScript against the observed Rewind step contract
// and SprintGuard's script security rules before submission.
export function validateScript(script: GeneratedTestScript): ScriptValidationResult {
  const errors: ScriptValidationIssue[] = []
  const warnings: ScriptValidationIssue[] = []

  if (!script.id) {
    errors.push({ field: 'id', message: 'Script id missing', code: 'ID_MISSING' })
  }
  if (!script.testCaseId) {
    errors.push({
      field: 'testCaseId',
      message: 'Traceability to test case lost',
      code: 'TRACE_MISSING',
    })
  }
  if (script.format !== 'rewind.steps.v1') {
    errors.push({
      field: 'format',
      message: `Unsupported script format: ${script.format}`,
      code: 'FORMAT_UNSUPPORTED',
    })
  }
  if (!script.steps || script.steps.length === 0) {
    errors.push({ field: 'steps', message: 'Script has no steps', code: 'STEPS_EMPTY' })
  } else {
    script.steps.forEach((step, i) => {
      if (!SUPPORTED_ACTIONS.has(step.action)) {
        errors.push({
          field: `steps[${i}].action`,
          message: `Unsupported action: ${step.action}`,
          code: 'ACTION_UNSUPPORTED',
        })
      }
      const serialized = JSON.stringify(step)
      if (/\{\{.*\}\}/.test(serialized)) {
        errors.push({
          field: `steps[${i}]`,
          message: 'Unresolved placeholder',
          code: 'PLACEHOLDER',
        })
      }
      for (const { re, message } of FORBIDDEN_PATTERNS) {
        if (re.test(serialized)) {
          errors.push({ field: `steps[${i}]`, message, code: 'SECURITY_VIOLATION' })
        }
      }
    })
  }
  if (script.targetUrl && !/^https?:\/\//i.test(script.targetUrl)) {
    warnings.push({
      field: 'targetUrl',
      message: 'targetUrl should use http(s)',
      code: 'URL_SCHEME',
    })
  }

  return { scriptId: script.id ?? 'unknown', valid: errors.length === 0, errors, warnings }
}
