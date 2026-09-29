import http from 'node:http'
import { randomUUID } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, firefox, webkit } from 'playwright'

const port = Number(process.env.UI_AUTOMATION_PORT || 8004)
const sessions = new Map()
const flows = new Map()
const replays = new Map()
const dataDirectory = path.resolve(process.env.UI_AUTOMATION_DATA_DIR || path.join(path.dirname(fileURLToPath(import.meta.url)), 'data'))
const chromiumExecutable = process.env.UI_AUTOMATION_CHROMIUM_PATH || chromium.executablePath()

await fs.mkdir(dataDirectory, { recursive: true })

const flowFile = (id) => path.join(dataDirectory, `${id}.json`)

async function saveFlow(flow) {
  await fs.writeFile(flowFile(flow.id), JSON.stringify(flow, null, 2))
  flows.set(flow.id, flow)
}

async function loadFlow(id) {
  if (flows.has(id)) return flows.get(id)
  try {
    const flow = JSON.parse(await fs.readFile(flowFile(id), 'utf8'))
    flows.set(id, flow)
    return flow
  } catch {
    return null
  }
}

function browserFor(name) {
  return name === 'firefox' ? firefox : name === 'webkit' ? webkit : chromium
}

function normalizeUrl(value) {
  const url = String(value || '').trim()
  return /^https?:\/\//i.test(url) ? url : `https://${url}`
}

