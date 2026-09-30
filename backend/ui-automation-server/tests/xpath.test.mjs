import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import fs from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { recorderScript, xpathEngineScript } from '../recorder.mjs'

const serverDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const controllerPort = 18004
const controller = `http://127.0.0.1:${controllerPort}`

// "record" is the page the flow is captured on; "replay" is the same app after a release:
// extra wrappers, regenerated ids and hashes, a late-rendering button and lazily loaded content.
function fixturePage(variant) {
  const replay = variant === 'replay'
  const dynamicId = replay ? 'input-9d81e0aa' : 'input-3f9a2c7b'
  const reactId = replay ? ':r9:' : ':r5:'
  const hashed = replay ? 'index_header__Q1W2E' : 'index_header__H8GJD'
  const rows = ['Order A', 'Order B', 'Order C', ...(replay ? ['Order D'] : [])]
  const open = replay ? '<div class="shell"><div><section>' : ''
  const close = replay ? '</section></div></div>' : ''
  return `<!doctype html><html><head><title>QA fixture</title>
<style>body{font-family:sans-serif} .spacer{height:${replay ? 3200 : 2000}px}</style></head><body>
<header class="app-header ${hashed}"><h1>Orders</h1><button type="button" aria-label="Toggle theme"><svg width="16" height="16"><path d="M0 0h16v16H0z"></path></svg></button></header>
${open}
<main id="main">
  <form id="order-form">
    <label>Email <input id="${dynamicId}" name="email" type="email"></label>
    <input id="${reactId}" placeholder="Quantity" type="text">
    <select name="plan"><option value="basic">Basic</option><option value="pro">Pro plan</option></select>
    <label><input type="checkbox" name="terms"> I accept the "terms" & don't mind</label>
    <div class="notes-section"><h2>Notes</h2><textarea></textarea></div>
    <input type="hidden" name="confirmed" value="no">
    <div class="actions">${replay ? '' : '<button type="submit" class="submit-btn">Place order</button>'}</div>
  </form>
  <table id="orders"><tbody>
    ${rows.map((row) => `<tr><td>${row}</td><td><button type="button" class="delete"><svg width="10" height="10"><path d="M0 0h10v10H0z"></path></svg> Delete</button></td></tr>`).join('')}
  </tbody></table>
  <div class="spacer"></div>
  <div id="lazy-zone"></div>
</main>
${close}
<p id="status"></p>
<script>
  const form = document.getElementById('order-form');
  document.getElementById('orders').addEventListener('click', (event) => {
    const button = event.target.closest('button.delete');
    if (button) button.closest('tr').remove();
  });
  let lazyLoaded = false;
  const loadLazy = () => {
    if (lazyLoaded || window.scrollY + window.innerHeight < document.body.scrollHeight - 150) return;
    lazyLoaded = true;
    const confirm = document.createElement('button');
    confirm.type = 'button';
    confirm.className = 'confirm-btn';
    confirm.textContent = 'Confirm order';
    confirm.addEventListener('click', () => { form.elements.confirmed.value = 'yes'; confirm.textContent = 'Confirmed'; });
    document.getElementById('lazy-zone').appendChild(confirm);
  };
  window.addEventListener('scroll', loadLazy);
  ${replay ? `setTimeout(() => { const submit = document.createElement('button'); submit.type = 'submit'; submit.className = 'submit-btn'; submit.textContent = 'Place order'; form.querySelector('.actions').appendChild(submit); }, 1500);` : ''}
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const payload = {
      email: form.elements.email.value,
      quantity: form.querySelector('input[placeholder="Quantity"]').value,
      plan: form.elements.plan.value,
      terms: form.elements.terms.checked,
      note: form.querySelector('textarea').value,
      confirmed: form.elements.confirmed.value,
      remaining: [...document.querySelectorAll('#orders td:first-child')].map((cell) => cell.textContent),
    };
    fetch('/submit', { method: 'POST', body: JSON.stringify(payload) }).then(() => { document.getElementById('status').textContent = 'Submitted'; });
  });
</script></body></html>`
}

let fixtureServer
let fixtureUrl
let submissions = []
let browser
let dataDirectory
let controllerProcess
let controllerLog = ''

