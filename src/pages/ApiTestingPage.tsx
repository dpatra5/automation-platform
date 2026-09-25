import { useState } from 'react'
import { useJobRunner } from '../hooks/useJobRunner'
import { JobStatusPanel } from '../components/JobStatusPanel'

const STEPS = [
  'Connecting to API testing tool',
  'Loading test collection',
  'Executing requests',
  'Validating responses',
  'Compiling report',
]

export function ApiTestingPage() {
  const [endpoint, setEndpoint] = useState('')
  const { status, logs, run } = useJobRunner({ steps: STEPS })

  const canRun = endpoint.trim().length > 0 && status !== 'queued' && status !== 'running'

  return (
    <div className="page">
      <h1>API Testing</h1>
      <p className="page-description">
        Provide the base API endpoint or collection name. The integrated API testing tool will run
        the automated test suite and report the results here.
      </p>

      <label className="field-label" htmlFor="api-endpoint">
        API endpoint / collection
      </label>
      <input
        id="api-endpoint"
        className="text-input"
        type="text"
        placeholder="https://api.example.com or collection name"
        value={endpoint}
        onChange={(e) => setEndpoint(e.target.value)}
      />

      <button type="button" className="run-btn" disabled={!canRun} onClick={run}>
        Run API Tests
      </button>

      <JobStatusPanel status={status} logs={logs}>
        <div className="result-grid">
          <div className="result-card">
            <h3>Test Summary</h3>
            <ul>
              <li>Total requests: 42</li>
              <li>Passed: 39</li>
              <li>Failed: 3</li>
              <li>Avg response time: 128ms</li>
            </ul>
          </div>
        </div>
      </JobStatusPanel>
    </div>
  )
}
