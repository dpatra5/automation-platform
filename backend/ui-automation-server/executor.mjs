// Runs a recorded test the way a test engineer would: step by step through the functional flow
// (not the raw mouse/scroll events), locating elements by their relative XPaths and validating each outcome.
// Every check is a soft assertion: a failed step is reported and the run carries on with the next step.
import { describeRawStep, functionalSteps, pageIdentity } from './repository.mjs'
import { cleanError, clickElement, EXPLICIT_WAIT_MS, isConsentElement, scrollToElement, softAssertions, waitForElement, waitForEnabled, withoutEngine } from './ui-utils.mjs'

const ELEMENT_ACTIONS = new Set(['click', 'dblclick', 'fill', 'select', 'check', 'uncheck', 'press', 'submit', 'drag', 'drop', 'assert'])

export function normalizeUrl(value) {
  const url = String(value || '').trim()
  return /^https?:\/\//i.test(url) ? url : `https://${url}`
}

export function substitute(value, data) {
  return String(value ?? '').replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key) => data[key] ?? `{{${key}}}`)
}

// Re-derives the relative XPath from the live element when the stored one did not match cleanly.
async function refreshStoredXPath(event, found) {
  if (found.selector === `xpath=${event.element?.xpath}` && found.count === 1) return false
  const fresh = await found.target.evaluate((node) => window.__uiAutomationXPath?.candidates(node, 4) ?? []).catch(() => [])
  if (!fresh.length || fresh[0] === event.element?.xpath) return false
  event.element = { ...event.element, xpath: fresh[0], xpathCandidates: fresh, selector: fresh[0] }
  return true
}

const frameRoot = (page, frame) => (frame || []).reduce((scope, xpath) => scope.frameLocator(`xpath=${xpath}`), page)

function samePage(expected, actual) {
  const a = pageIdentity(expected)
  const b = pageIdentity(actual)
  return a.host === b.host && a.path === b.path
}

// Answers native dialogs with the decision recorded for the next expected dialog step.
function createDialogHandler(steps, data) {
  const expected = steps.map((step, index) => ({ step, index })).filter(({ step }) => step.action === 'dialog')
  const outcomes = new Map()
  return {
    async handle(dialog) {
      const type = dialog.type()
      const next = type === 'beforeunload' ? null : expected.find(({ index }) => !outcomes.has(index))
      if (!next) {
        await dialog.accept().catch(() => {})
        return
      }
      const accept = next.step.accept !== false
      outcomes.set(next.index, { type, message: dialog.message(), accept })
      await (accept ? dialog.accept(type === 'prompt' ? substitute(next.step.promptText ?? dialog.defaultValue(), data) : undefined) : dialog.dismiss()).catch(() => {})
    },
    async waitFor(index, timeout) {
      const deadline = Date.now() + timeout
      while (!outcomes.has(index) && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 100))
      return outcomes.get(index) ?? null
    },
  }
}

async function locate(page, step, timeouts) {
  const event = step.source
  const root = frameRoot(page, event.frame)
  const requireVisible = !['fill', 'select', 'check', 'uncheck'].includes(step.action)
  const reveal = isConsentElement(event.element) ? [] : (step.reveal || []).filter((item) => item.xpath)
  if (!reveal.length) return waitForElement(page, root, event.element, { timeout: timeouts.element, requireVisible })
  try {
    return await waitForElement(page, root, event.element, { timeout: Math.min(3000, timeouts.element), requireVisible: true })
  } catch {
    // The element sits in a menu that opens on hover, as it did while recording.
    for (const item of reveal) {
      const trigger = await waitForElement(page, root, item, { timeout: 3000 }).catch(() => null)
      await trigger?.target.hover({ timeout: 3000 }).catch(() => {})
      await page.waitForTimeout(300)
    }
    return waitForElement(page, root, event.element, { timeout: timeouts.element, requireVisible })
  }
}

