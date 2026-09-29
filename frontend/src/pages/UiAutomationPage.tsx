import { useState } from 'react'
import { useJobRunner } from '../hooks/useJobRunner'
import { JobStatusPanel } from '../components/JobStatusPanel'

const STEPS = [
  'Connecting to UI automation tool',
  'Launching browser session',
  'Executing test scenarios',
  'Capturing screenshots',
  'Compiling report',
]

export function UiAutomationPage() {
  const [suiteName, setSuiteName] = useState('')
  const { status, logs, run } = useJobRunner({ steps: STEPS })

  const canRun = suiteName.trim().length > 0 && status !== 'queued' && status !== 'running'

  return (
    <div className="page">
      <h1>UI Automation</h1>
      <p className="page-description">
        Provide the test suite name. The integrated UI automation tool will run the scenarios across
        browsers and report the results here.
      </p>

      <label className="field-label" htmlFor="suite-name">
        Test suite
      </label>
      <input
        id="suite-name"
        className="text-input"
        type="text"
        placeholder="Regression suite name"
        value={suiteName}
        onChange={(e) => setSuiteName(e.target.value)}
      />

      <button type="button" className="run-btn" disabled={!canRun} onClick={run}>
        Run UI Automation
      </button>

      <JobStatusPanel status={status} logs={logs}>
        <div className="result-grid">
          <div className="result-card">
            <h3>Scenario Results</h3>
            <ul>
              <li>Scenarios run: 18</li>
              <li>Passed: 16</li>
              <li>Failed: 2</li>
              <li>Screenshots captured: 18</li>
            </ul>
          </div>
        </div>
      </JobStatusPanel>
    </div>
  )
}
