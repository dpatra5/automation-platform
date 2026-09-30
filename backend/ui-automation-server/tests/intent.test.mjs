import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import fs from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { attachRecorder, createSession } from '../recording.mjs'
import { functionalSteps } from '../repository.mjs'

const serverDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const controllerPort = 18006
const controller = `http://127.0.0.1:${controllerPort}`

// A sticky header with a hover mega-menu over a long page, like most content sites.
const layout = (title, body) => `<!doctype html><html><head><title>${title}</title><style>
  header{position:sticky;top:0;z-index:10;background:#fff;height:60px;border-bottom:1px solid #ccc}
  .menu{display:inline-block;position:relative;padding:20px}
  .dropdown{display:none;position:absolute;top:50px;left:0;background:#eee;width:600px;height:400px}
  .menu:hover .dropdown{display:block}
  .spacer{height:1800px}
</style></head><body><header><div class="menu"><span class="trigger">Tutorials</span><div class="dropdown"><a href="/python">Python</a></div></div></header>${body}</body></html>`

const pages = {
  '/': layout('Home', '<main><h1>Welcome</h1><div class="spacer"></div><button id="more" type="button">Load more</button><p id="more-status"></p></main><script>document.getElementById("more").onclick=()=>{document.getElementById("more-status").textContent="Loaded"}</script>'),
  '/python': layout('Python', '<main><h1>Python Tutorial</h1><a href="/python/next">Next lesson</a></main>'),
  '/python/next': layout('Next', '<main><h1>Variables</h1></main>'),
}

let fixtureServer
let fixtureUrl
let browser
let dataDirectory
let controllerProcess
let controllerLog = ''

before(async () => {
  fixtureServer = http.createServer((req, res) => {
    const html = pages[new URL(req.url, 'http://localhost').pathname]
    res.writeHead(html ? 200 : 404, { 'content-type': 'text/html; charset=utf-8' })
    res.end(html || 'not found')
  })
  await new Promise((resolve) => fixtureServer.listen(0, '127.0.0.1', resolve))
  fixtureUrl = `http://127.0.0.1:${fixtureServer.address().port}`
  dataDirectory = await fs.mkdtemp(path.join(os.tmpdir(), 'ui-automation-intent-'))
  browser = await chromium.launch({ headless: true })
  controllerProcess = spawn(process.execPath, ['server.mjs'], {
    cwd: serverDirectory,
    env: { ...process.env, UI_AUTOMATION_PORT: String(controllerPort), UI_AUTOMATION_DATA_DIR: dataDirectory, UI_AUTOMATION_HEADLESS: 'true', UI_AUTOMATION_ELEMENT_TIMEOUT_MS: '8000' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  controllerProcess.stdout.on('data', (chunk) => { controllerLog += chunk })
  controllerProcess.stderr.on('data', (chunk) => { controllerLog += chunk })
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      if ((await fetch(`${controller}/health`)).ok) return
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`Controller did not start:\n${controllerLog}`)
})

after(async () => {
  await browser?.close()
  controllerProcess?.kill()
  await new Promise((resolve) => fixtureServer?.close(resolve))
  await fs.rm(dataDirectory, { recursive: true, force: true })
})

async function api(pathname, init) {
  const response = await fetch(`${controller}${pathname}`, { headers: { 'content-type': 'application/json' }, ...init })
  assert.ok(response.ok, `${pathname} returned ${response.status}`)
  return response.json()
}

async function replay(flow) {
  await fs.writeFile(path.join(dataDirectory, `${flow.id}.json`), JSON.stringify(flow, null, 2))
  const started = await api(`/api/flows/${flow.id}/replay`, { method: 'POST', body: JSON.stringify({ browser: 'chromium' }) })
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const result = await api(`/api/replays/${started.id}`)
    if (result.status !== 'running') {
      await api(`/api/replays/${started.id}/close`, { method: 'POST' })
      return result
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error('Replay did not finish')
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

let recorded
async function recordJourney() {
  if (recorded) return structuredClone(recorded)
  const session = createSession({ id: 'qa-intent', flowName: 'QA intent', testSlug: 'qa-intent', url: `${fixtureUrl}/` })
  const context = await browser.newContext()
  await attachRecorder(session, context, { port: controllerPort, stop: async () => {} })
  const page = await context.newPage()
  session.status = 'recording'
  await page.goto(session.url)
  // Wander around like a real user: these moves and scrolls must not become steps.
  await page.mouse.move(300, 300)
  await page.mouse.wheel(0, 1500)
  await page.click('#more')
  await page.mouse.wheel(0, -1500)
  await page.hover('.trigger')
  await pause(400)
  await Promise.all([page.waitForURL('**/python'), page.click('text=Python')])
  await Promise.all([page.waitForURL('**/python/next'), page.click('text=Next lesson')])
  await pause(1700)
  await page.goBack()
  await pause(1700)
  await page.goForward()
  await page.locator('#__ui-automation-toolbar [data-action="verify"]').click()
  await page.click('h1')
  await pause(1700)
  await page.reload()
  await pause(500)
  session.status = 'stopped'
  await context.close()
  recorded = { id: 'qa-intent', flowName: session.flowName, url: session.url, events: session.events }
  return structuredClone(recorded)
}

test('the flow keeps what the user did, not how the mouse moved', async () => {
  const flow = await recordJourney()
  const steps = functionalSteps(flow).map((step) => step.action)
  assert.deepEqual(steps, ['open', 'click', 'click', 'navigate', 'click', 'navigate', 'back', 'forward', 'assert', 'reload'], steps.join(','))
  assert.ok(!flow.events.some((event) => ['hover', 'scroll', 'wheel', 'mousedown', 'mouseup', 'focus', 'keyup'].includes(event.action)), 'noise events were recorded')
  const python = functionalSteps(flow).find((step) => step.source?.element?.displayName === 'Python')
  assert.equal(python.reveal?.[0]?.displayName, 'Tutorials', 'the click inside the hover menu should remember the menu trigger')
  const check = functionalSteps(flow).find((step) => step.action === 'assert')
  assert.equal(check.expectedText, 'Variables')
})

test('execution reveals hover menus, scrolls to elements, goes back/forward, reloads and validates', async () => {
  const flow = await recordJourney()
  const result = await replay(flow)
  const failed = result.results.filter((step) => step.status !== 'passed').map((step) => `${step.index}. ${step.action}: ${step.message}`)
  assert.deepEqual(failed, [], `${failed.join('\n')}\n${controllerLog}`)
  assert.equal(result.status, 'passed')
  assert.deepEqual(result.results.map((step) => step.action), ['open', 'click', 'click', 'navigate', 'click', 'navigate', 'back', 'forward', 'assert', 'reload'])
  const back = result.results.find((step) => step.action === 'back')
  assert.match(back.message, /\/python\b/)
  const assertion = result.results.find((step) => step.action === 'assert')
  assert.match(assertion.message, /Text contains "Variables"/)
  assert.ok(result.results.every((step) => step.description), 'each result should describe the step')
})

test('a failed validation stops the test and skips the remaining steps', async () => {
  const flow = await recordJourney()
  flow.id = 'qa-intent-fail'
  flow.events.find((event) => event.action === 'assert').expectedText = 'Functions'
  const result = await replay(flow)
  assert.equal(result.status, 'failed')
  const failed = result.results.find((step) => step.status === 'failed')
  assert.equal(failed.action, 'assert')
  assert.match(failed.message, /Text check failed: expected "Functions", found "Variables"/)
  assert.deepEqual(result.results.slice(result.results.indexOf(failed) + 1).map((step) => step.status), ['skipped'])
})