const recorderScript = (sessionId) => `
(() => {
  if (window.__uiAutomationRecorder) return;
  window.__uiAutomationRecorder = true;
  const state = { paused: false };
  let lastHoverKey = '';
  let lastHoverAt = 0;
  const send = (payload) => {
    if (typeof window.uiAutomationRecord === 'function') return window.uiAutomationRecord(payload);
    return fetch('http://127.0.0.1:${port}/api/sessions/${sessionId}/events', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload), keepalive: true
    }).catch(() => {});
  };
  const xpathLiteral = (value) => {
    if (!value.includes("'")) return "'" + value + "'";
    if (!value.includes('"')) return '"' + value + '"';
    return 'concat(' + value.split("'").map((part) => "'" + part + "'").join(", \"'\", ") + ')';
  };
  const xpathMatches = (xpath, element) => {
    try {
      const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      return result.snapshotLength === 1 && result.snapshotItem(0) === element;
    } catch { return false; }
  };
  const stableId = (value) => value && !/^\\d/.test(value) && !/[\\s:]/.test(value) && !/[-_]([a-f\\d]{6,})$/i.test(value);
  const xpathPredicates = (element) => {
    const predicates = [];
    for (const attribute of ['data-testid', 'data-test-id', 'data-test', 'data-cy', 'data-qa', 'aria-label', 'name', 'placeholder', 'title', 'alt', 'href']) {
      const value = element.getAttribute(attribute);
      if (value && value.length <= 100) predicates.push('@' + attribute + '=' + xpathLiteral(value));
    }
    if (stableId(element.id)) predicates.push('@id=' + xpathLiteral(element.id));
    if (element.getAttribute('role')) predicates.push('@role=' + xpathLiteral(element.getAttribute('role')));
    if (element.getAttribute('type')) predicates.push('@type=' + xpathLiteral(element.getAttribute('type')));
    return predicates.slice(0, 6);
  };
  const xpathStep = (element) => {
    const tag = element.tagName.toLowerCase();
    let index = 1;
    let count = 0;
    for (const sibling of element.parentElement?.children || []) {
      if (sibling.tagName !== element.tagName) continue;
      count += 1;
      if (sibling === element) index = count;
    }
    return count > 1 ? tag + '[' + index + ']' : tag;
  };
  const relativeXPath = (element) => {
    const tag = element.tagName.toLowerCase();
    const predicates = xpathPredicates(element);
    for (const predicate of predicates) {
      const xpath = '//' + tag + '[' + predicate + ']';
      if (xpathMatches(xpath, element)) return xpath;
    }
    const text = (element.innerText || element.textContent || '').trim().slice(0, 80);
    if (text && ['button', 'a', 'label', 'summary', 'option', 'li', 'td', 'th'].includes(tag)) {
      const xpath = '//' + tag + '[normalize-space()=' + xpathLiteral(text) + ']';
      if (xpathMatches(xpath, element)) return xpath;
    }
    const steps = [];
    let current = element;
    while (current && current !== document.body && current.tagName.toLowerCase() !== 'html') {
      const currentTag = current.tagName.toLowerCase();
      const anchor = xpathPredicates(current)[0];
      steps.unshift(xpathStep(current));
      if (anchor) {
        const xpath = '//' + currentTag + '[' + anchor + ']/' + steps.slice(1).join('/');
        if (xpathMatches(xpath, element)) return xpath;
      }
      current = current.parentElement;
    }
    return '//' + steps.join('/');
  };
  const describe = (element) => {
    if (!(element instanceof Element)) return { selector: '', tag: '' };
    const tag = element.tagName.toLowerCase();
    const id = element.getAttribute('id');
    const testId = element.getAttribute('data-testid');
    const role = element.getAttribute('role');
    const label = element.getAttribute('aria-label');
    const selector = relativeXPath(element);
    const attributes = Object.fromEntries([...element.attributes].map((attribute) => [attribute.name, attribute.value]));
    return { selector, xpath: selector, tag, id, testId, role, label, text: (element.textContent || '').trim().slice(0, 120), value: element.value ?? null, checked: element.checked ?? null, selected: element.selected ?? null, attributes };
  };
  const record = (event) => {
    if (state.paused) return;
    const element = describe(event.target);
    if (event.action === 'hover') {
      const key = element.selector || element.id || element.tag;
      const now = Date.now();
      if (key === lastHoverKey && now - lastHoverAt < 350) return;
      lastHoverKey = key;
      lastHoverAt = now;
    }
    send({ type: 'action', ...event, pageUrl: location.href, element });
  };
  const later = (payload) => setTimeout(() => record(payload), 0);
  document.addEventListener('click', (event) => later({ action: 'click', target: event.target, button: event.button, x: event.clientX, y: event.clientY, modifiers: { alt: event.altKey, ctrl: event.ctrlKey, shift: event.shiftKey, meta: event.metaKey } }), true);
  document.addEventListener('dblclick', (event) => later({ action: 'dblclick', target: event.target, x: event.clientX, y: event.clientY }), true);
  document.addEventListener('mousedown', (event) => record({ action: 'mousedown', target: event.target, button: event.button, x: event.clientX, y: event.clientY }), true);
  document.addEventListener('mouseup', (event) => record({ action: 'mouseup', target: event.target, button: event.button, x: event.clientX, y: event.clientY }), true);
  document.addEventListener('mouseover', (event) => record({ action: 'hover', target: event.target }), true);
  document.addEventListener('focusin', (event) => record({ action: 'focus', target: event.target }), true);
  document.addEventListener('input', (event) => later({ action: 'input', target: event.target, value: event.target?.value ?? '' }), true);
  document.addEventListener('change', (event) => later({ action: 'change', target: event.target, value: event.target?.value ?? '', selected: event.target?.selectedOptions?.[0]?.text ?? null }), true);
  document.addEventListener('keydown', (event) => record({ action: 'keydown', target: event.target, key: event.key, code: event.code, modifiers: { alt: event.altKey, ctrl: event.ctrlKey, shift: event.shiftKey, meta: event.metaKey } }), true);
  document.addEventListener('keyup', (event) => record({ action: 'keyup', target: event.target, key: event.key, code: event.code }), true);
  document.addEventListener('wheel', (event) => record({ action: 'wheel', target: event.target, deltaX: event.deltaX, deltaY: event.deltaY }), true);
  document.addEventListener('scroll', (event) => record({ action: 'scroll', target: event.target, x: window.scrollX, y: window.scrollY }), true);
  document.addEventListener('dragstart', (event) => record({ action: 'dragstart', target: event.target }), true);
  document.addEventListener('drop', (event) => record({ action: 'drop', target: event.target }), true);
  document.addEventListener('submit', (event) => later({ action: 'submit', target: event.target }), true);
  const snapshot = () => send({ type: 'dom', pageUrl: location.href, html: document.documentElement.outerHTML.slice(0, 200000) });
  let mutationTimer;
  new MutationObserver(() => { if (!state.paused) { clearTimeout(mutationTimer); mutationTimer = setTimeout(() => send({ type: 'dom-change', pageUrl: location.href, html: document.documentElement.outerHTML.slice(0, 200000) }), 100); } }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  window.addEventListener('load', snapshot);
  const toolbar = document.createElement('div');
  toolbar.id = '__ui-automation-toolbar';
  toolbar.innerHTML = '<strong>UI Automation</strong><span id="__ui-status">Recording</span><button data-action="pause">Pause</button><button data-action="resume" hidden>Resume</button><button data-action="stop">Stop</button>';
  Object.assign(toolbar.style, { position: 'fixed', zIndex: '2147483647', bottom: '16px', right: '16px', display: 'flex', gap: '8px', alignItems: 'center', padding: '10px 12px', borderRadius: '10px', background: '#101323', color: '#fff', font: '13px Segoe UI, sans-serif', boxShadow: '0 8px 24px #0005' });
  toolbar.querySelectorAll('button').forEach((button) => { Object.assign(button.style, { border: '0', borderRadius: '6px', padding: '5px 8px', cursor: 'pointer' }); button.addEventListener('click', () => {
    const action = button.dataset.action;
    if (action === 'pause') { state.paused = true; toolbar.querySelector('[data-action="pause"]').hidden = true; toolbar.querySelector('[data-action="resume"]').hidden = false; toolbar.querySelector('#__ui-status').textContent = 'Paused'; send({ type: 'control', action: 'pause' }); }
    if (action === 'resume') { state.paused = false; toolbar.querySelector('[data-action="pause"]').hidden = false; toolbar.querySelector('[data-action="resume"]').hidden = true; toolbar.querySelector('#__ui-status').textContent = 'Recording'; send({ type: 'control', action: 'resume' }); }
    if (action === 'stop') send({ type: 'control', action: 'stop' });
  }); });
  (document.body || document.documentElement).appendChild(toolbar);
})();
`