const checkboxLike = (element) => ['checkbox', 'radio'].includes((element?.attributes?.type || '').toLowerCase())
const INPUT_ACTIONS = new Set(['fill', 'select', 'check', 'uncheck', 'press'])

async function performElementStep(page, step, steps, index, data, timeouts, result, soft) {
  const event = step.source
  let found
  try {
    found = await locate(page, step, timeouts)
  } catch (error) {
    // The saved browser state usually already holds the consent cookie, so the banner does not show again.
    if ((step.action === 'click' || step.action === 'dblclick') && isConsentElement(event.element)) {
      soft.check(true, 'Cookie banner not shown', 'Consent is already stored for this site; nothing to accept')
      result.notes.push('Skipped: cookie consent was already given')
      return
    }
    soft.check(false, 'Element is visible', cleanError(error))
    return
  }
  soft.check(true, found.hidden ? 'Element is present (hidden field)' : 'Element is visible', withoutEngine(found.selector))
  if (!found.pageLoaded) result.notes.push(`Page was still loading after ${timeouts.element / 1000}s; continued with the visible element.`)
  result.locator = withoutEngine(found.selector)
  if (found.count > 1) result.notes.push(`Locator matched ${found.count} elements; used the first visible one.`)
  if (await refreshStoredXPath(event, found)) {
    result.healed = true
    result.notes.push(`Stored relative XPath refreshed to ${event.element.xpath}`)
  }
  const target = found.target
  const force = found.hidden
  const element = event.element
  const override = data[element?.label] ?? data[element?.id] ?? data[element?.testId] ?? data[element?.name]
  const modifiers = Object.entries(event.modifiers || {}).filter(([, enabled]) => enabled).map(([key]) => ({ ctrl: 'Control', meta: 'Meta', shift: 'Shift', alt: 'Alt' })[key] || key)

  if (INPUT_ACTIONS.has(step.action) && !force) {
    if (!soft.check(await waitForEnabled(target, timeouts.element), 'Element is enabled', 'Field stayed disabled')) return
    await scrollToElement(page, target)
  }

  switch (step.action) {
    case 'click':
    case 'dblclick': {
      const outcome = await clickElement(page, target, { action: step.action, modifiers, timeout: timeouts.element })
      soft.check(outcome.enabled, 'Element is enabled', outcome.enabled ? '' : 'Element stayed disabled')
      if (outcome.enabled) soft.check(outcome.clicked, step.action === 'dblclick' ? 'Element double-clicked' : 'Element clicked', outcome.via)
      break
    }
    case 'fill': {
      const expected = substitute(override ?? event.value, data)
      await target.fill(expected, { force })
      const actual = await target.inputValue().catch(() => null)
      soft.check(actual === null || actual === expected, 'Field value matches', actual === null || actual === expected ? '' : `expected "${expected}", field shows "${actual}"`)
      break
    }
    case 'select': {
      const label = substitute(override ?? event.selected ?? event.value, data)
      const value = substitute(override ?? event.value, data)
      await target.selectOption({ label }, { force }).catch(() => target.selectOption(value, { force }))
      const selected = await target.evaluate((node) => [node.value, node.selectedOptions?.[0]?.text?.trim()]).catch(() => [])
      soft.check(selected.includes(label) || selected.includes(value), 'Selected option matches', selected.includes(label) || selected.includes(value) ? '' : `expected "${label}", got "${selected[1] ?? selected[0]}"`)
      break
    }
    case 'check':
    case 'uncheck': {
      const want = step.action === 'check'
      if (checkboxLike(element)) await target.setChecked(want, { force })
      else await clickElement(page, target, { timeout: timeouts.element })
      if (checkboxLike(element)) soft.check((await target.isChecked()) === want, `Box is ${want ? 'checked' : 'unchecked'}`)
      break
    }
    case 'press':
      await target.press(substitute(event.key, data))
      soft.check(true, `Pressed ${event.key}`)
      break
    case 'submit':
      await target.evaluate((node) => node.requestSubmit ? node.requestSubmit() : node.submit())
      soft.check(true, 'Form submitted')
      break
    case 'drag': {
      const drop = steps[index + 1]?.action === 'drop' ? steps[index + 1] : null
      if (!drop) {
        await target.hover()
        break
      }
      const destination = await locate(page, drop, timeouts)
      await target.dragTo(destination.target)
      drop.performed = true
      soft.check(true, 'Dragged to drop target')
      break
    }
    case 'drop':
      if (!step.performed) await target.hover()
      break
    case 'assert': {
      const expected = substitute(step.expectedText, data).replace(/\s+/g, ' ').trim()
      if (expected) {
        const actual = (await target.innerText().catch(() => target.textContent()) || '').replace(/\s+/g, ' ').trim()
        soft.check(actual.includes(expected), `Text contains "${expected.slice(0, 60)}"`, actual.includes(expected) ? '' : `found "${actual.slice(0, 200)}"`)
      }
      break
    }
  }
}

