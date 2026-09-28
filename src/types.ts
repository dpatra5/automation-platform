export type MenuKey = 'project-plan' | 'api-testing' | 'load-testing' | 'rewind-automation' | 'ui-automation'

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
    description: 'Build API test collections with assertions, chaining, data-driven runs and CI reports.',
    icon: '🔌',
  },
  {
    key: 'load-testing',
    label: 'Load Testing',
    description: 'Simulate concurrent user load and measure performance.',
    icon: '📈',
  },
  {
    key: 'rewind-automation',
    label: 'Rewind Automation Tool',
    description: 'Open the independent Rewind regression testing tool.',
    icon: '🖥️',
  },
  {
    key: 'ui-automation',
    label: 'UI Automation',
    description: 'Start a separate browser-flow automation workspace for recording and validating UI scenarios.',
    icon: '🎯',
  },
]
