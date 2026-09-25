import { useState } from 'react'
import { useJobRunner } from '../hooks/useJobRunner'
import { JobStatusPanel } from '../components/JobStatusPanel'

const STEPS = [
  'Connecting to load testing tool',
  'Provisioning virtual users',
  'Ramping up load',
  'Collecting performance metrics',
  'Compiling report',
]

export function LoadTestingPage() {
  const [targetUrl, setTargetUrl] = useState('')
  const [virtualUsers, setVirtualUsers] = useState(50)
  const { status, logs, run } = useJobRunner({ steps: STEPS })

  const canRun = targetUrl.trim().length > 0 && status !== 'queued' && status !== 'running'

  return (
    <div className="page">
      <h1>Load Testing</h1>
      <p className="page-description">
        Configure the target and concurrent load. The integrated load testing tool will simulate
        traffic and report performance metrics here.
      </p>

      <label className="field-label" htmlFor="target-url">
        Target URL
      </label>
      <input
        id="target-url"
        className="text-input"
        type="text"
        placeholder="https://example.com"
        value={targetUrl}
        onChange={(e) => setTargetUrl(e.target.value)}
      />

      <label className="field-label" htmlFor="virtual-users">
        Virtual users
      </label>
      <input
        id="virtual-users"
        className="text-input"
        type="number"
        min={1}
        value={virtualUsers}
        onChange={(e) => setVirtualUsers(Number(e.target.value))}
      />

      <button type="button" className="run-btn" disabled={!canRun} onClick={run}>
        Run Load Test
      </button>

      <JobStatusPanel status={status} logs={logs}>
        <div className="result-grid">
          <div className="result-card">
            <h3>Performance Metrics</h3>
            <ul>
              <li>Virtual users: {virtualUsers}</li>
              <li>Throughput: 320 req/s</li>
              <li>Avg response time: 245ms</li>
              <li>Error rate: 0.4%</li>
            </ul>
          </div>
        </div>
      </JobStatusPanel>
    </div>
  )
}