async function startFixtureServer() {
  fixtureServer = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/submit') {
      let body = ''
      req.on('data', (chunk) => { body += chunk })
      req.on('end', () => { submissions.push(JSON.parse(body)); res.end('ok') })
      return
    }
    const variant = new URL(req.url, 'http://localhost').searchParams.get('v') || 'record'
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
    res.end(fixturePage(variant))
  })
  await new Promise((resolve) => fixtureServer.listen(0, '127.0.0.1', resolve))
  fixtureUrl = `http://127.0.0.1:${fixtureServer.address().port}/`
}

async function startController() {
  controllerProcess = spawn(process.execPath, ['server.mjs'], {
    cwd: serverDirectory,
    env: { ...process.env, UI_AUTOMATION_PORT: String(controllerPort), UI_AUTOMATION_DATA_DIR: dataDirectory, UI_AUTOMATION_HEADLESS: 'true', UI_AUTOMATION_ELEMENT_TIMEOUT_MS: '10000' },
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
}

async function api(pathname, init) {
  const response = await fetch(`${controller}${pathname}`, { headers: { 'content-type': 'application/json' }, ...init })
  assert.ok(response.ok, `${pathname} returned ${response.status}`)
  return response.json()
}

async function runReplay(flowId, data = {}) {
  const started = await api(`/api/flows/${flowId}/replay`, { method: 'POST', body: JSON.stringify({ browser: 'chromium', data }) })
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const replay = await api(`/api/replays/${started.id}`)
    if (replay.status !== 'running') {
      await api(`/api/replays/${started.id}/close`, { method: 'POST' })
      return replay
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error('Replay did not finish')
}

const failures = (replay) => replay.results.filter((result) => result.status === 'failed').map((result) => `${result.index}. ${result.action}: ${result.message}`)
const isRelative = (xpath) => /^\(?\/\//.test(xpath) && !/^\(?\/\/html\//.test(xpath)

before(async () => {
  await startFixtureServer()
  dataDirectory = await fs.mkdtemp(path.join(os.tmpdir(), 'ui-automation-qa-'))
  browser = await chromium.launch({ headless: true })
  await startController()
})

after(async () => {
  await browser?.close()
  controllerProcess?.kill()
  await new Promise((resolve) => fixtureServer?.close(resolve))
  await fs.rm(dataDirectory, { recursive: true, force: true })
})

test('every element on the page gets a unique relative XPath', async () => {
  for (const variant of ['record', 'replay']) {
    const page = await browser.newPage()
    await page.goto(`${fixtureUrl}?v=${variant}`)
    await page.addScriptTag({ content: xpathEngineScript })
    const report = await page.evaluate(() => {
      const engine = window.__uiAutomationXPath
      return [...document.querySelectorAll('*')].map((element) => {
        const candidates = engine.candidates(element)
        const resolves = candidates.map((xpath) => engine.matchesOnly(xpath, element))
        return { tag: element.localName, candidates, resolves }
      })
    })
    await page.close()
    for (const item of report) {
      assert.ok(item.candidates.length > 0, `${variant}: no XPath for <${item.tag}>`)
      item.candidates.forEach((xpath, index) => {
        assert.ok(isRelative(xpath), `${variant}: XPath is not relative: ${xpath}`)
        assert.ok(item.resolves[index], `${variant}: XPath does not uniquely match its <${item.tag}>: ${xpath}`)
      })
    }
  }
})

test('XPaths avoid generated ids and hashed classes, and handle quotes', async () => {
  const page = await browser.newPage()
  await page.goto(`${fixtureUrl}?v=record`)
  await page.addScriptTag({ content: xpathEngineScript })
  const xpaths = await page.evaluate(() => {
    const engine = window.__uiAutomationXPath
    const best = (selector) => engine.candidates(document.querySelector(selector))
    return {
      email: best('input[name="email"]'),
      quantity: best('input[placeholder="Quantity"]'),
      header: best('header'),
      terms: best('input[name="terms"]'),
      termsLabel: best('label:nth-of-type(2)'),
      svgInButton: engine.describe(engine.actionable(document.querySelector('header svg path'))).xpath,
    }
  })
  await page.close()
  assert.equal(xpaths.email[0], "//input[@name='email']")
  assert.ok(xpaths.email.every((xpath) => !xpath.includes('3f9a2c7b')), 'uses generated id')
  assert.equal(xpaths.quantity[0], "//input[@placeholder='Quantity']")
  assert.ok(xpaths.quantity.every((xpath) => !xpath.includes(':r5:')), 'uses React useId')
  assert.ok(xpaths.header.every((xpath) => !xpath.includes('H8GJD')), 'uses hashed CSS-module class')
  assert.equal(xpaths.svgInButton, "//button[@aria-label='Toggle theme']", 'click on an icon should target its button')
  assert.ok(xpaths.termsLabel.some((xpath) => xpath.includes('concat(')), 'text with both quote kinds should use concat()')
})

test('recorder stores relative XPaths for user actions and ignores its own toolbar', async () => {
  const events = await recordFlow()
  const actions = events.filter((event) => event.type === 'action')
  const interesting = actions.filter((event) => ['click', 'input', 'change'].includes(event.action))
  assert.ok(interesting.length >= 7, `expected clicks and inputs, got ${interesting.map((event) => event.action).join(',')}`)
  for (const event of actions) {
    assert.ok(event.element?.xpath, `${event.action} has no XPath`)
    assert.ok(isRelative(event.element.xpath), `${event.action} XPath not relative: ${event.element.xpath}`)
    assert.equal(event.element.selector, event.element.xpath)
  }
  assert.ok(actions.every((event) => !event.element.xpath.includes('__ui-automation-toolbar')), 'toolbar interactions were recorded')
  const deleteClick = actions.find((event) => event.action === 'click' && event.element.text === 'Delete')
  assert.ok(deleteClick, 'click on the delete icon should be recorded against its button')
  assert.equal(deleteClick.element.tag, 'button')
})

async function recordFlow() {
  const context = await browser.newContext()
  const events = []
  await context.exposeBinding('uiAutomationRecord', (_source, payload) => { events.push(payload) })
  await context.addInitScript({ content: recorderScript('qa', controllerPort) })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(`${fixtureUrl}?v=record`)
  await page.fill('input[name="email"]', 'qa@example.com')
  await page.locator('input[placeholder="Quantity"]').pressSequentially('12')
  await page.selectOption('select[name="plan"]', 'pro')
  await page.check('input[name="terms"]')
  await page.fill('textarea', 'Leave at the door')
  await page.locator('#orders tr:nth-child(2) button.delete svg').click()
  await page.locator('#__ui-automation-toolbar [data-action="pause"]').click()
  await page.locator('#__ui-automation-toolbar [data-action="resume"]').click()
  await page.mouse.wheel(0, 5000)
  await page.locator('.confirm-btn').click()
  await page.locator('.submit-btn').click()
  await page.waitForFunction(() => document.getElementById('status').textContent === 'Submitted')
  await context.close()
  assert.deepEqual(errors, [], `page errors while recording: ${errors.join('; ')}`)
  return events
}

test('a live recording session injects the recorder without script errors', async () => {
  const session = await api('/api/sessions', { method: 'POST', body: JSON.stringify({ url: `${fixtureUrl}?v=record`, flowName: 'QA live session' }) })
  let status
  // Chromium can take over 10s to launch on machines with endpoint scanning.
  for (let attempt = 0; attempt < 120; attempt += 1) {
    status = await api(`/api/sessions/${session.id}`)
    if (status.status === 'recording' && status.eventCount > 0) break
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  await api(`/api/sessions/${session.id}/stop`, { method: 'POST' })
  assert.equal(status.status, 'recording')
  assert.ok(status.eventCount > 0, 'the injected recorder sent nothing - it failed to run in the page')
})

test('replay locates every element by relative XPath on a changed page', async () => {
  submissions = []
  const events = await recordFlow()
  submissions = []
  const flowId = 'qa-relative-xpath'
  await fs.writeFile(path.join(dataDirectory, `${flowId}.json`), JSON.stringify({ id: flowId, flowName: 'QA relative XPath', url: `${fixtureUrl}?v=replay`, events }, null, 2))

  const replay = await runReplay(flowId)
  assert.deepEqual(failures(replay), [], 'replay had failing steps')
  assert.equal(replay.status, 'passed')
  assert.equal(submissions.length, 1, 'the order form should be submitted exactly once')
  assert.deepEqual(submissions[0], {
    email: 'qa@example.com',
    quantity: '12',
    plan: 'pro',
    terms: true,
    note: 'Leave at the door',
    confirmed: 'yes',
    remaining: ['Order A', 'Order C', 'Order D'],
  })
  const located = replay.results.filter((result) => result.locator)
  assert.ok(located.length > 0 && located.every((result) => isRelative(result.locator)), 'steps should be located by relative XPath')
})

test('test data overrides recorded values', async () => {
  submissions = []
  const events = await recordFlow()
  submissions = []
  const flowId = 'qa-test-data'
  await fs.writeFile(path.join(dataDirectory, `${flowId}.json`), JSON.stringify({ id: flowId, flowName: 'QA data', url: `${fixtureUrl}?v=replay`, events }, null, 2))
  const replay = await runReplay(flowId, { email: 'override@example.com' })
  assert.deepEqual(failures(replay), [])
  assert.equal(submissions[0]?.email, 'override@example.com')
})

test('flows recorded with the old CSS selectors still replay and gain relative XPaths', async () => {
  submissions = []
  const flowId = 'qa-legacy-css'
  const legacyEvents = [
    { type: 'action', action: 'input', value: 'legacy@example.com', pageUrl: `${fixtureUrl}?v=record`, element: { selector: 'form > label:nth-of-type(1) > input', tag: 'input', id: 'input-3f9a2c7b', text: '', value: 'legacy@example.com' } },
    { type: 'action', action: 'click', x: 5, y: 5, pageUrl: `${fixtureUrl}?v=record`, element: { selector: 'table#orders > tbody > tr:nth-of-type(1) > td:nth-of-type(2) > button', tag: 'button', text: 'Delete' } },
    { type: 'action', action: 'click', x: 5, y: 5, pageUrl: `${fixtureUrl}?v=record`, element: { selector: 'div.actions > button', tag: 'button', text: 'Place order' } },
  ]
  await fs.writeFile(path.join(dataDirectory, `${flowId}.json`), JSON.stringify({ id: flowId, flowName: 'QA legacy', url: `${fixtureUrl}?v=replay`, events: legacyEvents }, null, 2))

  const replay = await runReplay(flowId)
  assert.deepEqual(failures(replay), [])
  assert.equal(submissions[0]?.email, 'legacy@example.com')
  assert.deepEqual(submissions[0]?.remaining, ['Order B', 'Order C', 'Order D'])
  assert.equal(replay.healedSteps, 3)
  const stored = JSON.parse(await fs.readFile(path.join(dataDirectory, `${flowId}.json`), 'utf8'))
  for (const event of stored.events) {
    assert.ok(isRelative(event.element.xpath), `legacy step was not upgraded: ${event.element.xpath}`)
    assert.ok(event.element.xpathCandidates.length >= 1)
  }
  assert.equal(stored.events[0].element.xpath, "//input[@name='email']")
})

test('an element that only loads after scrolling is found by scrolling', async () => {
  submissions = []
  const flowId = 'qa-lazy'
  const pageUrl = `${fixtureUrl}?v=replay`
  const events = [
    { type: 'action', action: 'click', pageUrl, element: { xpath: "//button[contains(concat(' ', normalize-space(@class), ' '), ' confirm-btn ')]", xpathCandidates: [], selector: '', tag: 'button', text: 'Confirm order' } },
    { type: 'action', action: 'click', pageUrl, element: { xpath: "//button[@type='submit']", xpathCandidates: [], selector: '', tag: 'button', text: 'Place order' } },
  ]
  await fs.writeFile(path.join(dataDirectory, `${flowId}.json`), JSON.stringify({ id: flowId, flowName: 'QA lazy', url: pageUrl, events }, null, 2))
  const replay = await runReplay(flowId)
  assert.deepEqual(failures(replay), [])
  assert.equal(submissions[0]?.confirmed, 'yes')
})

test('a missing element fails with a clear message after waiting', async () => {
  const flowId = 'qa-missing'
  const events = [{ type: 'action', action: 'click', pageUrl: `${fixtureUrl}?v=replay`, element: { xpath: "//button[normalize-space()='Does not exist']", xpathCandidates: [], selector: "//button[normalize-space()='Does not exist']", tag: 'button' } }]
  await fs.writeFile(path.join(dataDirectory, `${flowId}.json`), JSON.stringify({ id: flowId, flowName: 'QA missing', url: `${fixtureUrl}?v=replay`, events }, null, 2))
  const started = Date.now()
  const replay = await runReplay(flowId)
  assert.equal(replay.status, 'failed')
  const failed = replay.results.find((result) => result.status === 'failed')
  assert.equal(failed?.action, 'click')
  assert.match(failed.message, /not found after waiting 10s and scrolling/)
  assert.ok(Date.now() - started >= 9000, 'should wait before giving up')
})