function json(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json', 'access-control-allow-origin': '*' })
  res.end(JSON.stringify(body))
}

function readBody(req) {
  return new Promise((resolve) => { let data = ''; req.on('data', (chunk) => { data += chunk }); req.on('end', () => resolve(data ? JSON.parse(data) : {})) })
}

function scriptFor(session) {
  const lines = [`import { test, expect } from '@playwright/test`, '', `test.use({ storageState: './data/${session.id}.storage.json' })`, '', `test('${session.flowName.replace(/'/g, "\\'")}', async ({ page }) => {`, `  await page.goto(${JSON.stringify(session.url)})`]
  for (const event of session.events.filter((item) => item.type === 'action')) {
    const locator = event.element?.testId ? `page.getByTestId(${JSON.stringify(event.element.testId)})` : event.element?.role ? `page.getByRole(${JSON.stringify(event.element.role)})` : event.element?.label ? `page.getByLabel(${JSON.stringify(event.element.label)})` : event.element?.text ? `page.getByText(${JSON.stringify(event.element.text)})` : `page.locator(${JSON.stringify(event.element?.id ? `#${event.element.id}` : event.element?.selector || event.element?.tag || 'body')})`
    if (event.action === 'click') lines.push(`  await ${locator}.click()`)
    if (event.action === 'input' || event.action === 'change') lines.push(`  await ${locator}.fill(${JSON.stringify(event.value || '')})`)
    if (event.action === 'keydown') lines.push(`  await ${locator}.press(${JSON.stringify(event.key)})`)
  }
  lines.push('})')
  return lines.join('\n')
}

