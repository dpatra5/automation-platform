import { useCallback, useEffect, useState } from 'react'
import { uiAutomationClient, type TestDetail, type TestPage, type TestSummary } from '../../api/uiAutomationClient'
import { ReplayRunner } from './ReplayRunner'

const formatDate = (value?: string) => value ? new Date(value).toLocaleString() : '—'

function RunBadge({ run }: { run: TestSummary['lastRun'] }) {
  if (!run) return <span className="run-badge run-badge-none">Never run</span>
  return <span className={`run-badge run-badge-${run.status}`}>{run.status} · {run.passed}/{run.passed + run.failed}</span>
}

function LocatorTable({ elements }: { elements: Record<string, string> }) {
  return (
    <table className="locator-table">
      <thead><tr><th>Element name</th><th>Relative XPath</th></tr></thead>
      <tbody>
        {Object.entries(elements).map(([name, xpath]) => (
          <tr key={name}><td><code>{name}</code></td><td><code className="locator-xpath">{xpath}</code></td></tr>
        ))}
      </tbody>
    </table>
  )
}

function PageLocators({ name, page }: { name: string; page: TestPage }) {
  return (
    <div className="locator-page">
      <div className="locator-page-heading">
        <h4>{name}</h4>
        <span>{page.path}</span>
        <code>{page.file}</code>
      </div>
      {Object.keys(page.elements).length > 0 && <LocatorTable elements={page.elements} />}
      {Object.entries(page.components).map(([componentName, component]) => (
        <div key={componentName} className="component-block">
          <div className="locator-page-heading">
            <h5>{componentName}</h5>
            <span className={`component-kind component-kind-${component.kind}`}>{component.kind}</span>
            {component.root && <code>{component.root}</code>}
            {component.frame?.length ? <code>iframe: {component.frame.join(' → ')}</code> : null}
          </div>
          <LocatorTable elements={component.elements} />
        </div>
      ))}
    </div>
  )
}

function TestDetailView({ slug, onBack, onChanged }: { slug: string; onBack: () => void; onChanged: () => void }) {
  const [test, setTest] = useState<TestDetail | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setTest(await uiAutomationClient.getTest(slug))
      setError('')
    } catch {
      setError('Could not load this test. Check that the UI Automation controller is running on port 8004.')
    }
  }, [slug])

  useEffect(() => { load() }, [load])

  if (error) return <div className="connection-error">{error}</div>
  if (!test) return <p className="panel-copy">Loading test…</p>

  return (
    <div className="test-detail">
      <button type="button" className="secondary-btn" onClick={onBack}>← Back to test library</button>
      <div className="tool-panel test-detail-header">
        <div>
          <span className="tool-eyebrow">Saved test · tests/{test.slug}/test.json</span>
          <h2>{test.name}</h2>
          <p className="panel-copy"><a href={test.url} target="_blank" rel="noreferrer noopener">{test.url}</a></p>
          <p className="test-meta">Created {formatDate(test.createdAt)} · Updated {formatDate(test.updatedAt)}</p>
        </div>
        <RunBadge run={test.lastRun} />
      </div>

      <section className="script-panel">
        <div className="script-panel-heading"><h2>Run test</h2><span className="replay-private-note">Runs the functional flow step by step and validates each result; stops at the first failure.</span></div>
        <ReplayRunner start={(browser, data) => uiAutomationClient.runTest(test.slug, browser, data)} onFinished={() => { load(); onChanged() }} />
      </section>

      <section className="tool-panel test-section">
        <h3>Functional flow</h3>
        <ol className="flow-steps">
          {test.flow.map((step) => (
            <li key={step.step}>
              <span>{step.description}</span>
              {step.tab !== undefined && <span className="tab-badge">tab {step.tab}</span>}
              {step.element && <code>{[step.page, step.component, step.element].filter(Boolean).join('.')}</code>}
              {step.hover?.length ? <code>hover: {step.hover.join(' → ')}</code> : null}
            </li>
          ))}
        </ol>
      </section>

      <section className="tool-panel test-section">
        <h3>Element locators</h3>
        <p className="panel-copy">Element names are shared with the page repository (pages/…), so the same element has the same name in every test.</p>
        {Object.keys(test.pages).length === 0 && <p className="panel-copy">No elements were interacted with.</p>}
        {Object.entries(test.pages).map(([name, page]) => <PageLocators key={name} name={name} page={page} />)}
      </section>

      {test.history.length > 0 && (
        <section className="tool-panel test-section">
          <h3>Run history</h3>
          <ul className="run-history">
            {test.history.map((run) => (
              <li key={run.id}><RunBadge run={run} /> {run.browser} · {formatDate(run.at)}{run.healedSteps ? ` · ${run.healedSteps} XPaths refreshed` : ''}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export function TestLibrary({ initialSlug }: { initialSlug?: string | null }) {
  const [tests, setTests] = useState<TestSummary[] | null>(null)
  const [selected, setSelected] = useState<string | null>(initialSlug ?? null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setTests(await uiAutomationClient.listTests())
      setError('')
    } catch {
      setError('Could not load saved tests. Start the UI Automation controller on port 8004.')
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (initialSlug) setSelected(initialSlug) }, [initialSlug])

  if (selected) return <TestDetailView slug={selected} onBack={() => { setSelected(null); load() }} onChanged={load} />

  const visible = (tests || []).filter((test) => `${test.name} ${test.url}`.toLowerCase().includes(filter.trim().toLowerCase()))

  return (
    <div className="test-library">
      <div className="test-library-toolbar">
        <input className="text-input" type="search" placeholder="Search tests by name or URL" value={filter} onChange={(event) => setFilter(event.target.value)} />
        <button type="button" className="secondary-btn" onClick={load}>Refresh</button>
      </div>
      {error && <div className="connection-error">{error}</div>}
      {tests && !visible.length && <p className="panel-copy">{tests.length ? 'No tests match your search.' : 'No saved tests yet. Record a flow and it will appear here.'}</p>}
      <div className="test-grid">
        {visible.map((test) => (
          <button type="button" key={test.slug} className="test-card" onClick={() => setSelected(test.slug)}>
            <div className="test-card-heading"><strong>{test.name}</strong><RunBadge run={test.lastRun} /></div>
            <span className="test-card-url">{test.url}</span>
            <span className="test-meta">{test.stepCount} steps · {test.pageCount} pages · {test.elementCount} elements</span>
            <span className="test-meta">Updated {formatDate(test.updatedAt)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
