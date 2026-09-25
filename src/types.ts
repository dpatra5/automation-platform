export type MenuKey = 'project-plan' | 'api-testing' | 'load-testing' | 'ui-automation'

export interface MenuItem {
  key: MenuKey
  label: string
  description: string
  icon: string
}

export type JobStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed'

export const MENU_ITEMS: MenuItem[] = [
  {
    key: 'project-plan',
    label: 'Project Plan Creation',
    description: 'Analyze a problem statement and generate summary, acceptance criteria, SDLC, STLC and Jira tickets.',
    icon: '📋',
  },
  {
    key: 'api-testing',
    label: 'API Testing',
    description: 'Run automated API test suites against your service endpoints.',
    icon: '🔌',
  },
  {
    key: 'load-testing',
    label: 'Load Testing',
    description: 'Simulate concurrent user load and measure performance.',
    icon: '📈',
  },
  {
    key: 'ui-automation',
    label: 'UI Automation',
    description: 'Run automated UI regression scenarios across browsers.',
    icon: '🖥️',
  },
]
