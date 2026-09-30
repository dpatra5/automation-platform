// Turns a raw recording into a readable test record plus a shared page-object repository:
//   tests/<test-slug>/test.json    - element name -> XPath per page/component, and the functional flow
//   pages/<host>/<page-slug>.json  - every element of a page (and its modals/frames), shared by all tests

export const CLICK_ACTIONS = new Set(['click', 'dblclick'])
const NOISE_ACTIONS = new Set(['hover', 'focus', 'mousedown', 'mouseup', 'keyup', 'wheel', 'scroll'])
const PAGE_ACTIONS = new Set(['newTab', 'switchTab', 'closeTab', 'back', 'forward', 'reload'])
const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'AltGraph', 'Fn'])
// Editing keys inside a text field are already reflected in the field's value.
const EDITING_KEYS = new Set(['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Home', 'End'])
const DYNAMIC_SEGMENT = /^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|[A-Za-z0-9_-]{24,})$/i

export function slugify(value, fallback = 'item') {
  const slug = String(value ?? '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
  return slug || fallback
}

export const isSlug = (value) => /^[a-z0-9]+(-[a-z0-9]+)*$/.test(String(value ?? ''))

function words(value) {
  return String(value ?? '').replace(/([a-z])([A-Z])/g, '$1 $2').split(/[^\p{L}\p{N}]+/u).filter(Boolean)
}

function camel(parts) {
  return parts.map((part, index) => {
    const lower = part.toLowerCase()
    return index === 0 ? lower : lower.charAt(0).toUpperCase() + lower.slice(1)
  }).join('')
}

const capitalize = (value) => value.charAt(0).toUpperCase() + value.slice(1)

export function isTypedCharacter(event) {
  const editable = ['input', 'textarea'].includes(event.element?.tag) || event.element?.attributes?.contenteditable === 'true'
  return editable && typeof event.key === 'string' && event.key.length === 1 && !event.modifiers?.ctrl && !event.modifiers?.meta && !event.modifiers?.alt
}

function isNoiseKey(event) {
  if (MODIFIER_KEYS.has(event.key) || isTypedCharacter(event)) return true
  const editable = ['input', 'textarea'].includes(event.element?.tag) || event.element?.attributes?.contenteditable === 'true'
  return editable && EDITING_KEYS.has(event.key) && !event.modifiers?.ctrl && !event.modifiers?.meta
}

const hasLocator = (element) => Boolean(element && (element.xpath || element.selector || element.id || element.testId || element.name || element.label || element.text))

// The browser reports one user gesture as several events; replaying each would click or type twice.
export function coveredBy(actionEvents, index) {
  const event = actionEvents[index]
  const upcoming = actionEvents.slice(index + 1, index + 5)
  if ((event.action === 'mousedown' || event.action === 'mouseup') && upcoming.some((next) => CLICK_ACTIONS.has(next.action))) return 'Performed by the following click step.'
  if (event.action === 'click' && upcoming.some((next) => next.action === 'dblclick' && next.element?.xpath === event.element?.xpath)) return 'Performed by the following double-click step.'
  if (event.action === 'keyup') return 'Replayed by its key-down step.'
  if (event.action === 'keydown' && isTypedCharacter(event)) return 'Typed text is replayed by the input step.'
  if (event.action === 'submit' && actionEvents.slice(Math.max(0, index - 4), index).some((previous) => CLICK_ACTIONS.has(previous.action) || (previous.action === 'keydown' && previous.key === 'Enter'))) return 'Form was submitted by the preceding step.'
  return null
}

export function pageIdentity(pageUrl) {
  let url
  try {
    url = new URL(pageUrl)
  } catch {
    return { host: 'unknown', path: '/', name: 'blankPage', file: 'pages/unknown/blank.json' }
  }
  if (!/^https?:$/.test(url.protocol)) return { host: 'unknown', path: '/', name: 'blankPage', file: 'pages/unknown/blank.json' }
  const segments = url.pathname.split('/').filter(Boolean)
  if (url.hash.startsWith('#/')) segments.push(...url.hash.slice(2).split(/[/?]/).filter(Boolean))
  const pattern = segments.map((segment) => DYNAMIC_SEGMENT.test(segment) ? ':id' : decodeURIComponent(segment).replace(/\.(html?|aspx?|php|jsp)$/i, ''))
  const nameParts = pattern.flatMap((segment) => segment === ':id' ? ['id'] : words(segment))
  const name = nameParts.length ? `${camel(nameParts.slice(-4))}Page` : 'homePage'
  const host = slugify(url.host, 'unknown')
  return { host: url.host, path: `/${pattern.join('/')}`, name, file: `pages/${host}/${slugify(pattern.join('-').replace(/:/g, ''), 'home')}.json` }
}

export function elementKind(element = {}) {
  const tag = element.tag || ''
  const role = element.role || ''
  const type = (element.attributes?.type || '').toLowerCase()
  if (role === 'tab') return 'tab'
  if (role === 'menuitem') return 'menuItem'
  if (role === 'option' || tag === 'option') return 'option'
  if (role === 'switch') return 'switch'
  if (tag === 'input' && ['submit', 'button', 'reset'].includes(type)) return 'button'
  if (tag === 'input' && ['checkbox', 'radio'].includes(type)) return type
  if (role === 'checkbox' || role === 'radio') return role
  if (tag === 'button' || role === 'button') return 'button'
  if (tag === 'a' || role === 'link') return 'link'
  if (tag === 'select' || role === 'combobox' || role === 'listbox') return 'dropdown'
  if (tag === 'textarea') return 'textArea'
  if (tag === 'input' || role === 'textbox' || element.attributes?.contenteditable === 'true') return 'input'
  if (tag === 'img' || tag === 'svg') return 'image'
  if (tag === 'label') return 'label'
  if (/^h[1-6]$/.test(tag)) return 'heading'
  return 'element'
}

export function elementBaseName(element = {}) {
  const attributes = element.attributes || {}
  const source = element.displayName || element.label || attributes.placeholder || attributes.title || attributes.alt ||
    (element.text && element.text.length <= 40 ? element.text : '') || element.name || element.testId || element.id || ''
  const kind = elementKind(element)
  const parts = words(source).slice(0, 5)
  if (!parts.length) return kind
  let name = camel(parts)
  if (/^\d/.test(name)) name = `${kind}${capitalize(name)}`
  return name.toLowerCase().endsWith(kind.toLowerCase()) ? name : `${name}${capitalize(kind)}`
}

function componentFor(event) {
  const container = event.element?.container
  const frame = Array.isArray(event.frame) && event.frame.length ? event.frame : null
  if (!container && !frame) return null
  const parts = []
  if (frame) parts.push(...(words(event.frameName).length ? words(event.frameName) : ['frame']), 'frame')
  if (container) parts.push(...words(container.name).slice(0, 4), container.kind === 'modal' ? 'modal' : container.kind)
  const kind = container ? container.kind : 'frame'
  return { name: camel(parts), kind, root: container?.xpath || null, frame }
}

const maskValue = (event) => (event.element?.attributes?.type || '').toLowerCase() === 'password' ? '********' : event.value

function describeStep(step, element) {
  const target = step.element ? `'${element?.displayName || element?.text || step.element}' ${elementKind(element).replace(/([A-Z])/g, ' $1').toLowerCase()}` : ''
  const where = step.component ? ` in ${step.component}` : ''
  const on = step.page ? ` on ${step.page}` : ''
  const via = step.hover?.length ? ` (after hovering ${step.hover.join(', ')})` : ''
  switch (step.action) {
    case 'open': return `Open ${step.url}`
    case 'navigate': return step.implicit ? `Verify the page navigates to ${step.url}` : `Navigate to ${step.url}`
    case 'back': return `Go back to ${step.url}`
    case 'forward': return `Go forward to ${step.url}`
    case 'reload': return `Reload ${step.url}`
    case 'newTab': return `New tab ${step.tab} opens${step.url ? ` with ${step.url}` : ''}`
    case 'switchTab': return `Switch to tab ${step.tab}${step.url ? ` (${step.url})` : ''}`
    case 'closeTab': return `Close tab ${step.tab}`
    case 'dialog': return `${step.accept === false ? 'Dismiss' : 'Accept'} ${step.dialogType} dialog "${step.message}"${step.promptText ? ` with "${step.promptText}"` : ''}`
    case 'fill': return `Enter "${step.value ?? ''}" into ${target}${where}${on}`
    case 'select': return `Select "${step.value ?? ''}" in ${target}${where}${on}`
    case 'check': return `Check ${target}${where}${on}`
    case 'uncheck': return `Uncheck ${target}${where}${on}`
    case 'press': return `Press ${step.key} in ${target}${where}${on}`
    case 'assert': return `Verify ${target}${where}${on} is visible${step.expectedText ? ` with text "${step.expectedText}"` : ''}`
    default: return `${capitalize(step.action)} ${target}${where}${on}${via}`.trim()
  }
}

// Plain-language label for an executable step, before element names are assigned.
export function describeRawStep(raw) {
  const element = raw.source?.element
  const name = element ? element.displayName || element.text || element.name || element.tag : undefined
  const hover = (raw.reveal || []).map((item) => item.displayName || item.text || item.tag).filter(Boolean)
  return describeStep({ ...raw, element: name, hover }, element)
}

// Collapses raw browser events into the steps a tester would perform; this is also what gets executed.
export function functionalSteps(flow) {
  const actions = (flow.events || []).filter((event) => event.type === 'action')
  const steps = [{ action: 'open', url: flow.url, tab: 0, source: null }]
  actions.forEach((event, index) => {
    if (NOISE_ACTIONS.has(event.action) || coveredBy(actions, index)) return
    const base = { tab: event.tab ?? null, url: event.pageUrl, source: event }
    if (event.action === 'navigate') return steps.push({ ...base, action: 'navigate', implicit: Boolean(event.implicit) })
    if (PAGE_ACTIONS.has(event.action)) {
      const previous = steps[steps.length - 1]
      if (event.action === 'switchTab' && previous?.action === 'switchTab') return Object.assign(previous, base)
      return steps.push({ ...base, action: event.action, openerTab: event.openerTab ?? null })
    }
    if (event.action === 'dialog') return steps.push({ ...base, action: 'dialog', dialogType: event.dialogType, message: event.message, accept: event.accept !== false, promptText: event.promptText ?? null })
    if (!hasLocator(event.element) || event.element.tag === 'page' || event.element.tag === 'dialog') return
    if (event.action === 'keydown' && isNoiseKey(event)) return
    const type = (event.element.attributes?.type || '').toLowerCase()
    let action = event.action
    let value
    if (event.action === 'input' || event.action === 'change') {
      if (event.element.tag === 'select') { action = 'select'; value = event.selected ?? event.value }
      else if (type === 'checkbox' || type === 'radio') action = event.element.checked ? 'check' : 'uncheck'
      else { action = 'fill'; value = maskValue(event) }
      const previous = steps[steps.length - 1]
      const sameElement = previous?.source?.element && (previous.source.element.xpath || previous.source.element.selector) === (event.element.xpath || event.element.selector)
      if (sameElement && ['fill', 'select', 'check', 'uncheck'].includes(previous.action)) {
        Object.assign(previous, { action, value, source: event })
        return
      }
    } else if (event.action === 'keydown') {
      action = 'press'
    } else if (event.action === 'dragstart') {
      action = 'drag'
    } else if (event.action === 'assert') {
      steps.push({ ...base, action, expectedText: event.expectedText || '' })
      return
    }
    steps.push({ ...base, action, value, key: event.key, reveal: event.reveal || [] })
  })
  return steps
}

function emptyPage(identity) {
  return { name: identity.name, host: identity.host, path: identity.path, elements: {}, components: {}, updatedAt: null }
}

function releaseTest(page, slug) {
  const prune = (elements) => {
    for (const [name, entry] of Object.entries(elements)) {
      entry.usedBy = (entry.usedBy || []).filter((test) => test !== slug)
      if (!entry.usedBy.length) delete elements[name]
    }
  }
  prune(page.elements)
  for (const [name, component] of Object.entries(page.components || {})) {
    prune(component.elements)
    if (!Object.keys(component.elements).length) delete page.components[name]
  }
}

// Reuses the name an XPath already has on the page so every test refers to one element the same way.
function registerElement(bucket, element, slug) {
  const existing = Object.entries(bucket.elements).find(([, entry]) => entry.xpath === element.xpath)
  let name = existing?.[0]
  if (!name) {
    const base = elementBaseName(element)
    name = base
    for (let suffix = 2; bucket.elements[name]; suffix += 1) name = `${base}${suffix}`
    bucket.elements[name] = { xpath: element.xpath, alternatives: (element.xpathCandidates || []).filter((xpath) => xpath !== element.xpath), tag: element.tag, kind: elementKind(element), text: element.displayName || element.text || '', usedBy: [] }
  }
  const entry = bucket.elements[name]
  entry.alternatives = [...new Set([...(entry.alternatives || []), ...(element.xpathCandidates || [])])].filter((xpath) => xpath !== entry.xpath).slice(0, 4)
  if (!entry.usedBy.includes(slug)) entry.usedBy.push(slug)
  return name
}

/**
 * @param flow recorded flow with testSlug/flowName/url/events
 * @param loadPage (file) => existing page document or null
 * @param previousTest earlier test.json for this slug (keeps createdAt/lastRun/history)
 */
export function buildRepository(flow, loadPage, previousTest = null) {
  const slug = flow.testSlug
  const now = new Date().toISOString()
  const pages = new Map()
  const pageFor = (identity) => {
    if (!pages.has(identity.file)) {
      const page = loadPage(identity.file) || emptyPage(identity)
      page.components ||= {}
      releaseTest(page, slug)
      pages.set(identity.file, page)
    }
    return pages.get(identity.file)
  }
  for (const file of previousTest ? Object.values(previousTest.pages || {}).map((page) => page.file) : []) {
    if (!pages.has(file)) {
      const page = loadPage(file)
      if (page) { releaseTest(page, slug); pages.set(file, page) }
    }
  }

  const testPages = {}
  // Files the element under its page (and modal/iframe component) in both the shared page and this test.
  const register = (element, event) => {
    const identity = pageIdentity(event.pageUrl)
    const page = pageFor(identity)
    const component = componentFor({ ...event, element })
    let bucket = page
    if (component) {
      page.components[component.name] ||= { kind: component.kind, root: component.root, frame: component.frame, elements: {} }
      bucket = page.components[component.name]
      if (component.root) bucket.root = component.root
    }
    const name = registerElement(bucket, element, slug)
    const testPage = testPages[identity.name] ||= { file: identity.file, path: identity.path, elements: {}, components: {} }
    if (component) {
      const testComponent = testPage.components[component.name] ||= { kind: component.kind, root: component.root, frame: component.frame, elements: {} }
      testComponent.elements[name] = bucket.elements[name].xpath
    } else {
      testPage.elements[name] = bucket.elements[name].xpath
    }
    return { page: identity.name, component: component?.name, name, xpath: bucket.elements[name].xpath }
  }

  const flowSteps = functionalSteps(flow).map((raw, index) => {
    const step = { step: index + 1, action: raw.action }
    if (raw.tab != null) step.tab = raw.tab
    for (const key of ['url', 'implicit', 'dialogType', 'message', 'accept', 'promptText', 'value', 'key', 'expectedText']) if (raw[key] !== undefined && raw[key] !== null && raw[key] !== false && raw[key] !== '') step[key] = raw[key]
    if (raw.action === 'dialog') step.accept = raw.accept
    const element = raw.source?.element
    if (element?.xpath) {
      const hover = (raw.reveal || []).filter((item) => item.xpath).map((item) => register(item, raw.source).name)
      if (hover.length) step.hover = hover
      const registered = register(element, raw.source)
      step.page = registered.page
      if (registered.component) step.component = registered.component
      step.element = registered.name
      step.xpath = registered.xpath
    } else if (raw.url && raw.action !== 'dialog') {
      step.page = pageIdentity(raw.url).name
    }
    step.description = describeStep(step, element)
    return step
  })

  for (const page of pages.values()) page.updatedAt = now
  const test = {
    name: flow.flowName,
    slug,
    flowId: flow.id,
    url: flow.url,
    createdAt: previousTest?.createdAt || flow.createdAt || now,
    updatedAt: now,
    lastRun: previousTest?.lastRun || null,
    history: previousTest?.history || [],
    pages: testPages,
    flow: flowSteps,
  }
  return { test, pages }
}
