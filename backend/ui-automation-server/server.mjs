import http from 'node:http'
import { randomUUID } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, firefox, webkit } from 'playwright'
import { xpathEngineScript } from './recorder.mjs'
import { attachRecorder, createSession, handleControl } from './recording.mjs'
import { buildRepository, describeRawStep, functionalSteps, isSlug, pageIdentity, slugify } from './repository.mjs'
import { executeFlow, normalizeUrl } from './executor.mjs'

const port = Number(process.env.UI_AUTOMATION_PORT || 8004)
const headless = process.env.UI_AUTOMATION_HEADLESS === 'true'
const elementTimeoutMs = Number(process.env.UI_AUTOMATION_ELEMENT_TIMEOUT_MS || 15000)
const optionalElementTimeoutMs = Number(process.env.UI_AUTOMATION_OPTIONAL_ELEMENT_TIMEOUT_MS || 3000)
const sessions = new Map()
const flows = new Map()
const replays = new Map()
const dataDirectory = path.resolve(process.env.UI_AUTOMATION_DATA_DIR || path.join(path.dirname(fileURLToPath(import.meta.url)), 'data'))
const chromiumExecutable = process.env.UI_AUTOMATION_CHROMIUM_PATH || chromium.executablePath()

await fs.mkdir(dataDirectory, { recursive: true })

const flowFile = (id) => path.join(dataDirectory, `${id}.json`)
const testsDirectory = path.join(dataDirectory, 'tests')
const pagesDirectory = path.join(dataDirectory, 'pages')
const testFile = (slug) => path.join(testsDirectory, slug, 'test.json')
const reservedSlugs = new Set()

function repositoryPath(relative) {
  const full = path.resolve(dataDirectory, relative)
  if (!full.startsWith(dataDirectory + path.sep)) throw new Error(`Invalid repository path: ${relative}`)
  return full
}

async function readJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'))
  } catch {
    return null
  }
}

async function writeJson(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true })
  await fs.writeFile(file, JSON.stringify(value, null, 2))
}

// Page files are shared between tests, so repository writes run one at a time.
let repositoryQueue = Promise.resolve()
const queueRepository = (task) => {
  const run = repositoryQueue.then(task)
  repositoryQueue = run.catch((error) => console.error(`[repository] ${error.message}`))
  return run
}

async function allocateTestSlug(name) {
  const base = slugify(name, 'test')
  for (let suffix = 1; ; suffix += 1) {
    const slug = suffix === 1 ? base : `${base}-${suffix}`
    if (reservedSlugs.has(slug)) continue
    if (await fs.access(path.join(testsDirectory, slug)).then(() => true, () => false)) continue
    reservedSlugs.add(slug)
    return slug
  }
}

function writeRepository(flow) {
  if (!flow.testSlug) return Promise.resolve(null)
  return queueRepository(async () => {
    const previous = await readJson(testFile(flow.testSlug))
    const files = new Set(Object.values(previous?.pages || {}).map((page) => page.file))
    for (const event of flow.events || []) if (event.type === 'action' && event.element?.xpath) files.add(pageIdentity(event.pageUrl).file)
    const loaded = new Map()
    for (const file of files) loaded.set(file, await readJson(repositoryPath(file)))
    const { test, pages } = buildRepository(flow, (file) => loaded.get(file) ?? null, previous)
    for (const [file, page] of pages) {
      if (!Object.keys(page.elements).length && !Object.keys(page.components).length) await fs.rm(repositoryPath(file), { force: true })
      else await writeJson(repositoryPath(file), page)
    }
    await writeJson(testFile(flow.testSlug), test)
    return test
  })
}

function recordRun(flow, replay) {
  if (!flow.testSlug) return Promise.resolve()
  return queueRepository(async () => {
    const test = await readJson(testFile(flow.testSlug))
    if (!test) return
    const run = { id: replay.id, status: replay.status, browser: replay.browser, at: new Date().toISOString(), passed: replay.results.filter((result) => result.status === 'passed').length, failed: replay.results.filter((result) => result.status === 'failed').length, healedSteps: replay.healedSteps ?? 0 }
    test.lastRun = run
    test.history = [run, ...(test.history || [])].slice(0, 20)
    await writeJson(testFile(flow.testSlug), test)
  })
}

