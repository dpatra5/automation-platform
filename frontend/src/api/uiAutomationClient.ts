const CONTROLLER_URL = import.meta.env.VITE_UI_AUTOMATION_CONTROLLER_URL ?? 'http://127.0.0.1:8004'

export interface UiAutomationSession {
  id: string
  flowName: string
  testSlug?: string
  status: 'starting' | 'recording' | 'paused' | 'stopped' | 'error'
  eventCount: number
  currentUrl: string
  dialogPolicy?: 'accept' | 'dismiss'
  openTabs?: number
  actions?: Array<{ action: string; pageUrl: string; tab?: number; text?: string; value?: string; xpath?: string }>
}

export interface SoftAssertion {
  label: string
  passed: boolean
  detail: string
}

export interface ReplayResult {
  index: number
  action: string
  description?: string
  pageUrl: string
  status: 'passed' | 'failed' | 'skipped'
  message: string
  assertions?: SoftAssertion[]
  notes?: string[]
  locator?: string
  tab?: number
}

export interface RunSummary {
  status: 'passed' | 'failed'
  startedAt: string
  finishedAt: string
  durationMs: number
  steps: { total: number; passed: number; failed: number }
  assertions: { total: number; passed: number; failed: number }
  failures: Array<{ step: number; description: string; reasons: string[] }>
}

export interface ReplaySession {
  id: string
  flowId: string
  testSlug?: string
  status: 'running' | 'passed' | 'failed'
  browser: string
  results: ReplayResult[]
  summary?: RunSummary | null
  browserOpen?: boolean
  sharedBrowser?: boolean
  healedSteps?: number
}

export const reportUrl = (replayId: string, format: 'json' | 'html') =>
  `${CONTROLLER_URL}/api/replays/${encodeURIComponent(replayId)}/report${format === 'html' ? '.html' : ''}`

export type BrowserName = 'chromium' | 'firefox' | 'webkit'

export interface TestRun {
  id: string
  status: 'passed' | 'failed' | 'running'
  browser: string
  at: string
  passed: number
  failed: number
  assertionsPassed?: number
  assertionsFailed?: number
  durationMs?: number
  healedSteps: number
}

export interface TestSummary {
  slug: string
  name: string
  url: string
  flowId: string
  createdAt: string
  updatedAt: string
  lastRun: TestRun | null
  stepCount: number
  pageCount: number
  elementCount: number
}

export interface TestComponent {
  kind: string
  root: string | null
  frame: string[] | null
  elements: Record<string, string>
}

export interface TestPage {
  file: string
  path: string
  elements: Record<string, string>
  components: Record<string, TestComponent>
}

export interface TestStep {
  step: number
  action: string
  description: string
  tab?: number
  page?: string
  component?: string
  element?: string
  hover?: string[]
  expectedText?: string
  xpath?: string
  value?: string
  key?: string
  url?: string
}

export interface TestDetail extends Omit<TestSummary, 'stepCount' | 'pageCount' | 'elementCount'> {
  history: TestRun[]
  pages: Record<string, TestPage>
  flow: TestStep[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${CONTROLLER_URL}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  if (!response.ok) throw new Error(`UI automation controller returned ${response.status}`)
  return response.json() as Promise<T>
}

export const uiAutomationClient = {
  start: (url: string, flowName: string) =>
    request<{ id: string; status: UiAutomationSession['status']; flowName: string }>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ url, flowName }),
    }),
  status: (id: string) => request<UiAutomationSession>(`/api/sessions/${id}`),
  stop: (id: string) => request<UiAutomationSession>(`/api/sessions/${id}/stop`, { method: 'POST' }),
  replay: (id: string, browser: BrowserName, data: Record<string, string>) =>
    request<{ id: string; status: string; browser: string }>(`/api/flows/${id}/replay`, {
      method: 'POST',
      body: JSON.stringify({ browser, data }),
    }),
  replayStatus: (id: string) => request<ReplaySession>(`/api/replays/${id}`),
  closeReplay: (id: string) => request<{ id: string; status: string; browserOpen: boolean }>(`/api/replays/${id}/close`, { method: 'POST' }),
  openSharedBrowser: (url: string, browser: BrowserName) =>
    request<{ browser: string; url: string }>('/api/shared-browser/open', { method: 'POST', body: JSON.stringify({ url, browser }) }),
  listTests: () => request<TestSummary[]>('/api/tests'),
  getTest: (slug: string) => request<TestDetail>(`/api/tests/${encodeURIComponent(slug)}`),
  runTest: (slug: string, browser: BrowserName, data: Record<string, string>) =>
    request<{ id: string; status: string; browser: string }>(`/api/tests/${encodeURIComponent(slug)}/replay`, {
      method: 'POST',
      body: JSON.stringify({ browser, data }),
    }),
}
