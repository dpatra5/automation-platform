import { useEffect, useRef, useState } from 'react'
import { uiAutomationClient, type UiAutomationSession } from '../api/uiAutomationClient'
import { ReplayRunner } from './ui-automation-tool/ReplayRunner'
import { TestLibrary } from './ui-automation-tool/TestLibrary'

type RunState = UiAutomationSession['status'] | 'idle'

export function UiAutomationToolPage() {
  const [view, setView] = useState<'record' | 'library'>('record')
  const [librarySlug, setLibrarySlug] = useState<string | null>(null)
  const [url, setUrl] = useState('')
  const [flowName, setFlowName] = useState('')
  const [runState, setRunState] = useState<RunState>('idle')
  const [session, setSession] = useState<UiAutomationSession | null>(null)
  const [error, setError] = useState('')
  const poller = useRef<number | null>(null)
  const controller = import.meta.env.VITE_UI_AUTOMATION_CONTROLLER_URL ?? 'http://127.0.0.1:8004'

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
      setError('Could not start Playwright. Start the UI Automation controller on port 8004.')
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

  const openInLibrary = (slug?: string) => {
    setLibrarySlug(slug ?? null)
    setView('library')
  }

  const statusLabel = runState === 'starting' ? 'Starting Playwright…' : runState === 'recording' ? 'Recording' : runState === 'paused' ? 'Paused' : runState === 'stopped' ? 'Recording saved' : runState === 'error' ? 'Controller unavailable' : 'Not started'

  return (
    <div className="page">
      <div className="tool-page-header">
        <div>
          <span className="tool-eyebrow">Independent Playwright tool</span>
          <h1>UI Automation</h1>
          <p className="page-description">Start a visible Playwright browser, record every action with relative XPaths, follow popups, new tabs, dialogs, modals and iframes, then save the flow as a named test you can re-run from the test library.</p>
        </div>
        <div className="tool-page-mark">🎯</div>
      </div>

      <div className="ui-tool-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={view === 'record'} className={`ui-tool-tab${view === 'record' ? ' active' : ''}`} onClick={() => setView('record')}>Record</button>
        <button type="button" role="tab" aria-selected={view === 'library'} className={`ui-tool-tab${view === 'library' ? ' active' : ''}`} onClick={() => openInLibrary()}>Test library</button>
      </div>

      {view === 'library' ? <TestLibrary key={librarySlug ?? 'list'} initialSlug={librarySlug} /> : <>
      <div className="ui-tool-layout">
        <section className="tool-panel">
          <h2>New test</h2>
          <p className="panel-copy">Use the application normally; the recorder keeps what you do (clicks, typing, selections, tabs, back/forward, dialogs), not mouse movement or scrolling. Use the toolbar's <strong>Verify</strong> button, then click an element, to add a check. <strong>Dialogs</strong> chooses whether alert/confirm/prompt dialogs are accepted or dismissed.</p>
          <label className="field-label" htmlFor="automation-url">Application URL</label>
          <input id="automation-url" className="text-input" type="url" placeholder="https://example.com" value={url} onChange={(event) => setUrl(event.target.value)} disabled={runState === 'recording' || runState === 'paused'} />
          <label className="field-label" htmlFor="flow-name">Test name</label>
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
          <h2>{flowName || 'Your test'}</h2>
          <ul className="flow-checklist">
            <li className={runState !== 'idle' && runState !== 'error' ? 'check-done' : ''}>Playwright browser started</li>
            <li className={['recording', 'paused', 'stopped'].includes(runState) ? 'check-done' : ''}>Popups, tabs, dialogs, modals and iframes are followed{session?.openTabs ? ` (${session.openTabs} open tab${session.openTabs > 1 ? 's' : ''})` : ''}</li>
            <li className={runState === 'recording' || runState === 'paused' || runState === 'stopped' ? 'check-done' : ''}>{session?.currentUrl ? `${runState === 'starting' ? 'Opening' : 'Opened'} ${session.currentUrl}` : 'Target URL is opening'}</li>
            <li className={runState === 'stopped' ? 'check-done' : ''}>{session?.eventCount || 0} captured events</li>
            <li className={runState === 'stopped' ? 'check-done' : ''}>{session?.testSlug ? `Saved to tests/${session.testSlug}` : 'Saved to the test library'}</li>
          </ul>
          {runState === 'stopped' && session?.testSlug && <button type="button" className="secondary-btn" onClick={() => openInLibrary(session.testSlug)}>Open saved test</button>}
        </aside>
      </div>

      {session?.status === 'stopped' && <section className="script-panel">
        <div className="script-panel-heading"><h2>Run saved test</h2><span className="replay-private-note">Element names, XPaths and the functional flow are in the test library.</span></div>
        <div className="activity-summary">
          <h3>Functional flow</h3>
          <p>{session.actions?.length ?? 0} steps were learned from {session.eventCount} captured events.</p>
          <ul>{(session.actions || []).map((action, index) => <li key={`${action.action}-${index}`}><strong>{index + 1}. {action.text || action.action}</strong>{action.tab !== undefined && <span className="tab-badge">tab {action.tab}</span>}{action.xpath && <code className="action-xpath">{action.xpath}</code>}</li>)}</ul>
        </div>
        <ReplayRunner start={(browser, data) => uiAutomationClient.replay(session.id, browser, data)} />
      </section>}
      </>}
    </div>
  )
}
