import { recorderScript } from './recorder.mjs'

export function xpathLiteral(value) {
  if (!value.includes("'")) return `'${value}'`
  if (!value.includes('"')) return `"${value}"`
  return `concat('${value.split("'").join(`', "'", '`)}')`
}

export function createSession({ id, flowName, testSlug, url }) {
  return { id, flowName, testSlug, url, currentUrl: url, status: 'starting', events: [], script: '', context: null, browser: null, startedAt: new Date().toISOString(), tabs: new Map(), frames: new WeakMap(), nextTab: 0, lastTab: null, dialogPolicy: 'accept' }
}

export async function handleControl(session, event, stop) {
  if (event.action === 'stop') await stop(session)
  else if (event.action === 'pause' && session.status === 'recording') session.status = 'paused'
  else if (event.action === 'resume' && session.status === 'paused') session.status = 'recording'
  else if (event.action === 'dialog-policy') session.dialogPolicy = event.value === 'dismiss' ? 'dismiss' : 'accept'
}

const pageMarker = (tag = 'page') => ({ selector: '', tag })
// Actions that can make the page navigate; a navigation shortly after one of them was caused by the app.
const NAVIGATION_TRIGGERS = new Set(['click', 'dblclick', 'keydown', 'submit', 'change', 'input'])
const USER_NAVIGATION_GAP_MS = 1500

function switchTo(session, tab, url) {
  if (session.lastTab !== null && session.lastTab !== tab.tab) {
    session.events.push({ type: 'action', action: 'switchTab', tab: tab.tab, pageUrl: url, element: pageMarker() })
  }
  session.lastTab = tab.tab
}

async function frameChain(frame) {
  const xpaths = []
  let current = frame
  while (current.parentFrame()) {
    const handle = await current.frameElement()
    const xpath = await handle.evaluate((node) => window.__uiAutomationXPath?.candidates(node, 1)[0] || '').catch(() => '')
    await handle.dispose()
    const name = current.name()
    xpaths.unshift(xpath || (name ? `//iframe[@name=${xpathLiteral(name)}]` : '//iframe'))
    current = current.parentFrame()
  }
  let name = frame.name()
  if (!name) {
    try { name = new URL(frame.url()).pathname.split('/').filter(Boolean).pop() || '' } catch { name = '' }
  }
  return { xpaths, name: name || 'frame' }
}

// Tags each recorded event with its tab and iframe so replay can act in the same place.
function annotateEvent(session, event, source) {
  const tab = source?.page ? session.tabs.get(source.page) : null
  if (!tab) return
  event.tab = tab.tab
  switchTo(session, tab, source.page.url())
  if (NAVIGATION_TRIGGERS.has(event.action)) {
    tab.hadAction = true
    tab.lastActionAt = Date.now()
  }
  const frame = source.frame
  if (frame && frame !== source.page.mainFrame()) {
    event.frameUrl = event.pageUrl
    event.pageUrl = source.page.url()
    if (!session.frames.has(frame)) session.frames.set(frame, frameChain(frame).catch(() => ({ xpaths: [], name: 'frame' })))
    return session.frames.get(frame).then((chain) => {
      if (chain.xpaths.length) {
        event.frame = chain.xpaths
        event.frameName = chain.name
      }
    })
  }
}