function buildSummary(results, startedAt) {
  const finishedAt = new Date()
  const assertions = results.flatMap((result) => result.assertions || [])
  const failedSteps = results.filter((result) => result.status === 'failed')
  return {
    status: failedSteps.length ? 'failed' : 'passed',
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    durationMs: finishedAt - startedAt,
    steps: { total: results.length, passed: results.filter((result) => result.status === 'passed').length, failed: failedSteps.length },
    assertions: { total: assertions.length, passed: assertions.filter((item) => item.passed).length, failed: assertions.filter((item) => !item.passed).length },
    failures: failedSteps.map((result) => ({
      step: result.index,
      description: result.description,
      reasons: (result.assertions || []).filter((item) => !item.passed).map((item) => item.detail ? `${item.label}: ${item.detail}` : item.label),
    })),
  }
}

/**
 * Executes the functional flow of a recording. With `shared`, the context is the long-lived test browser:
 * only tabs opened by this run are used, and they are closed when the run ends.
 * Results are pushed to replay.results as they complete so the UI can show progress.
 */
export async function executeFlow(context, flow, data, replay, timeouts, { shared = false } = {}) {
  const steps = functionalSteps(flow)
  const tabbed = steps.some((step) => Number.isInteger(step.tab) && step.source)
  const dialogs = createDialogHandler(steps, data)
  const tabs = []
  const runPages = new Set()
  const own = (page) => {
    if (runPages.has(page)) return
    runPages.add(page)
    page.on('dialog', dialogs.handle)
    tabs.push(page)
  }
  const firstPage = await context.newPage()
  own(firstPage)
  let activePage = firstPage
  const onPage = async (page) => {
    // In the shared test browser only pop-ups opened by this run's tabs belong to it.
    if (shared) {
      const opener = await page.opener().catch(() => null)
      if (!opener || !runPages.has(opener)) return
    }
    own(page)
    if (!tabbed) activePage = page
  }
  context.on('page', onPage)
  const waitForTab = async (tab, timeout) => {
    const deadline = Date.now() + timeout
    while (!tabs[tab] && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 100))
    return tabs[tab] ?? null
  }
  const pageFor = async (step) => {
    if (!Number.isInteger(step.tab)) return activePage
    const page = await waitForTab(step.tab, timeouts.element)
    if (!page) throw new Error(`Tab ${step.tab} never opened. The link or button that opens it may have changed.`)
    if (page.isClosed()) throw new Error(`Tab ${step.tab} was closed before this step`)
    return page
  }
  const activate = async (page) => {
    if (page === activePage) return
    activePage = page
    await page.bringToFront().catch(() => {})
  }

  let healedSteps = 0
  const startedAt = new Date()
  for (const [index, step] of steps.entries()) {
    const result = { index: index + 1, action: step.action, description: describeRawStep(step), pageUrl: step.url, status: 'passed', message: '', assertions: [], notes: [] }
    if (Number.isInteger(step.tab)) result.tab = step.tab
    const soft = softAssertions()
    try {
      switch (step.action) {
        case 'open': {
          const response = await firstPage.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
          soft.check(!response || response.status() < 400, 'Page loaded', response ? `HTTP ${response.status()}` : '')
          break
        }
        case 'dialog': {
          const outcome = await dialogs.waitFor(index, timeouts.optional)
          if (!soft.check(outcome, `${step.dialogType} dialog appeared`, outcome ? '' : `"${step.message}" did not appear`)) break
          soft.check(true, `${outcome.accept ? 'Accepted' : 'Dismissed'} ${outcome.type}`, `"${outcome.message}"`)
          if (step.message && outcome.message !== step.message) result.notes.push(`Recorded message was "${step.message}"`)
          break
        }
        case 'closeTab': {
          const closing = tabs[step.tab]
          if (closing && !closing.isClosed()) await closing.waitForEvent('close', { timeout: 1500 }).catch(() => closing.close())
          if (activePage === closing) activePage = tabs.filter((page) => !page.isClosed()).pop() || firstPage
          soft.check(true, `Tab ${step.tab} closed`)
          break
        }
        case 'newTab': {
          // A tab the user opened by hand (no opener) is opened here; one the app opens must appear by itself.
          let page = await waitForTab(step.tab, step.openerTab == null ? 2000 : timeouts.element)
          if (!page && step.openerTab == null) {
            page = await context.newPage()
            own(page)
            await page.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
          }
          if (!soft.check(page, `Tab ${step.tab} opened`, page ? '' : 'The link or button that opens it may have changed')) break
          await activate(page)
          await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.element, waitUntil: 'domcontentloaded' }).catch(() => {})
          soft.check(samePage(step.url, page.url()), 'New tab shows the expected page', page.url())
          break
        }
        default: {
          const page = await pageFor(step)
          await activate(page)
          page.setDefaultTimeout(EXPLICIT_WAIT_MS)
          await page.waitForLoadState('domcontentloaded').catch(() => {})
          if (step.action === 'switchTab') {
            soft.check(true, `Tab ${step.tab} is active`, page.url())
          } else if (step.action === 'navigate' && step.implicit) {
            await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.element, waitUntil: 'domcontentloaded' }).catch(() => {})
            soft.check(samePage(step.url, page.url()), `Reached ${pageIdentity(step.url).path}`, samePage(step.url, page.url()) ? '' : `page is ${page.url()}`)
          } else if (step.action === 'navigate') {
            await page.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
            soft.check(true, 'Page loaded', page.url())
          } else if (step.action === 'back' || step.action === 'forward') {
            await (step.action === 'back' ? page.goBack({ waitUntil: 'domcontentloaded', timeout: 30000 }) : page.goForward({ waitUntil: 'domcontentloaded', timeout: 30000 }))
            await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.optional }).catch(() => {})
            soft.check(samePage(step.url, page.url()), `Went ${step.action} to ${pageIdentity(step.url).path}`, samePage(step.url, page.url()) ? '' : `page is ${page.url()}`)
          } else if (step.action === 'reload') {
            await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 })
            soft.check(true, 'Page reloaded')
          } else if (ELEMENT_ACTIONS.has(step.action)) {
            await performElementStep(page, step, steps, index, data, timeouts, result, soft)
            if (result.healed) healedSteps += 1
          } else {
            result.notes.push(`Unsupported step "${step.action}" was skipped`)
          }
        }
      }
    } catch (error) {
      soft.check(false, `${step.action} step completed`, cleanError(error))
    }
    result.assertions = soft.list
    const failed = soft.failed
    result.status = failed.length ? 'failed' : 'passed'
    result.message = failed.length
      ? failed.map((item) => item.detail ? `${item.label}: ${item.detail}` : item.label).join(' · ')
      : [...soft.list.map((item) => item.label), ...result.notes].join(' · ')
    delete result.healed
    replay.results.push(result)
  }
  context.off('page', onPage)
  if (shared) await Promise.all([...runPages].filter((page) => !page.isClosed()).map((page) => page.close().catch(() => {})))
  return { healedSteps, summary: buildSummary(replay.results, startedAt) }
}