async function listTests() {
  const entries = await fs.readdir(testsDirectory, { withFileTypes: true }).catch(() => [])
  const tests = []
  for (const entry of entries) {
    if (!entry.isDirectory() || !isSlug(entry.name)) continue
    const test = await readJson(testFile(entry.name))
    if (!test) continue
    const pages = Object.values(test.pages || {})
    const elementCount = pages.reduce((total, page) => total + Object.keys(page.elements || {}).length + Object.values(page.components || {}).reduce((sum, component) => sum + Object.keys(component.elements || {}).length, 0), 0)
    tests.push({ slug: test.slug, name: test.name, url: test.url, flowId: test.flowId, createdAt: test.createdAt, updatedAt: test.updatedAt, lastRun: test.lastRun, stepCount: (test.flow || []).length, pageCount: pages.length, elementCount })
  }
  return tests.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
}

async function listPages() {
  const hosts = await fs.readdir(pagesDirectory, { withFileTypes: true }).catch(() => [])
  const pages = []
  for (const host of hosts.filter((entry) => entry.isDirectory())) {
    for (const name of await fs.readdir(path.join(pagesDirectory, host.name)).catch(() => [])) {
      if (!name.endsWith('.json')) continue
      const page = await readJson(path.join(pagesDirectory, host.name, name))
      if (page) pages.push({ file: `pages/${host.name}/${name}`, ...page })
    }
  }
  return pages.sort((a, b) => `${a.host}${a.path}`.localeCompare(`${b.host}${b.path}`))
}

async function saveFlow(flow) {
  await fs.writeFile(flowFile(flow.id), JSON.stringify(flow, null, 2))
  flows.set(flow.id, flow)
  await writeRepository(flow).catch(() => {})
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

function json(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json', 'access-control-allow-origin': '*' })
  res.end(JSON.stringify(body))
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = ''
    req.on('data', (chunk) => { data += chunk })
    req.on('end', () => {
      try {
        resolve(data ? JSON.parse(data) : {})
      } catch {
        resolve({})
      }
    })
  })
}