function attachPageTracking(session, page, port) {
  const tab = { tab: session.nextTab++, navigated: false, hadAction: false, lastActionAt: 0, lastUrl: '', openEvent: null, closed: false, history: [], position: -1 }
  session.tabs.set(page, tab)
  if (tab.tab > 0 && session.status === 'recording') {
    tab.openEvent = { type: 'action', action: 'newTab', tab: tab.tab, openerTab: null, pageUrl: page.url(), element: pageMarker() }
    session.events.push(tab.openEvent)
    session.lastTab = tab.tab
    page.opener().then((opener) => { tab.openEvent.openerTab = opener ? session.tabs.get(opener)?.tab ?? null : null }).catch(() => {})
  }
  const script = recorderScript(session.id, port)
  page.on('domcontentloaded', () => page.evaluate(script).catch(() => {}))
  page.on('load', () => page.evaluate(script).catch(() => {}))
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return
    const url = frame.url()
    if (!tab.navigated) {
      if (url === 'about:blank') return
      tab.navigated = true
      tab.lastUrl = url
      tab.history = [url]
      tab.position = 0
      if (tab.openEvent) tab.openEvent.pageUrl = url
      session.currentUrl = url
      return
    }
    if (url === tab.lastUrl) return
    tab.lastUrl = url
    session.currentUrl = url
    const sinceAction = Date.now() - tab.lastActionAt
    const userDriven = !tab.hadAction || sinceAction >= USER_NAVIGATION_GAP_MS
    // Browser back/forward: the URL matches the neighbouring history entry and no page action caused it.
    let action = 'navigate'
    if (userDriven && url === tab.history[tab.position - 1]) { tab.position -= 1; action = 'back' }
    else if (userDriven && url === tab.history[tab.position + 1]) { tab.position += 1; action = 'forward' }
    else {
      tab.history = [...tab.history.slice(0, tab.position + 1), url]
      tab.position = tab.history.length - 1
    }
    if (session.status !== 'recording') return
    if (action !== 'navigate') return session.events.push({ type: 'action', action, tab: tab.tab, pageUrl: url, element: pageMarker() })
    const implicit = !tab.hadAction || sinceAction < 5000
    session.events.push({ type: 'action', action: 'navigate', tab: tab.tab, implicit, pageUrl: url, element: pageMarker() })
  })
  page.on('close', () => {
    tab.closed = true
    if (session.status === 'recording') session.events.push({ type: 'action', action: 'closeTab', tab: tab.tab, pageUrl: tab.lastUrl, element: pageMarker() })
    if (session.lastTab === tab.tab) session.lastTab = null
  })
}

// Native alert/confirm/prompt dialogs block the page, so they are answered per the toolbar policy and recorded as steps.
async function recordDialog(session, dialog) {
  const type = dialog.type()
  const accept = type === 'beforeunload' || session.dialogPolicy !== 'dismiss'
  const page = dialog.page()
  if (session.status === 'recording' && type !== 'beforeunload') {
    session.events.push({ type: 'action', action: 'dialog', tab: page ? session.tabs.get(page)?.tab : undefined, dialogType: type, message: dialog.message(), accept, promptText: type === 'prompt' && accept ? dialog.defaultValue() : null, pageUrl: page?.url() ?? '', element: pageMarker('dialog') })
  }
  await (accept ? dialog.accept() : dialog.dismiss()).catch(() => {})
}

// Wires the recorder into every tab, popup, iframe and dialog of the context. Call before opening pages.
export async function attachRecorder(session, context, { port, stop }) {
  session.context = context
  session.pending = new Set()
  await context.exposeBinding('uiAutomationRecord', async (source, payload) => {
    const event = payload && typeof payload === 'object' ? payload : { type: 'warning', message: 'Invalid recorder event' }
    if (event.type === 'control') return handleControl(session, event, stop)
    const tab = source?.page ? session.tabs.get(source.page) : null
    if (event.type === 'tab-visible') {
      if (tab && session.status === 'recording') switchTo(session, tab, source.page.url())
      return
    }
    if (event.type === 'page-load') {
      // A reload keeps the URL, so framenavigated cannot tell it apart; the page reports it instead.
      if (tab && event.navType === 'reload' && session.status === 'recording' && tab.navigated && Date.now() - tab.lastActionAt >= USER_NAVIGATION_GAP_MS) {
        session.events.push({ type: 'action', action: 'reload', tab: tab.tab, pageUrl: event.pageUrl, element: pageMarker() })
      }
      return
    }
    if (event.type === 'action' && session.status !== 'recording') return
    const framed = annotateEvent(session, event, source)
    session.events.push(event)
    if (framed) {
      session.pending.add(framed)
      framed.finally(() => session.pending.delete(framed))
    }
  })
  await context.addInitScript({ content: recorderScript(session.id, port) })
  context.on('page', (page) => attachPageTracking(session, page, port))
  context.on('dialog', (dialog) => recordDialog(session, dialog))
}
