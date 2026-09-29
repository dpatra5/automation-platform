import type {
  RewindExecutionState,
  SprintGuardExecutionResult,
} from '../models/rewindExecution.types'

// Normalizes the various shapes Rewind may emit ("completed", "success",
// "ok"...) into the SprintGuard execution status enum.
const STATE_MAP: Record<string, RewindExecutionState> = {
  queued: 'queued',
  pending: 'queued',
  running: 'running',
  in_progress: 'running',
  passed: 'passed',
  completed: 'passed',
  success: 'passed',
  ok: 'passed',
  failed: 'failed',
  error: 'failed',
  cancelled: 'cancelled',
  canceled: 'cancelled',
}

export function normalizeRewindStatus(raw: string): RewindExecutionState {
  return STATE_MAP[raw?.toLowerCase?.() ?? ''] ?? 'running'
}

export interface RewindResultLike {
  executionId?: string
  testCaseId?: string
  status?: string
  startedAt?: string
  completedAt?: string
  durationMs?: number
  logs?: unknown
  screenshots?: unknown
  artifacts?: unknown
  error?: unknown
}

export function toSprintGuardResult(
  raw: RewindResultLike,
  fallback: { executionId: string; testCaseId: string },
): SprintGuardExecutionResult {
  const arr = (v: unknown): string[] => {
    if (Array.isArray(v)) return v.map((x) => (typeof x === 'string' ? x : JSON.stringify(x)))
    if (v == null) return []
    return [typeof v === 'string' ? v : JSON.stringify(v)]
  }
  let errorText: string | undefined
  if (raw.error != null) {
    errorText = typeof raw.error === 'string' ? raw.error : JSON.stringify(raw.error)
  }
  return {
    executionId: raw.executionId ?? fallback.executionId,
    testCaseId: raw.testCaseId ?? fallback.testCaseId,
    status: normalizeRewindStatus(raw.status ?? ''),
    startedAt: raw.startedAt,
    completedAt: raw.completedAt,
    durationMs: raw.durationMs,
    logs: arr(raw.logs),
    screenshots: arr(raw.screenshots),
    artifacts: arr(raw.artifacts),
    error: errorText,
  }
}
