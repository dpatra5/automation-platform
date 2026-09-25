import { useCallback, useRef, useState } from 'react'
import type { JobStatus } from '../types'

interface UseJobRunnerOptions {
  steps: string[]
  stepDelayMs?: number
  onComplete?: () => void
}

interface JobRunnerState {
  status: JobStatus
  logs: string[]
  run: () => void
  reset: () => void
}

export function useJobRunner({ steps, stepDelayMs = 700, onComplete }: UseJobRunnerOptions): JobRunnerState {
  const [status, setStatus] = useState<JobStatus>('idle')
  const [logs, setLogs] = useState<string[]>([])
  const timersRef = useRef<number[]>([])

  const clearTimers = () => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }

  const run = useCallback(() => {
    clearTimers()
    setLogs([])
    setStatus('queued')

    const queueTimer = window.setTimeout(() => {
      setStatus('running')
      steps.forEach((step, index) => {
        const stepTimer = window.setTimeout(() => {
          setLogs((prev) => [...prev, step])
          if (index === steps.length - 1) {
            const doneTimer = window.setTimeout(() => {
              setStatus('completed')
              onComplete?.()
            }, stepDelayMs)
            timersRef.current.push(doneTimer)
          }
        }, index * stepDelayMs)
        timersRef.current.push(stepTimer)
      })
    }, 400)
    timersRef.current.push(queueTimer)
  }, [steps, stepDelayMs, onComplete])

  const reset = useCallback(() => {
    clearTimers()
    setStatus('idle')
    setLogs([])
  }, [])

  return { status, logs, run, reset }
}
