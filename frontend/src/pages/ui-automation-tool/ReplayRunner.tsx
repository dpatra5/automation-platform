import { useEffect, useRef, useState } from 'react'
import { reportUrl, uiAutomationClient, type BrowserName, type ReplaySession } from '../../api/uiAutomationClient'

interface ReplayRunnerProps {
  start: (browser: BrowserName, data: Record<string, string>) => Promise<{ id: string }>
  onFinished?: (replay: ReplaySession) => void
  signInUrl?: string
}

const parseTestData = (text: string) =>
  Object.fromEntries(text.split('\n').map((line) => {
    const separator = line.indexOf('=')
    return separator > 0 ? [line.slice(0, separator).trim(), line.slice(separator + 1).trim()] : ['', '']
  }).filter(([key, value]) => key && value))

export function ReplayRunner({ start, onFinished, signInUrl }: ReplayRunnerProps) {
  const [browser, setBrowser] = useState<BrowserName>('chromium')
  const [testData, setTestData] = useState('')
  const [status, setStatus] = useState('')
  const [replay, setReplay] = useState<ReplaySession | null>(null)
  const poller = useRef<number | null>(null)

  useEffect(() => () => {
    if (poller.current) window.clearInterval(poller.current)
  }, [])

  const run = async () => {
    if (poller.current) window.clearInterval(poller.current)
    setReplay(null)
    setStatus('Starting replay…')
    try {
      const started = await start(browser, parseTestData(testData))
      setStatus(`Replay running in ${browser}…`)
      poller.current = window.setInterval(async () => {
        try {
          const next = await uiAutomationClient.replayStatus(started.id)
          setReplay(next)
          if (next.status !== 'running') {
            if (poller.current) window.clearInterval(poller.current)
            setStatus(`${next.status === 'passed' ? 'Replay completed successfully.' : 'Replay completed with failures.'}${next.sharedBrowser ? ' The test tabs were closed; the test browser stays signed in.' : ''}`)
            onFinished?.(next)
          }
        } catch {
          if (poller.current) window.clearInterval(poller.current)
          setStatus('Lost connection to the Playwright controller.')
        }
      }, 1000)
    } catch {
      setStatus('Replay could not start. Check that the controller is running.')
    }
  }

  const closeBrowser = async () => {
    if (!replay) return
    await uiAutomationClient.closeReplay(replay.id)
    setReplay((current) => current ? { ...current, browserOpen: false } : current)
  }

  const openForSignIn = async () => {
    if (!signInUrl) return
    try {
      await uiAutomationClient.openSharedBrowser(signInUrl, browser)
      setStatus('The test browser is open. Sign in there, then click Run test; runs reuse that sign-in.')
    } catch {
      setStatus('Could not open the test browser. Check that the controller is running.')
    }
  }

  const running = replay?.status === 'running' || status.startsWith('Starting') || status.startsWith('Replay running')

  return (
    <>
      <div className="replay-controls">
        <label className="field-label" htmlFor="replay-browser">Browser</label>
        <select id="replay-browser" className="field" value={browser} onChange={(event) => setBrowser(event.target.value as BrowserName)}>
          <option value="chromium">Chromium</option>
          <option value="firefox">Firefox</option>
          <option value="webkit">WebKit</option>
        </select>
        <textarea aria-label="Test data" className="field replay-data" rows={3} placeholder={'Test data (optional)\nemail=user@example.com'} value={testData} onChange={(event) => setTestData(event.target.value)} />
        <button type="button" className="run-btn" onClick={run} disabled={running}>Run test</button>
        {signInUrl && <button type="button" className="secondary-btn" onClick={openForSignIn} disabled={running} title="Opens the app in the test browser so you can sign in once; later runs reuse it">Sign in first</button>}
        {status && <span className="replay-status">{status}</span>}
      </div>
      {replay && (
        <div className="replay-results">
          <div className="script-panel-heading">
            <h3>{replay.status === 'running' ? 'Execution in progress' : 'Execution report'}</h3>
            <div className="tool-actions">
              {replay.summary && <a className="secondary-btn" href={reportUrl(replay.id, 'html')} target="_blank" rel="noreferrer noopener">Open report</a>}
              {replay.summary && <a className="secondary-btn" href={reportUrl(replay.id, 'json')}>Download JSON</a>}
              {replay.browserOpen && <button type="button" className="secondary-btn" onClick={closeBrowser}>Close replay browser</button>}
            </div>
          </div>
          {replay.summary ? (
            <div className="run-summary">
              <div className={`run-summary-card run-summary-${replay.summary.status}`}><span>Result</span><b>{replay.summary.status.toUpperCase()}</b></div>
              <div className="run-summary-card"><span>Steps passed</span><b>{replay.summary.steps.passed} / {replay.summary.steps.total}</b></div>
              <div className="run-summary-card"><span>Steps failed</span><b>{replay.summary.steps.failed}</b></div>
              <div className="run-summary-card"><span>Assertions passed</span><b>{replay.summary.assertions.passed} / {replay.summary.assertions.total}</b></div>
              <div className="run-summary-card"><span>Duration</span><b>{(replay.summary.durationMs / 1000).toFixed(1)}s</b></div>
              {replay.healedSteps ? <div className="run-summary-card"><span>XPaths refreshed</span><b>{replay.healedSteps}</b></div> : null}
            </div>
          ) : (
            <p>{replay.results.length} steps executed so far…</p>
          )}
          {replay.summary && replay.summary.failures.length > 0 && (
            <div className="run-failures">
              <h4>Failures</h4>
              <ul>
                {replay.summary.failures.map((failure) => (
                  <li key={failure.step}><strong>Step {failure.step}:</strong> {failure.description}<ul>{failure.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></li>
                ))}
              </ul>
            </div>
          )}
          <ul>
            {replay.results.map((result) => (
              <li key={result.index} className={`replay-result-${result.status}`}>
                <strong>{result.index}. {result.description || result.action}</strong>
                {result.tab !== undefined && <span className="tab-badge">tab {result.tab}</span>} {result.status}
                {result.assertions?.length ? (
                  <ul className="soft-assertions">
                    {result.assertions.map((item, position) => (
                      <li key={position} className={item.passed ? 'assertion-pass' : 'assertion-fail'}>{item.passed ? '✓' : '✗'} {item.label}{item.detail ? ` — ${item.detail}` : ''}</li>
                    ))}
                    {result.notes?.map((note) => <li key={note} className="assertion-note">{note}</li>)}
                  </ul>
                ) : result.message ? ` — ${result.message}` : ''}
                {result.locator && <code className="action-xpath">{result.locator}</code>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
