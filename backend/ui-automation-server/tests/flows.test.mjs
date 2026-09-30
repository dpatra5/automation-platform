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
import { buildRepository, functionalSteps, pageIdentity } from '../repository.mjs'

const serverDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const controllerPort = 18005
const controller = `http://127.0.0.1:${controllerPort}`

// The replay variant renders the modal late and keeps a hidden copy of it, like many component libraries do.
function mainPage(variant) {
  const replay = variant === 'replay'
  const nicknameId = replay ? 'nick-b81f3c9d' : 'nick-a92c7e10'
  const hiddenCopy = replay ? '<div role="dialog" class="modal" hidden><h2>Edit profile</h2><input name="nickname"><button type="button">Save</button></div>' : ''
  return `<!doctype html><html><head><title>Portal</title></head><body>
<h1>Portal</h1>
<button type="button" id="open-help">Open help</button>
<button type="button" id="delete">Delete item</button>
<button type="button" id="edit">Edit profile</button>
${hiddenCopy}
<div role="dialog" aria-modal="true" aria-labelledby="edit-title" class="modal" id="edit-modal" hidden>
  <h2 id="edit-title">Edit profile</h2>
  <label for="${nicknameId}">Nickname</label><input id="${nicknameId}" name="nickname">
  <button type="button" id="save">Save</button>
</div>
<iframe name="payment" src="/frame" width="400" height="120"></iframe>
<script>
  const post = (body) => fetch('/submit', { method: 'POST', body: JSON.stringify(body) });
  document.getElementById('open-help').addEventListener('click', () => window.open('/help', '_blank'));
  document.getElementById('delete').addEventListener('click', () => { if (confirm('Delete item?')) post({ deleted: true }); });
  document.getElementById('edit').addEventListener('click', () => setTimeout(() => { document.getElementById('edit-modal').hidden = false; }, ${replay ? 400 : 0}));
  document.getElementById('save').addEventListener('click', () => {
    post({ nickname: document.getElementById('${nicknameId}').value });
    document.getElementById('edit-modal').hidden = true;
  });
</script></body></html>`
}

const helpPage = `<!doctype html><html><body><h1>Help</h1><input name="question"><button type="button" id="send">Send</button>
<script>document.getElementById('send').addEventListener('click', () => fetch('/submit', { method: 'POST', body: JSON.stringify({ question: document.querySelector('input').value }) }).then(() => window.close()));</script></body></html>`

const framePage = `<!doctype html><html><body><input name="card"><button type="button" id="pay">Pay</button>
<script>document.getElementById('pay').addEventListener('click', () => fetch('/submit', { method: 'POST', body: JSON.stringify({ card: document.querySelector('input').value }) }));</script></body></html>`

let fixtureServer
let fixtureUrl
let submissions = []
let browser
let dataDirectory
let controllerProcess
let controllerLog = ''

before(async () => {
  fixtureServer = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/submit') {
      let body = ''
      req.on('data', (chunk) => { body += chunk })
      req.on('end', () => { submissions.push(JSON.parse(body)); res.end('ok') })
      return
    }
    const url = new URL(req.url, 'http://localhost')
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
    res.end(url.pathname === '/help' ? helpPage : url.pathname === '/frame' ? framePage : mainPage(url.searchParams.get('v') || 'record'))
  })
  await new Promise((resolve) => fixtureServer.listen(0, '127.0.0.1', resolve))
  fixtureUrl = `http://127.0.0.1:${fixtureServer.address().port}/`
  dataDirectory = await fs.mkdtemp(path.join(os.tmpdir(), 'ui-automation-flows-'))
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

