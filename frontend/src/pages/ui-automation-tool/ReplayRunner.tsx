import { useEffect, useRef, useState } from 'react'
import { uiAutomationClient, type BrowserName, type ReplaySession } from '../../api/uiAutomationClient'

interface ReplayRunnerProps {
  start: (browser: BrowserName, data: Record<string, string>) => Promise<{ id: string }>
  onFinished?: (replay: ReplaySession) => void
}

const parseTestData = (text: string) =>
  Object.fromEntries(text.split('\n').map((line) => {
    const separator = line.indexOf('=')
    return separator > 0 ? [line.slice(0, separator).trim(), line.slice(separator + 1).trim()] : ['', '']
  }).filter(([key, value]) => key && value))

export function ReplayRunner({ start, onFinished }: ReplayRunnerProps) {
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
            setStatus(next.status === 'passed' ? 'Replay completed successfully.' : 'Replay completed with failures.')
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
        {status && <span className="replay-status">{status}</span>}
      </div>
      {replay && (
        <div className="replay-results">
          <div className="script-panel-heading">
            <h3>Replay results</h3>
            {replay.browserOpen && <button type="button" className="secondary-btn" onClick={closeBrowser}>Close replay browser</button>}
          </div>
          <p>
            {replay.results.filter((result) => result.status === 'passed').length} passed, {replay.results.filter((result) => result.status === 'failed').length} failed
            {replay.results.some((result) => result.status === 'skipped') ? `, ${replay.results.filter((result) => result.status === 'skipped').length} skipped` : ''}
            {replay.healedSteps ? `, ${replay.healedSteps} stored XPaths refreshed` : ''}
          </p>
          <ul>
            {replay.results.map((result) => (
              <li key={result.index} className={`replay-result-${result.status}`}>
                <strong>{result.index}. {result.description || result.action}</strong>
                {result.tab !== undefined && <span className="tab-badge">tab {result.tab}</span>} {result.status}
                {result.message ? ` — ${result.message}` : ''}
                {result.locator && <code className="action-xpath">{result.locator}</code>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
