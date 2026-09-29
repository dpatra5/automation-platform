const CONTROLLER_URL = import.meta.env.VITE_UI_AUTOMATION_CONTROLLER_URL ?? 'http://127.0.0.1:8004'

export interface UiAutomationSession {
  id: string
  flowName: string
  status: 'starting' | 'recording' | 'paused' | 'stopped' | 'error'
  eventCount: number
  currentUrl: string
  actions?: Array<{ action: string; pageUrl: string; text?: string; value?: string }>
}

export interface ReplayResult {
  index: number
  action: string
  pageUrl: string
  status: 'passed' | 'failed'
  message: string
}

export interface ReplaySession {
  id: string
  flowId: string
  status: 'running' | 'passed' | 'failed'
  browser: string
  results: ReplayResult[]
  browserOpen?: boolean
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
  replay: (id: string, browser: 'chromium' | 'firefox' | 'webkit', data: Record<string, string>) =>
    request<{ id: string; status: string; browser: string }>(`/api/flows/${id}/replay`, {
      method: 'POST',
      body: JSON.stringify({ browser, data }),
    }),
  replayStatus: (id: string) => request<ReplaySession>(`/api/replays/${id}`),
  closeReplay: (id: string) => request<{ id: string; status: string; browserOpen: boolean }>(`/api/replays/${id}/close`, { method: 'POST' }),
}
