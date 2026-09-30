// Runs a recorded test the way a test engineer would: step by step through the functional flow
// (not the raw mouse/scroll events), locating elements by their relative XPaths and validating each outcome.
import { describeRawStep, functionalSteps, pageIdentity } from './repository.mjs'
import { xpathLiteral } from './recording.mjs'

const SVG_TAGS = new Set(['svg', 'path', 'g', 'use', 'circle', 'rect', 'polygon', 'polyline', 'line', 'ellipse', 'text', 'tspan'])
const ELEMENT_ACTIONS = new Set(['click', 'dblclick', 'fill', 'select', 'check', 'uncheck', 'press', 'submit', 'drag', 'drop', 'assert'])
const OVERLAY_ERROR = /intercepts pointer events|not stable|outside of the viewport|element is not visible/i

export const withoutEngine = (selector) => selector.replace(/^xpath=/, '')

export function normalizeUrl(value) {
  const url = String(value || '').trim()
  return /^https?:\/\//i.test(url) ? url : `https://${url}`
}

export function substitute(value, data) {
  return String(value ?? '').replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key) => data[key] ?? `{{${key}}}`)
}

// Playwright errors carry a long ANSI-coloured call log; the first line is what a tester needs.
function cleanError(error) {
  const text = String(error?.message ?? error).replace(/\u001b\[\d+m/g, '')
  const first = text.split('\n')[0].trim()
  const blocker = text.match(/<([a-z0-9-]+)[^>]*>.*?<\/\1>|<[a-z0-9-]+[^>]*>/i)
  return /intercepts pointer events/.test(text) && blocker ? `${first} Another element covers the target: ${blocker[0].slice(0, 160)}` : first
}

// Stored relative XPaths come first; the other recorded attributes only rescue older flows.
export function locatorCandidates(element = {}) {
  const selectors = []
  const add = (selector) => { if (selector && !selectors.includes(selector)) selectors.push(selector) }
  const xpath = (value) => `xpath=${value}`
  if (element.xpath) add(xpath(element.xpath))
  for (const candidate of element.xpathCandidates || []) add(xpath(candidate))
  if (element.selector) add(/^\(*\//.test(element.selector) ? xpath(element.selector) : element.selector)
  const tag = element.tag && /^[a-z][\w-]*$/i.test(element.tag) && !SVG_TAGS.has(element.tag) ? element.tag : '*'
  if (element.testId) add(xpath(`//${tag}[@data-testid=${xpathLiteral(element.testId)}]`))
  if (element.id) add(xpath(`//${tag}[@id=${xpathLiteral(element.id)}]`))
  if (element.label) add(xpath(`//${tag}[@aria-label=${xpathLiteral(element.label)}]`))
  if (element.name) add(xpath(`//${tag}[@name=${xpathLiteral(element.name)}]`))
  const text = (element.text || '').replace(/\s+/g, ' ').trim()
  if (text && text.length <= 80 && tag !== '*') add(xpath(`//${tag}[normalize-space()=${xpathLiteral(text)}]`))
  return selectors
}

// Scrolls whatever actually scrolls (the window or the biggest scrollable container) so lazy content renders.
async function scrollForMore(page) {
  return page.evaluate(() => {
    const scrollable = (element) => element.scrollHeight > element.clientHeight + 20 && (element === document.scrollingElement || /(auto|scroll|overlay)/.test(getComputedStyle(element).overflowY))
    const candidates = [document.scrollingElement, ...document.querySelectorAll('body *')].filter((element) => element && scrollable(element))
    const target = candidates.sort((a, b) => b.clientHeight * b.clientWidth - a.clientHeight * a.clientWidth)[0]
    if (!target) return true
    const before = target.scrollTop
    target.scrollBy(0, Math.max(target.clientHeight * 0.9, 300))
    return target.scrollTop === before
  }).catch(() => true)
}

async function scrollToTop(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0)
    for (const element of document.querySelectorAll('body *')) if (element.scrollTop > 0) element.scrollTop = 0
  }).catch(() => {})
}