async function stopSession(session) {
  if (session.status === 'stopped') return
  session.status = 'stopped'
  await new Promise((resolve) => setTimeout(resolve, 300))
  if (session.context) {
    try {
      session.storageState = await session.context.storageState()
    } catch (error) {
      session.events.push({ type: 'warning', message: `Browser closed before authentication state could be saved: ${error.message}` })
    }
  }
  session.storageStateFile = `./data/${session.id}.storage.json`
  if (session.storageState) await fs.writeFile(path.join(dataDirectory, `${session.id}.storage.json`), JSON.stringify(session.storageState, null, 2))
  session.script = scriptFor(session)
  await saveFlow({ id: session.id, flowName: session.flowName, url: session.url, events: session.events, script: session.script, storageState: session.storageState })
  try {
    await session.context?.close()
  } catch {
    // The browser may already have been closed by the user.
  }
  try {
    await session.browser?.close()
  } catch {
    // The browser may already have been closed by the user.
  }
}

function actionSummary(events) {
  return events.filter((event) => event.type === 'action').map((event) => ({
    action: event.action,
    pageUrl: event.pageUrl,
    text: event.element?.text,
    value: event.value,
  }))
}

function attachPageTracking(session, page) {
  page.on('domcontentloaded', () => page.evaluate(recorderScript(session.id)).catch(() => {}))
  page.on('load', () => page.evaluate(recorderScript(session.id)).catch(() => {}))
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame() && session.status === 'recording' && frame.url() !== session.url) {
      session.events.push({ type: 'action', action: 'navigate', pageUrl: frame.url(), element: { selector: '', tag: 'page' } })
    }
  })
}

function replayView(replay) {
  return { id: replay.id, flowId: replay.flowId, status: replay.status, browser: replay.browser, results: replay.results, browserOpen: replay.browserOpen ?? false }
}

function substitute(value, data) {
  return String(value ?? '').replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key) => data[key] ?? `{{${key}}}`)
}

async function waitForTarget(page, selector, timeout = 15000) {
  const target = page.locator(selector.startsWith('/') ? `xpath=${selector}` : selector).first()
  const deadline = Date.now() + timeout
  let lastError
  while (Date.now() < deadline) {
    try {
      await target.waitFor({ state: 'attached', timeout: Math.min(2000, deadline - Date.now()) })
      await target.scrollIntoViewIfNeeded({ timeout: 2000 })
      await target.waitFor({ state: 'visible', timeout: Math.min(2000, deadline - Date.now()) })
      return target
    } catch (error) {
      lastError = error
      await page.waitForTimeout(250)
    }
  }
  throw lastError || new Error(`Element not found: ${selector}`)
}

