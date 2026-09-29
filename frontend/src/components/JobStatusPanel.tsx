import type { JobStatus } from '../types'

const STATUS_LABEL: Record<JobStatus, string> = {
  idle: 'Not started',
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

interface JobStatusPanelProps {
  status: JobStatus
  logs: string[]
  children?: React.ReactNode
}

export function JobStatusPanel({ status, logs, children }: JobStatusPanelProps) {
  if (status === 'idle') return null

  return (
    <div className="job-status-panel">
      <div className="job-status-header">
        <span className={`status-badge status-${status}`}>{STATUS_LABEL[status]}</span>
      </div>

      {logs.length > 0 && (
        <ul className="job-log-list">
          {logs.map((log) => (
            <li key={log}>
              <span className="log-tick">✓</span> {log}
            </li>
          ))}
        </ul>
      )}

      {status === 'completed' && children}
    </div>
  )
}