// root is the page, or a frame locator when the element lives inside an iframe.
export async function findElement(page, root, element, { timeout, requireVisible = true }) {
  const selectors = locatorCandidates(element)
  if (!selectors.length) throw new Error('No locator was recorded for this step')
  const deadline = Date.now() + timeout
  let hiddenMatch = null
  let reachedBottom = false
  let returnedToTop = false
  for (let attempt = 0; ; attempt += 1) {
    for (const selector of selectors) {
      const locator = root.locator(selector)
      const count = await locator.count().catch(() => 0)
      if (!count) continue
      // Closed modals and templates often keep hidden copies of an element; use the one the user can see.
      for (let index = 0; index < Math.min(count, 5); index += 1) {
        const target = locator.nth(index)
        if (await target.isVisible().catch(() => false)) {
          await target.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
          return { target, selector, count, hidden: false }
        }
      }
      hiddenMatch ||= { target: locator.first(), selector, count, hidden: true }
    }
    if (Date.now() >= deadline) break
    if (attempt >= 1 && !hiddenMatch) {
      if (!reachedBottom) reachedBottom = await scrollForMore(page)
      else if (!returnedToTop) {
        returnedToTop = true
        await scrollToTop(page)
      }
    }
    await page.waitForTimeout(Math.max(0, Math.min(500, deadline - Date.now())))
  }
  if (hiddenMatch && !requireVisible) return hiddenMatch
  if (hiddenMatch) throw new Error(`Element exists but stayed hidden for ${timeout / 1000}s: ${withoutEngine(hiddenMatch.selector)}`)
  throw new Error(`Element not found after waiting ${timeout / 1000}s and scrolling. Tried: ${selectors.map(withoutEngine).join(' | ')}`)
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

// Closes hover menus / popovers left open by earlier steps so they stop covering the target.
async function dismissOverlays(page) {
  await page.mouse.move(1, 1).catch(() => {})
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(250)
}

async function clickLikeAUser(page, target, action, modifiers) {
  const method = action === 'dblclick' ? 'dblclick' : 'click'
  try {
    await target[method]({ modifiers, timeout: 5000 })
    return ''
  } catch (error) {
    if (!OVERLAY_ERROR.test(error.message)) throw error
  }
  await dismissOverlays(page)
  await target.evaluate((element) => element.scrollIntoView({ block: 'center', inline: 'center' })).catch(() => {})
  try {
    await target[method]({ modifiers, timeout: 5000 })
    return 'An overlay was covering the element; closed it and clicked again.'
  } catch (error) {
    if (!OVERLAY_ERROR.test(error.message)) throw error
  }
  await target.evaluate((element, twice) => { element.click(); if (twice) element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })) }, action === 'dblclick')
  return 'The element stayed covered by another element (e.g. a sticky header); clicked it directly.'
}

async function locate(page, step, timeouts) {
  const event = step.source
  const root = frameRoot(page, event.frame)
  const requireVisible = !['fill', 'select', 'check', 'uncheck'].includes(step.action)
  const reveal = (step.reveal || []).filter((item) => item.xpath)
  if (!reveal.length) return findElement(page, root, event.element, { timeout: timeouts.element, requireVisible })
  try {
    return await findElement(page, root, event.element, { timeout: Math.min(3000, timeouts.element), requireVisible: true })
  } catch {
    // The element sits in a menu that opens on hover, as it did while recording.
    for (const item of reveal) {
      const trigger = await findElement(page, root, item, { timeout: 3000 }).catch(() => null)
      await trigger?.target.hover({ timeout: 3000 }).catch(() => {})
      await page.waitForTimeout(300)
    }
    return findElement(page, root, event.element, { timeout: timeouts.element, requireVisible })
  }
}

