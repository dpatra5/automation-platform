import { useEffect } from 'react'

const REWIND_APP_URL = import.meta.env.VITE_REWIND_APP_URL ?? 'http://localhost:5174'

export function UiAutomationPage() {
  // The Rewind extension only answers the page's top frame, so embedding the
  // tool in an iframe here means it can never detect the extension. Opening
  // it in its own tab makes it the top frame, where recording works.
  useEffect(() => {
    window.open(REWIND_APP_URL, '_blank', 'noopener,noreferrer')
  }, [])

  return (
    <div className="page">
      <h1>UI Automation</h1>
      <p className="page-description">
        The Rewind UI automation tool opened in a new tab. It needs to be its own top-level
        tab (not embedded) for the recording extension to work correctly.
      </p>
      <a className="run-btn" href={REWIND_APP_URL} target="_blank" rel="noreferrer">
        Open UI Automation tool
      </a>
    </div>
  )
}
