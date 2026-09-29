export const SPRINTGUARD_EVENT_BUS = 'sprintguard.rewind'

export const REWIND_EVENT = {
  submit: 'rewind:submit',
  status: 'rewind:status',
  result: 'rewind:result',
} as const

export const SCRIPT_FORMAT_VERSION = '1.0.0'
export const VAGUE_STEP_PATTERNS: RegExp[] = [
  /^verify (the )?(application|system|page) works?$/i,
  /^check (the )?response$/i,
  /^validate (the )?page$/i,
  /^test (the )?functionality$/i,
  /^it works$/i,
]