const checkboxLike = (element) => ['checkbox', 'radio'].includes((element?.attributes?.type || '').toLowerCase())

async function performElementStep(page, step, steps, index, data, timeouts, result) {
  const event = step.source
  const found = await locate(page, step, timeouts)
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

  switch (step.action) {
    case 'click':
    case 'dblclick': {
      const note = await clickLikeAUser(page, target, step.action, modifiers)
      if (note) result.notes.push(note)
      break
    }
    case 'fill': {
      const expected = substitute(override ?? event.value, data)
      await target.fill(expected, { force })
      const actual = await target.inputValue().catch(() => null)
      if (actual !== null && actual !== expected) throw new Error(`Value check failed: expected "${expected}", field shows "${actual}"`)
      result.checks.push('Field value matches')
      break
    }
    case 'select': {
      const label = substitute(override ?? event.selected ?? event.value, data)
      await target.selectOption({ label }, { force }).catch(() => target.selectOption(substitute(override ?? event.value, data), { force }))
      const selected = await target.evaluate((node) => [node.value, node.selectedOptions?.[0]?.text?.trim()]).catch(() => [])
      if (!selected.includes(label) && !selected.includes(substitute(override ?? event.value, data))) throw new Error(`Selection check failed: expected "${label}", got "${selected[1] ?? selected[0]}"`)
      result.checks.push('Selected option matches')
      break
    }
    case 'check':
    case 'uncheck': {
      const want = step.action === 'check'
      if (checkboxLike(element)) await target.setChecked(want, { force })
      else await clickLikeAUser(page, target, 'click', [])
      if (checkboxLike(element) && (await target.isChecked()) !== want) throw new Error(`Expected the box to be ${want ? 'checked' : 'unchecked'}`)
      result.checks.push(`Box is ${want ? 'checked' : 'unchecked'}`)
      break
    }
    case 'press':
      await target.press(substitute(event.key, data))
      break
    case 'submit':
      await target.evaluate((node) => node.requestSubmit ? node.requestSubmit() : node.submit())
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
      break
    }
    case 'drop':
      if (!step.performed) await target.hover()
      break
    case 'assert': {
      const expected = substitute(step.expectedText, data).replace(/\s+/g, ' ').trim()
      result.checks.push('Element is visible')
      if (expected) {
        const actual = (await target.innerText().catch(() => target.textContent()) || '').replace(/\s+/g, ' ').trim()
        if (!actual.includes(expected)) throw new Error(`Text check failed: expected "${expected}", found "${actual.slice(0, 200)}"`)
        result.checks.push(`Text contains "${expected.slice(0, 60)}"`)
      }
      break
    }
  }
}

/**
 * Executes the functional flow of a recording inside a fresh browser context.
 * Results are pushed to replay.results as they complete so the UI can show progress.
 */
