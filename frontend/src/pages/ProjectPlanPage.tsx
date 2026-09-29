import { useState } from 'react'
import { useJobRunner } from '../hooks/useJobRunner'
import { JobStatusPanel } from '../components/JobStatusPanel'

const STEPS = [
  'Analyzing problem statement',
  'Generating summary',
  'Deriving acceptance criteria',
  'Mapping SDLC phases',
  'Mapping STLC phases',
  'Creating Jira tickets',
]

export function ProjectPlanPage() {
  const [problemStatement, setProblemStatement] = useState('')
  const { status, logs, run } = useJobRunner({ steps: STEPS })

  const canRun = problemStatement.trim().length > 0 && status !== 'queued' && status !== 'running'

  return (
    <div className="page">
      <h1>Project Plan Creation</h1>
      <p className="page-description">
        Paste a problem statement below. The integrated planning tool will analyze it and produce a
        summary, acceptance criteria, SDLC and STLC breakdown, and draft Jira tickets.
      </p>

      <label className="field-label" htmlFor="problem-statement">
        Problem statement
      </label>
      <textarea
        id="problem-statement"
        className="text-input"
        rows={6}
        placeholder="Describe the problem you want to solve..."
        value={problemStatement}
        onChange={(e) => setProblemStatement(e.target.value)}
      />

      <button type="button" className="run-btn" disabled={!canRun} onClick={run}>
        Analyze &amp; Generate Plan
      </button>

      <JobStatusPanel status={status} logs={logs}>
        <div className="result-grid">
          <div className="result-card">
            <h3>Summary</h3>
            <p>{problemStatement.slice(0, 160) || 'N/A'}...</p>
          </div>
          <div className="result-card">
            <h3>Acceptance Criteria</h3>
            <ul>
              <li>Given the described problem, the solution addresses the core need.</li>
              <li>All edge cases identified in the statement are covered.</li>
              <li>Solution is verifiable via test cases.</li>
            </ul>
          </div>
          <div className="result-card">
            <h3>SDLC</h3>
            <ul>
              <li>Requirements → Design → Development → Testing → Deployment → Maintenance</li>
            </ul>
          </div>
          <div className="result-card">
            <h3>STLC</h3>
            <ul>
              <li>Test Planning → Test Design → Test Execution → Defect Tracking → Closure</li>
            </ul>
          </div>
          <div className="result-card">
            <h3>Jira Tickets</h3>
            <ul>
              <li>AP-101: Implement core requirement</li>
              <li>AP-102: Write automated test cases</li>
              <li>AP-103: Review and QA sign-off</li>
            </ul>
          </div>
        </div>
      </JobStatusPanel>
    </div>
  )
}
