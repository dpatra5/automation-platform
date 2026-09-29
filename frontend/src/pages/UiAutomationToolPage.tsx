import { useEffect, useRef, useState } from 'react'
import { uiAutomationClient, type ReplaySession, type UiAutomationSession } from '../api/uiAutomationClient'

type RunState = UiAutomationSession['status'] | 'idle'

export function UiAutomationToolPage() {
  const [url, setUrl] = useState('')
  const [flowName, setFlowName] = useState('')
  const [runState, setRunState] = useState<RunState>('idle')
  const [session, setSession] = useState<UiAutomationSession | null>(null)
  const [error, setError] = useState('')
  const [browser, setBrowser] = useState<'chromium' | 'firefox' | 'webkit'>('chromium')
  const [testData, setTestData] = useState('')
  const [replayStatus, setReplayStatus] = useState('')
  const [replay, setReplay] = useState<ReplaySession | null>(null)
  const poller = useRef<number | null>(null)
  const controller = import.meta.env.VITE_UI_AUTOMATION_CONTROLLER_URL ?? 'http://127.0.0.1:8001'

  useEffect(() => () => {
    if (poller.current) window.clearInterval(poller.current)
  }, [])

  const poll = (id: string) => {
    poller.current = window.setInterval(async () => {
      try {
        const next = await uiAutomationClient.status(id)
        setSession(next)
        setRunState(next.status)
        if (next.status === 'stopped' && poller.current) window.clearInterval(poller.current)
      } catch {
        setError('Lost connection to the Playwright controller.')
        if (poller.current) window.clearInterval(poller.current)
      }
    }, 1000)
  }

  const startFlow = async () => {
    if (!url.trim() || !flowName.trim()) return
    setError('')
    setRunState('starting')
    try {
      const started = await uiAutomationClient.start(url.trim(), flowName.trim())
      setRunState(started.status)
      poll(started.id)
    } catch {
      setRunState('error')
      setError('Could not start Playwright. Start the UI Automation controller on port 8001.')
    }
  }

  const sendControl = async (action: 'pause' | 'resume') => {
    if (!session) return
    await fetch(`${controller}/api/sessions/${session.id}/events`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ type: 'control', action }),
    })
    setRunState(action === 'pause' ? 'paused' : 'recording')
  }

  const stopFlow = async () => {
    if (!session) return
    const stopped = await uiAutomationClient.stop(session.id)
    setSession(stopped)
    setRunState('stopped')
    if (poller.current) window.clearInterval(poller.current)
  }

  const replayFlow = async () => {
    if (!session) return
    setReplayStatus('Starting replay…')
    try {
      const data = Object.fromEntries(testData.split('\n').map((line) => line.split('=').map((part) => part.trim())).filter(([key, value]) => key && value))
      const started = await uiAutomationClient.replay(session.id, browser, data)
      setReplayStatus(`Replay started in ${browser}.`)
      const replayId = started.id
      const replayPoller = window.setInterval(async () => {
        const next = await uiAutomationClient.replayStatus(replayId)
        setReplay(next)
        if (next.status !== 'running') {
          window.clearInterval(replayPoller)
          setReplayStatus(next.status === 'passed' ? 'Replay completed successfully.' : 'Replay completed with failures.')
        }
      }, 1000)
    } catch {
      setReplayStatus('Replay could not start. Check that the controller is running.')
    }
  }

  const closeReplay = async () => {
    if (!replay) return
    await uiAutomationClient.closeReplay(replay.id)
    setReplay((current) => current ? { ...current, browserOpen: false } : current)
  }

  const statusLabel = runState === 'starting' ? 'Starting Playwright…' : runState === 'recording' ? 'Recording' : runState === 'paused' ? 'Paused' : runState === 'stopped' ? 'Recording saved' : runState === 'error' ? 'Controller unavailable' : 'Not started'

  return (
    <div className="page">
      <div className="tool-page-header">
        <div>
          <span className="tool-eyebrow">Independent Playwright tool</span>
          <h1>UI Automation</h1>
          <p className="page-description">Start a visible Playwright browser, authenticate once if needed, record every action and DOM snapshot, follow new tabs automatically, then replay the saved flow across browsers and test data.</p>
        </div>
        <div className="tool-page-mark">🎯</div>
      </div>

      <div className="ui-tool-layout">
        <section className="tool-panel">
          <h2>New flow</h2>
          <p className="panel-copy">The recorder toolbar is injected into every page opened by the Playwright context, including new tabs and windows.</p>
          <label className="field-label" htmlFor="automation-url">Application URL</label>
          <input id="automation-url" className="text-input" type="url" placeholder="https://example.com" value={url} onChange={(event) => setUrl(event.target.value)} disabled={runState === 'recording' || runState === 'paused'} />
          <label className="field-label" htmlFor="flow-name">Flow name</label>
          <input id="flow-name" className="text-input" type="text" placeholder="Checkout validation" value={flowName} onChange={(event) => setFlowName(event.target.value)} disabled={runState === 'recording' || runState === 'paused'} />
          <div className="tool-actions">
            <button type="button" className="run-btn" disabled={!url.trim() || !flowName.trim() || ['starting', 'recording', 'paused'].includes(runState)} onClick={startFlow}>Start recording</button>
            {runState === 'recording' && <button type="button" className="secondary-btn" onClick={() => sendControl('pause')}>Pause</button>}
            {runState === 'paused' && <button type="button" className="secondary-btn" onClick={() => sendControl('resume')}>Resume</button>}
            {['recording', 'paused'].includes(runState) && <button type="button" className="stop-btn" onClick={stopFlow}>Stop recording</button>}
          </div>
          {error && <div className="connection-error">{error}</div>}
        </section>

        <aside className="tool-panel tool-status-card">
          <span className={`flow-status flow-status-${runState}`}>{statusLabel}</span>
          <h2>{flowName || 'Your flow'}</h2>
          <ul className="flow-checklist">
            <li className={runState !== 'idle' && runState !== 'error' ? 'check-done' : ''}>Playwright browser started</li>
            <li className={['recording', 'paused', 'stopped'].includes(runState) ? 'check-done' : ''}>New tabs are followed automatically</li>
            <li className={runState === 'recording' || runState === 'paused' || runState === 'stopped' ? 'check-done' : ''}>{session?.currentUrl ? `${runState === 'starting' ? 'Opening' : 'Opened'} ${session.currentUrl}` : 'Target URL is opening'}</li>
            <li className={runState === 'stopped' ? 'check-done' : ''}>{session?.eventCount || 0} captured events</li>
            <li className={runState === 'stopped' ? 'check-done' : ''}>Saved flow ready to replay</li>
          </ul>
        </aside>
      </div>

      {session?.status === 'stopped' && <section className="script-panel">
        <div className="script-panel-heading"><h2>Replay saved flow</h2><span className="replay-private-note">Generated script is stored privately.</span></div>
        <div className="activity-summary">
          <h3>Observed activity</h3>
          <p>{session.eventCount} actions were captured across the browser flow.</p>
          <ul>{(session.actions || []).map((action, index) => <li key={`${action.action}-${index}`}><strong>{index + 1}. {action.action}</strong> <span>{action.text || action.value || action.pageUrl}</span></li>)}</ul>
        </div>
        <div className="replay-controls">
          <label className="field-label" htmlFor="replay-browser">Browser</label>
          <select id="replay-browser" className="field" value={browser} onChange={(event) => setBrowser(event.target.value as typeof browser)}>
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
          <label className="field-label" htmlFor="replay-data">Test data</label>
          <textarea id="replay-data" className="field replay-data" rows={3} placeholder="email=user@example.com\nitem=Premium" value={testData} onChange={(event) => setTestData(event.target.value)} />
          <button type="button" className="run-btn" onClick={replayFlow}>Run flow again</button>
          {replayStatus && <span className="replay-status">{replayStatus}</span>}
        </div>
        {replay && <div className="replay-results"><div className="script-panel-heading"><h3>Replay results</h3>{replay.browserOpen && <button type="button" className="secondary-btn" onClick={closeReplay}>Close replay browser</button>}</div><p>{replay.results.filter((result) => result.status === 'passed').length} passed, {replay.results.filter((result) => result.status === 'failed').length} failed</p><ul>{replay.results.map((result) => <li key={result.index} className={`replay-result-${result.status}`}><strong>{result.index}. {result.action}</strong> {result.status}{result.message ? ` — ${result.message}` : ''}</li>)}</ul></div>}
      </section>}
    </div>
  )
}