function scriptFor(session) {
  const lines = [`import { test, expect } from '@playwright/test`, '', `test.use({ storageState: './data/${session.id}.storage.json' })`, '', `test('${session.flowName.replace(/'/g, "\\'")}', async ({ page }) => {`, `  await page.goto(${JSON.stringify(session.url)})`]
  for (const event of session.events.filter((item) => item.type === 'action')) {
    const xpath = event.element?.xpath || (event.element?.selector?.startsWith('/') ? event.element.selector : '')
    const locator = xpath ? `page.locator(${JSON.stringify(`xpath=${xpath}`)})` : `page.locator(${JSON.stringify(event.element?.selector || event.element?.tag || 'body')})`
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
  await Promise.allSettled([...(session.pending || [])])
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
  await saveFlow({ id: session.id, flowName: session.flowName, testSlug: session.testSlug, createdAt: session.startedAt, url: session.url, events: session.events, script: session.script, storageState: session.storageState })
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

function actionSummary(session) {
  return functionalSteps({ url: session.url, events: session.events }).map((step) => ({
    action: step.action,
    pageUrl: step.url,
    tab: step.tab ?? undefined,
    text: describeRawStep(step),
    xpath: step.source?.element?.xpath || '',
  }))
}

function sessionView(session) {
  return { id: session.id, flowName: session.flowName, testSlug: session.testSlug, status: session.status, eventCount: session.events.length, currentUrl: session.currentUrl, dialogPolicy: session.dialogPolicy, openTabs: [...session.tabs.values()].filter((tab) => !tab.closed).length, actions: actionSummary(session) }
}


function replayView(replay) {
  return { id: replay.id, flowId: replay.flowId, testSlug: replay.testSlug, status: replay.status, browser: replay.browser, results: replay.results, browserOpen: replay.browserOpen ?? false, healedSteps: replay.healedSteps ?? 0 }
}

async function replayFlow(flow, browserName, data, replayId) {
  const replay = replays.get(replayId) || { id: replayId, flowId: flow.id, status: 'running', browser: browserName, results: [], browserProcess: null }
  replays.set(replayId, replay)
  const browserType = browserFor(browserName)
  try {
    const browser = await browserType.launch({ headless })
    replay.browserProcess = browser
    const context = await browser.newContext(flow.storageState ? { storageState: flow.storageState } : {})
    await context.addInitScript({ content: xpathEngineScript })
    const { healedSteps } = await executeFlow(context, flow, data, replay, { element: elementTimeoutMs, optional: optionalElementTimeoutMs })
    if (healedSteps) await saveFlow(flow)
    replay.healedSteps = healedSteps
    replay.status = replay.results.every((result) => result.status === 'passed') ? 'passed' : 'failed'
    replay.browserOpen = true
  } catch (error) {
    replay.status = 'failed'
    replay.results.push({ index: 0, action: 'browser-start', pageUrl: flow.url, status: 'failed', message: error.message })
  }
  await recordRun(flow, replay).catch(() => {})
  return replay
}

async function startReplay(flow, body) {
  const browser = ['chromium', 'firefox', 'webkit'].includes(body.browser) ? body.browser : 'chromium'
  const data = body.data && typeof body.data === 'object' ? body.data : {}
  const replayId = randomUUID()
  replays.set(replayId, { id: replayId, flowId: flow.id, testSlug: flow.testSlug, status: 'running', browser, results: [] })
  replayFlow(flow, browser, data, replayId).catch((error) => {
    const replay = replays.get(replayId)
    if (replay) { replay.status = 'failed'; replay.results.push({ index: 0, action: 'browser-start', pageUrl: flow.url, status: 'failed', message: error.message }) }
  })
  return { id: replayId, status: 'running', browser }
}

const server = http.createServer((req, res) => {
  route(req, res).catch((error) => {
    console.error(error)
    if (!res.headersSent) json(res, 500, { error: error.message })
    else res.end()
  })
})

async function route(req, res) {
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
    const flowName = String(body.flowName || 'UI flow').trim().slice(0, 120) || 'UI flow'
    const testSlug = await allocateTestSlug(flowName)
    const session = createSession({ id, flowName, testSlug, url: targetUrl })
    sessions.set(id, session)
    ;(async () => {
      try {
        console.log(`[${id}] launching Chromium`)
        session.browser = await chromium.launch({ headless, timeout: 15000, executablePath: chromiumExecutable })
        console.log(`[${id}] Chromium launched`)
        await attachRecorder(session, await session.browser.newContext(), { port, stop: stopSession })
        console.log(`[${id}] browser context created`)
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
    return json(res, 201, { id, status: session.status, flowName: session.flowName, testSlug })
  }
  const eventMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/events$/)
  if (req.method === 'POST' && eventMatch) {
    const session = sessions.get(eventMatch[1])
    if (!session) return json(res, 404, { error: 'Session not found' })
    const event = await readBody(req)
    if (event.type === 'control') await handleControl(session, event, stopSession)
    else if (session.status === 'recording' || event.type !== 'action') session.events.push(event)
    return json(res, 200, { status: session.status })
  }
  const stopMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/stop$/)
  if (req.method === 'POST' && stopMatch) {
    const session = sessions.get(stopMatch[1])
    if (!session) return json(res, 404, { error: 'Session not found' })
    await stopSession(session)
    return json(res, 200, sessionView(session))
  }
  const sessionMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)$/)
  if (req.method === 'GET' && sessionMatch) {
    const session = sessions.get(sessionMatch[1])
    return session ? json(res, 200, sessionView(session)) : json(res, 404, { error: 'Session not found' })
  }
  const replayMatch = url.pathname.match(/^\/api\/flows\/([^/]+)\/replay$/)
  if (req.method === 'POST' && replayMatch) {
    const flow = await loadFlow(replayMatch[1])
    if (!flow) return json(res, 404, { error: 'Flow not found. Stop a recording before replaying it.' })
    return json(res, 202, await startReplay(flow, await readBody(req)))
  }
  if (req.method === 'GET' && url.pathname === '/api/tests') return json(res, 200, await listTests())
  if (req.method === 'GET' && url.pathname === '/api/pages') return json(res, 200, await listPages())
  const testMatch = url.pathname.match(/^\/api\/tests\/([^/]+)(\/replay)?$/)
  if (testMatch) {
    if (!isSlug(testMatch[1])) return json(res, 400, { error: 'Invalid test name' })
    const test = await readJson(testFile(testMatch[1]))
    if (!test) return json(res, 404, { error: 'Test not found' })
    if (req.method === 'GET' && !testMatch[2]) return json(res, 200, test)
    if (req.method === 'POST' && testMatch[2]) {
      const flow = await loadFlow(test.flowId)
      if (!flow) return json(res, 404, { error: 'The recording for this test is missing.' })
      return json(res, 202, await startReplay(flow, await readBody(req)))
    }
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
}

server.listen(port, '127.0.0.1', () => console.log(`UI Automation Playwright controller listening on http://127.0.0.1:${port}`))