async function waitForReplay(replayId) {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const replay = await api(`/api/replays/${replayId}`)
    if (replay.status !== 'running') {
      await api(`/api/replays/${replayId}/close`, { method: 'POST' })
      return replay
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error('Replay did not finish')
}

const waitForSubmissions = async (count) => {
  for (let attempt = 0; attempt < 100 && submissions.length < count; attempt += 1) await new Promise((resolve) => setTimeout(resolve, 50))
  assert.equal(submissions.length, count, `expected ${count} submissions, got ${JSON.stringify(submissions)}`)
}

async function recordPortalFlow() {
  submissions = []
  const session = createSession({ id: 'qa-portal', flowName: 'QA portal journey', testSlug: 'qa-portal-journey', url: `${fixtureUrl}?v=record` })
  const context = await browser.newContext()
  await attachRecorder(session, context, { port: controllerPort, stop: async () => {} })
  const page = await context.newPage()
  session.status = 'recording'
  await page.goto(session.url)

  const [popup] = await Promise.all([context.waitForEvent('page'), page.click('#open-help')])
  await popup.waitForLoadState('domcontentloaded')
  await popup.fill('input[name="question"]', 'How do I pay?')
  await Promise.all([popup.waitForEvent('close'), popup.click('#send')])

  await page.click('#delete')
  await page.click('#edit')
  await page.fill('input[name="nickname"]', 'Neo')
  await page.click('#save')

  const frame = page.frameLocator('iframe[name="payment"]')
  await frame.locator('input[name="card"]').fill('4242')
  await frame.locator('#pay').click()
  await waitForSubmissions(4)

  await Promise.allSettled([...session.pending])
  session.status = 'stopped'
  await context.close()
  return { id: session.id, flowName: session.flowName, testSlug: session.testSlug, url: session.url, events: session.events }
}

test('recording captures new tabs, tab close, dialogs, modals and iframes', async () => {
  const flow = await recordPortalFlow()
  const actions = flow.events.filter((event) => event.type === 'action')
  const newTab = actions.find((event) => event.action === 'newTab')
  assert.ok(newTab, 'popup was not recorded as a new tab')
  assert.equal(newTab.tab, 1)
  assert.equal(newTab.openerTab, 0)
  assert.ok(newTab.pageUrl.endsWith('/help'), `new tab URL: ${newTab.pageUrl}`)
  const openClick = actions.findIndex((event) => event.action === 'click' && event.element?.displayName === 'Open help')
  assert.ok(openClick >= 0 && openClick < actions.indexOf(newTab), 'the click that opened the tab should come first')
  assert.ok(actions.some((event) => event.action === 'closeTab' && event.tab === 1), 'tab close was not recorded')
  assert.ok(actions.some((event) => event.action === 'fill' || (event.action === 'input' && event.tab === 1)), 'popup input should be tagged with its tab')

  const dialog = actions.find((event) => event.action === 'dialog')
  assert.ok(dialog, 'confirm dialog was not recorded')
  assert.equal(dialog.dialogType, 'confirm')
  assert.equal(dialog.message, 'Delete item?')
  assert.equal(dialog.accept, true)
  const deleteClick = actions.findIndex((event) => event.action === 'click' && event.element?.displayName === 'Delete item')
  assert.ok(deleteClick >= 0 && deleteClick < actions.indexOf(dialog), 'the click that opened the dialog should come first')

  const save = actions.find((event) => event.action === 'click' && event.element?.displayName === 'Save')
  assert.deepEqual(save.element.container?.kind, 'modal')
  assert.equal(save.element.container.name, 'Edit profile')

  const card = actions.find((event) => event.action === 'input' && event.element?.attributes?.name === 'card')
  assert.ok(card?.frame?.length === 1, `iframe input has no frame path: ${JSON.stringify(card?.frame)}`)
  assert.equal(card.frameName, 'payment')
})

test('page repository names elements and groups modal and iframe components', async () => {
  const flow = await recordPortalFlow()
  const { test: record, pages } = buildRepository(flow, () => null)
  const home = record.pages.homePage
  const help = record.pages.helpPage
  assert.ok(home && help, `pages: ${Object.keys(record.pages)}`)
  assert.ok(home.elements.openHelpButton && home.elements.deleteItemButton && home.elements.editProfileButton, `home elements: ${Object.keys(home.elements)}`)
  assert.deepEqual(Object.keys(home.components).sort(), ['editProfileModal', 'paymentFrame'])
  assert.deepEqual(Object.keys(home.components.editProfileModal.elements).sort(), ['nicknameInput', 'saveButton'])
  assert.deepEqual(Object.keys(home.components.paymentFrame.elements).sort(), ['cardInput', 'payButton'])
  assert.ok(help.elements.questionInput && help.elements.sendButton, `help elements: ${Object.keys(help.elements)}`)
  assert.ok(Object.values(home.elements).every((xpath) => xpath.startsWith('//') || xpath.startsWith('(//')), 'repository XPaths must be relative')

  const flowText = record.flow.map((step) => step.description)
  assert.equal(record.flow[0].action, 'open')
  assert.ok(flowText.includes(`Enter "How do I pay?" into 'question' input on helpPage`) || flowText.some((line) => line.startsWith('Enter "How do I pay?"')), flowText.join('\n'))
  assert.ok(record.flow.some((step) => step.action === 'dialog' && step.accept === true))
  assert.ok(record.flow.some((step) => step.action === 'newTab') && record.flow.some((step) => step.action === 'closeTab'))
  assert.equal(record.flow.filter((step) => step.action === 'fill' && step.element === 'nicknameInput').length, 1, 'keystrokes should collapse into one fill step')
  assert.ok(!record.flow.some((step) => ['hover', 'focus', 'keyup', 'mousedown', 'mouseup'].includes(step.action)), 'noise events leaked into the functional flow')

  const homeFile = pageIdentity(`${fixtureUrl}?v=record`).file
  assert.ok(pages.get(homeFile).elements.openHelpButton.usedBy.includes('qa-portal-journey'))

  // A second test that reuses an element must share its name instead of creating a duplicate.
  const second = buildRepository({ ...flow, testSlug: 'second-test', events: flow.events.filter((event) => event.element?.displayName === 'Open help') }, (file) => pages.get(file))
  assert.ok(second.test.pages.homePage.elements.openHelpButton)
  assert.deepEqual(second.pages.get(homeFile).elements.openHelpButton.usedBy.sort(), ['qa-portal-journey', 'second-test'])
  assert.equal(functionalSteps(flow)[0].action, 'open')
})

test('replay follows the popup, answers the dialog, waits for the modal and acts inside the iframe', async () => {
  const flow = await recordPortalFlow()
  submissions = []
  await fs.writeFile(path.join(dataDirectory, `${flow.id}.json`), JSON.stringify({ ...flow, url: `${fixtureUrl}?v=replay` }, null, 2))
  const started = await api(`/api/flows/${flow.id}/replay`, { method: 'POST', body: JSON.stringify({ browser: 'chromium' }) })
  const replay = await waitForReplay(started.id)
  const failures = replay.results.filter((result) => result.status === 'failed').map((result) => `${result.index}. ${result.action}: ${result.message}`)
  assert.deepEqual(failures, [], `replay failures:\n${failures.join('\n')}\n${controllerLog}`)
  assert.deepEqual(submissions, [{ question: 'How do I pay?' }, { deleted: true }, { nickname: 'Neo' }, { card: '4242' }])
})

test('a dismissed dialog is replayed as dismissed', async () => {
  const flow = await recordPortalFlow()
  flow.events.find((event) => event.action === 'dialog').accept = false
  submissions = []
  await fs.writeFile(path.join(dataDirectory, 'qa-dismiss.json'), JSON.stringify({ ...flow, id: 'qa-dismiss', url: `${fixtureUrl}?v=replay` }, null, 2))
  const started = await api('/api/flows/qa-dismiss/replay', { method: 'POST', body: JSON.stringify({ browser: 'chromium' }) })
  const replay = await waitForReplay(started.id)
  assert.equal(replay.status, 'passed')
  assert.ok(!submissions.some((item) => item.deleted), 'dismissed confirm must not delete')
})

test('stopping a recording saves it to the test library and it can be re-run by name', async () => {
  const session = await api('/api/sessions', { method: 'POST', body: JSON.stringify({ url: `${fixtureUrl}?v=record`, flowName: 'Library smoke' }) })
  assert.equal(session.testSlug, 'library-smoke')
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const status = await api(`/api/sessions/${session.id}`)
    if (status.status === 'recording' && status.eventCount > 0) break
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  await api(`/api/sessions/${session.id}/stop`, { method: 'POST' })
  const tests = await api('/api/tests')
  const listed = tests.find((item) => item.slug === 'library-smoke')
  assert.ok(listed, `library: ${JSON.stringify(tests)}`)
  assert.equal(listed.name, 'Library smoke')
  const detail = await api('/api/tests/library-smoke')
  assert.equal(detail.flowId, session.id)
  assert.equal(detail.flow[0].action, 'open')
  const stored = JSON.parse(await fs.readFile(path.join(dataDirectory, 'tests', 'library-smoke', 'test.json'), 'utf8'))
  assert.equal(stored.name, 'Library smoke')

  const started = await api('/api/tests/library-smoke/replay', { method: 'POST', body: JSON.stringify({ browser: 'chromium' }) })
  const replay = await waitForReplay(started.id)
  assert.equal(replay.testSlug, 'library-smoke')
  const rerun = await api('/api/tests/library-smoke')
  assert.equal(rerun.lastRun?.id, started.id)

  const again = await api('/api/sessions', { method: 'POST', body: JSON.stringify({ url: `${fixtureUrl}?v=record`, flowName: 'Library smoke' }) })
  assert.equal(again.testSlug, 'library-smoke-2', 'a second test with the same name gets its own folder')
  await api(`/api/sessions/${again.id}/stop`, { method: 'POST' })

  const invalid = await fetch(`${controller}/api/tests/..%2F..%2Fsecrets`)
  assert.equal(invalid.status, 400)
})