async function replayFlow(flow, browserName, data, replayId) {
  const replay = replays.get(replayId) || { id: replayId, flowId: flow.id, status: 'running', browser: browserName, results: [], browserProcess: null }
  replays.set(replayId, replay)
  const browserType = browserFor(browserName)
  try {
    const browser = await browserType.launch({ headless: false })
    replay.browserProcess = browser
    const context = await browser.newContext(flow.storageState ? { storageState: flow.storageState } : {})
    const pages = new Map()
    let activePage = null
    const firstPage = await context.newPage()
    activePage = firstPage
    pages.set(flow.url, firstPage)
    context.on('page', (page) => {
      activePage = page
      page.on('domcontentloaded', () => pages.set(page.url(), page))
      page.on('load', () => pages.set(page.url(), page))
    })
    await firstPage.goto(normalizeUrl(substitute(flow.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
    const actionEvents = flow.events.filter((item) => item.type === 'action')
    for (const [index, event] of actionEvents.entries()) {
      const result = { index: index + 1, action: event.action, pageUrl: event.pageUrl, status: 'passed', message: '' }
      try {
        const page = pages.get(event.pageUrl) || activePage || firstPage
        page.setDefaultTimeout(5000)
        await page.waitForLoadState('domcontentloaded').catch(() => {})
        if (event.action === 'navigate') {
          await page.goto(normalizeUrl(substitute(event.pageUrl, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
        } else {
        const selector = event.element?.testId ? `[data-testid="${event.element.testId}"]` : event.element?.id ? `#${event.element.id}` : event.element?.label ? `[aria-label="${event.element.label}"]` : event.element?.selector || (event.element?.text ? `text=${event.element.text}` : event.element?.tag || 'body')
        const coordinateAction = ['mousedown', 'mouseup', 'wheel', 'scroll'].includes(event.action) || (['click', 'dblclick'].includes(event.action) && Number.isFinite(event.x) && Number.isFinite(event.y))
        let target = null
        if (!coordinateAction) {
          try {
            target = await waitForTarget(page, selector)
          } catch (error) {
            if (event.action === 'hover') {
              result.status = 'passed'
              result.message = 'Hover target was not present after waiting; continued with the next recorded action.'
              replay.results.push(result)
              continue
            }
            throw error
          }
        }
        if (event.action === 'click' || event.action === 'dblclick') {
          const nextEvent = actionEvents[index + 1]
          const mayOpenPage = nextEvent && nextEvent.pageUrl && nextEvent.pageUrl !== event.pageUrl
          const popupPromise = mayOpenPage
            ? context.waitForEvent('page', { timeout: 10000 }).catch(() => null)
            : null
          const modifiers = Object.entries(event.modifiers || {}).filter(([, enabled]) => enabled).map(([key]) => ({ ctrl: 'Control', meta: 'Meta', shift: 'Shift', alt: 'Alt' })[key] || key)
          if (Number.isFinite(event.x) && Number.isFinite(event.y)) {
            await page.mouse.move(event.x, event.y)
            await page.mouse.click(event.x, event.y, { clickCount: event.action === 'dblclick' ? 2 : 1, modifiers })
          } else {
            await target[event.action === 'dblclick' ? 'dblclick' : 'click']({ modifiers })
          }
          const popup = popupPromise ? await popupPromise : null
          if (popup) {
            activePage = popup
            await popup.waitForLoadState('domcontentloaded', { timeout: 30000 }).catch(() => {})
            pages.set(nextEvent.pageUrl, popup)
          } else if (mayOpenPage) {
            await page.waitForLoadState('domcontentloaded', { timeout: 30000 }).catch(() => {})
          }
        }
        if (event.action === 'mousedown') {
          await page.mouse.move(event.x ?? 0, event.y ?? 0)
          await page.mouse.down({ button: event.button === 2 ? 'right' : 'left' })
        }
        if (event.action === 'mouseup') {
          await page.mouse.move(event.x ?? 0, event.y ?? 0)
          await page.mouse.up({ button: event.button === 2 ? 'right' : 'left' })
        }
        if (event.action === 'hover') await target.hover()
        if (event.action === 'focus') await target.focus()
        if (event.action === 'input' || event.action === 'change') {
          const override = data[event.element?.label] || data[event.element?.id] || data[event.element?.testId]
          if (event.element?.tag === 'select') await target.selectOption({ label: substitute(override ?? event.value, data) })
          else await target.fill(substitute(override ?? event.value, data))
        }
        if (event.action === 'keydown') await target.press(substitute(event.key, data))
        if (event.action === 'keyup') await target.press(substitute(event.key, data))
        if (event.action === 'wheel') await page.mouse.wheel(event.deltaX || 0, event.deltaY || 0)
        if (event.action === 'scroll') await page.evaluate(({ x, y }) => window.scrollTo(x, y), { x: event.x || 0, y: event.y || 0 })
        if (event.action === 'submit') await target.evaluate((element) => element.requestSubmit ? element.requestSubmit() : element.submit())
        if (event.action === 'dragstart' || event.action === 'drop') await target.hover()
        const actual = target ? await target.evaluate((element) => ({ value: element.value ?? null, checked: element.checked ?? null, selected: element.selected ?? null, text: (element.textContent || '').trim().slice(0, 120) })) : null
        if (event.element?.value != null && ['input', 'change'].includes(event.action) && actual?.value !== event.element.value && !data[event.element?.label] && !data[event.element?.id] && !data[event.element?.testId]) throw new Error(`Value mismatch: expected ${event.element.value}, got ${actual?.value}`)
        if (!['click', 'dblclick', 'mousedown', 'mouseup', 'hover', 'focus', 'input', 'change', 'keydown', 'keyup', 'wheel', 'scroll', 'submit', 'dragstart', 'drop'].includes(event.action)) throw new Error(`Unsupported recorded action: ${event.action}`)
        }
      } catch (error) {
        result.status = 'failed'
        result.message = error.message
      }
      replay.results.push(result)
    }
    replay.status = replay.results.every((result) => result.status === 'passed') ? 'passed' : 'failed'
    replay.browserOpen = true
  } catch (error) {
    replay.status = 'failed'
    replay.results.push({ index: 0, action: 'browser-start', pageUrl: flow.url, status: 'failed', message: error.message })
  }
  return replay
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`)
  if (req.method === 'OPTIONS') { res.writeHead(204, { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'content-type' }); return res.end() }
  if (req.method === 'GET' && url.pathname === '/') {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
    return res.end(`<!doctype html><html><head><title>UI Automation Controller</title><style>body{font:16px Segoe UI,sans-serif;background:#f4f6fb;color:#101323;padding:48px}main{max-width:680px;margin:auto;background:#fff;border:1px solid #e3e6ef;border-radius:14px;padding:28px;box-shadow:0 8px 24px #10132314}h1{margin-top:0}code{background:#eef0f5;border-radius:5px;padding:3px 6px}li{margin:10px 0}</style></head><body><main><h1>UI Automation Controller</h1><p>The Playwright recording and replay backend is running.</p><ul><li><a href="/health">Health status</a></li><li>Recording API: <code>POST /api/sessions</code></li><li>Replay API: <code>POST /api/flows/{id}/replay</code></li></ul><p>Open the Automation Platform dashboard to use the UI.</p></main></body></html>`)
  }
  if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, { status: 'ok' })
  if (req.method === 'POST' && url.pathname === '/api/sessions') {
    const body = await readBody(req)
    const id = randomUUID()
    const targetUrl = normalizeUrl(body.url)
    const session = { id, flowName: body.flowName || 'UI flow', url: targetUrl, currentUrl: targetUrl, status: 'starting', events: [], script: '', context: null, browser: null, startedAt: new Date().toISOString() }
    sessions.set(id, session)
    ;(async () => {
      try {
        console.log(`[${id}] launching Chromium`)
        session.browser = await chromium.launch({ headless: false, timeout: 15000, executablePath: chromiumExecutable })
        console.log(`[${id}] Chromium launched`)
        session.context = await session.browser.newContext()
        console.log(`[${id}] browser context created`)
        await session.context.exposeBinding('uiAutomationRecord', async ({}, payload) => {
          const event = payload && typeof payload === 'object' ? payload : { type: 'warning', message: 'Invalid recorder event' }
          if (event.type === 'control' && event.action === 'stop') await stopSession(session)
          else if (event.type === 'control' && event.action === 'pause') session.status = 'paused'
          else if (event.type === 'control' && event.action === 'resume') session.status = 'recording'
          else session.events.push(event)
        })
        session.context.addInitScript({ content: recorderScript(id) })
        session.context.on('page', (page) => attachPageTracking(session, page))
        const page = await session.context.newPage()
        if (session.status === 'stopped') {
          await session.context.close()
          await session.browser.close()
          return
        }
        session.status = 'recording'
        session.currentUrl = targetUrl
        console.log(`[${id}] recording page ready`)
        page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch((error) => {
          session.events.push({ type: 'error', message: error.message, pageUrl: targetUrl })
        })
      } catch (error) {
        session.status = 'error'
        session.events.push({ type: 'error', message: error.message })
      }
    })()
    return json(res, 201, { id, status: session.status, flowName: session.flowName })
  }
  const eventMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/events$/)
  if (req.method === 'POST' && eventMatch) {
    const session = sessions.get(eventMatch[1]); if (!session) return json(res, 404, { error: 'Session not found' })
    const event = await readBody(req); if (event.type === 'control' && event.action === 'pause') session.status = 'paused'; if (event.type === 'control' && event.action === 'resume') session.status = 'recording'; if (event.type === 'control' && event.action === 'stop') await stopSession(session); if (event.type !== 'control') session.events.push(event)
    return json(res, 200, { status: session.status })
  }
  const stopMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/stop$/)
  if (req.method === 'POST' && stopMatch) { const session = sessions.get(stopMatch[1]); if (!session) return json(res, 404, { error: 'Session not found' }); await stopSession(session); return json(res, 200, { id: session.id, flowName: session.flowName, status: session.status, eventCount: session.events.length, currentUrl: session.currentUrl, actions: actionSummary(session.events) }) }
  const sessionMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)$/)
  if (req.method === 'GET' && sessionMatch) { const session = sessions.get(sessionMatch[1]); return session ? json(res, 200, { id: session.id, flowName: session.flowName, status: session.status, eventCount: session.events.length, currentUrl: session.currentUrl, actions: actionSummary(session.events) }) : json(res, 404, { error: 'Session not found' }) }
  const replayMatch = url.pathname.match(/^\/api\/flows\/([^/]+)\/replay$/)
  if (req.method === 'POST' && replayMatch) {
    const flow = await loadFlow(replayMatch[1])
    if (!flow) return json(res, 404, { error: 'Flow not found. Stop a recording before replaying it.' })
    const body = await readBody(req)
    const replayId = randomUUID()
    replays.set(replayId, { id: replayId, flowId: flow.id, status: 'running', browser: body.browser || 'chromium', results: [] })
    replayFlow(flow, body.browser || 'chromium', body.data || {}, replayId).catch((error) => {
      const replay = replays.get(replayId)
      if (replay) { replay.status = 'failed'; replay.results.push({ index: 0, action: 'browser-start', pageUrl: flow.url, status: 'failed', message: error.message }) }
    })
    return json(res, 202, { id: replayId, status: 'running', browser: body.browser || 'chromium' })
  }
  const replayStatusMatch = url.pathname.match(/^\/api\/replays\/([^/]+)$/)
  if (req.method === 'GET' && replayStatusMatch) {
    const replay = replays.get(replayStatusMatch[1])
    return replay ? json(res, 200, replayView(replay)) : json(res, 404, { error: 'Replay not found' })
  }
  const replayCloseMatch = url.pathname.match(/^\/api\/replays\/([^/]+)\/close$/)
  if (req.method === 'POST' && replayCloseMatch) {
    const replay = replays.get(replayCloseMatch[1])
    if (!replay) return json(res, 404, { error: 'Replay not found' })
    await replay.browserProcess?.close()
    replay.browserProcess = null
    replay.browserOpen = false
    return json(res, 200, { id: replay.id, status: replay.status, browserOpen: false })
  }
  json(res, 404, { error: 'Not found' })
})

server.listen(port, '127.0.0.1', () => console.log(`UI Automation Playwright controller listening on http://127.0.0.1:${port}`))