export async function executeFlow(context, flow, data, replay, timeouts) {
  const steps = functionalSteps(flow)
  const tabbed = steps.some((step) => Number.isInteger(step.tab) && step.source)
  const dialogs = createDialogHandler(steps, data)
  context.on('dialog', dialogs.handle)
  const tabs = []
  const firstPage = await context.newPage()
  tabs.push(firstPage)
  let activePage = firstPage
  context.on('page', (page) => {
    tabs.push(page)
    if (!tabbed) activePage = page
  })
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
  let stopped = false
  for (const [index, step] of steps.entries()) {
    const result = { index: index + 1, action: step.action, description: describeRawStep(step), pageUrl: step.url, status: 'passed', message: '', checks: [], notes: [] }
    if (Number.isInteger(step.tab)) result.tab = step.tab
    if (stopped) {
      result.status = 'skipped'
      result.message = 'Not run because an earlier step failed.'
      replay.results.push(result)
      continue
    }
    try {
      switch (step.action) {
        case 'open': {
          const response = await firstPage.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
          if (response && response.status() >= 400) throw new Error(`Page returned HTTP ${response.status()}`)
          result.checks.push(`Page loaded${response ? ` (HTTP ${response.status()})` : ''}`)
          break
        }
        case 'dialog': {
          const outcome = await dialogs.waitFor(index, timeouts.optional)
          if (!outcome) throw new Error(`Expected ${step.dialogType} dialog "${step.message}" did not appear`)
          result.checks.push(`${outcome.accept ? 'Accepted' : 'Dismissed'} ${outcome.type} "${outcome.message}"`)
          if (step.message && outcome.message !== step.message) result.notes.push(`Recorded message was "${step.message}"`)
          break
        }
        case 'closeTab': {
          const closing = tabs[step.tab]
          if (closing && !closing.isClosed()) await closing.waitForEvent('close', { timeout: 1500 }).catch(() => closing.close())
          if (activePage === closing) activePage = tabs.filter((page) => !page.isClosed()).pop() || firstPage
          result.checks.push(`Tab ${step.tab} closed`)
          break
        }
        case 'newTab': {
          // A tab the user opened by hand (no opener) is opened here; one the app opens must appear by itself.
          let page = await waitForTab(step.tab, step.openerTab == null ? 2000 : timeouts.element)
          if (!page && step.openerTab == null) {
            page = await context.newPage()
            await page.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
          }
          if (!page) throw new Error(`Tab ${step.tab} did not open. The link or button that opens it may have changed.`)
          await activate(page)
          await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.element, waitUntil: 'domcontentloaded' }).catch(() => {})
          if (!samePage(step.url, page.url())) throw new Error(`New tab shows ${page.url()}, expected ${step.url}`)
          result.checks.push(`New tab shows ${pageIdentity(page.url()).path}`)
          break
        }
        default: {
          const page = await pageFor(step)
          await activate(page)
          page.setDefaultTimeout(5000)
          await page.waitForLoadState('domcontentloaded').catch(() => {})
          if (step.action === 'switchTab') {
            result.checks.push(`Tab ${step.tab} is active (${page.url()})`)
          } else if (step.action === 'navigate' && step.implicit) {
            await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.element, waitUntil: 'domcontentloaded' }).catch(() => {})
            if (!samePage(step.url, page.url())) throw new Error(`Expected to reach ${step.url}, but the page is ${page.url()}`)
            result.checks.push(`Reached ${pageIdentity(page.url()).path}`)
          } else if (step.action === 'navigate') {
            await page.goto(normalizeUrl(substitute(step.url, data)), { waitUntil: 'domcontentloaded', timeout: 30000 })
            result.checks.push('Page loaded')
          } else if (step.action === 'back' || step.action === 'forward') {
            await (step.action === 'back' ? page.goBack({ waitUntil: 'domcontentloaded', timeout: 30000 }) : page.goForward({ waitUntil: 'domcontentloaded', timeout: 30000 }))
            await page.waitForURL((url) => samePage(step.url, url.href), { timeout: timeouts.optional }).catch(() => {})
            if (!samePage(step.url, page.url())) throw new Error(`Went ${step.action} to ${page.url()}, expected ${step.url}`)
            result.checks.push(`Now on ${pageIdentity(page.url()).path}`)
          } else if (step.action === 'reload') {
            await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 })
            result.checks.push('Page reloaded')
          } else if (ELEMENT_ACTIONS.has(step.action)) {
            await performElementStep(page, step, steps, index, data, timeouts, result)
            if (result.healed) healedSteps += 1
          } else {
            result.notes.push(`Unsupported step "${step.action}" was skipped`)
          }
        }
      }
    } catch (error) {
      result.status = 'failed'
      result.message = cleanError(error)
      stopped = true
    }
    if (result.status === 'passed') result.message = [...result.checks, ...result.notes].join(' · ')
    delete result.healed
    replay.results.push(result)
  }
  return { healedSteps }
}
