// Common wait / scroll / click utilities and soft assertions used for every element step.
import { xpathLiteral } from './recording.mjs'

export const EXPLICIT_WAIT_MS = Number(process.env.UI_AUTOMATION_EXPLICIT_WAIT_MS || 5000)

const SVG_TAGS = new Set(['svg', 'path', 'g', 'use', 'circle', 'rect', 'polygon', 'polyline', 'line', 'ellipse', 'text', 'tspan'])

export const withoutEngine = (selector) => selector.replace(/^xpath=/, '')

// Playwright errors carry a long ANSI-coloured call log; the first line is what a tester needs.
export function cleanError(error) {
  const text = String(error?.message ?? error).replace(/\u001b\[\d+m/g, '')
  const first = text.split('\n')[0].trim()
  const blocker = text.match(/<([a-z0-9-]+)[^>]*>.*?<\/\1>|<[a-z0-9-]+[^>]*>/i)
  return /intercepts pointer events/.test(text) && blocker ? `${first} Another element covers the target: ${blocker[0].slice(0, 160)}` : first
}

// Collects pass/fail checks without throwing, so a failed check never stops the run.
export function softAssertions() {
  const list = []
  return {
    list,
    check(passed, label, detail = '') {
      list.push({ label, passed: Boolean(passed), detail: String(detail ?? '') })
      return Boolean(passed)
    },
    get failed() { return list.filter((item) => !item.passed) },
  }
}

// Waits until the document has finished loading (readyState "complete"), up to the explicit wait.
export async function waitForPageLoad(page, timeout = EXPLICIT_WAIT_MS) {
  const started = Date.now()
  await page.waitForLoadState('load', { timeout }).catch(() => {})
  const remaining = Math.max(500, timeout - (Date.now() - started))
  return page.waitForFunction(() => document.readyState === 'complete', null, { timeout: remaining }).then(() => true, () => false)
}

// The one scroll helper: brings the element to the middle of its scroll container.
export async function scrollToElement(page, locator) {
  await locator.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
  await locator.evaluate((element) => element.scrollIntoView({ block: 'center', inline: 'center' })).catch(() => {})
  await page.waitForTimeout(150)
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

// root is the page, or a frame locator when the element lives inside an iframe.
export async function findElement(page, root, element, { timeout = EXPLICIT_WAIT_MS, requireVisible = true } = {}) {
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
        if (await target.isVisible().catch(() => false)) return { target, selector, count, hidden: false }
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

// Explicit wait used before every element interaction: page fully loaded, then the element visible.
export async function waitForElement(page, root, element, { timeout = EXPLICIT_WAIT_MS, requireVisible = true } = {}) {
  const pageLoaded = await waitForPageLoad(page, timeout)
  const found = await findElement(page, root, element, { timeout, requireVisible })
  return { ...found, pageLoaded }
}

export async function waitForEnabled(locator, timeout = EXPLICIT_WAIT_MS) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await locator.isEnabled().catch(() => false)) return true
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  return locator.isEnabled().catch(() => false)
}

// Playwright's trial click runs every actionability check (visible, stable, enabled, not covered) without clicking.
export async function isClickable(locator, timeout = 1000) {
  return locator.click({ trial: true, timeout }).then(() => true, () => false)
}

const MODAL_SELECTOR = 'dialog, [role="dialog"], [role="alertdialog"], [aria-modal="true"], .modal'

// Cookie banners from common consent managers (OneTrust, Cookiebot, Didomi, Usercentrics, TrustArc, Quantcast, ...).
const CONSENT_PATTERN = /cookie|consent|gdpr|onetrust|optanon|cookiebot|didomi|usercentrics|truste|osano|\bcmp\b|qc-cmp|sp_message/i

export function isConsentElement(element = {}) {
  const parts = [element.xpath, ...(element.xpathCandidates || []), element.id, element.text, element.displayName, element.label, element.container?.name, element.attributes?.id, element.attributes?.class, element.attributes?.['aria-label']]
  return CONSENT_PATTERN.test(parts.filter(Boolean).join(' '))
}

export async function isInsideModal(locator) {
  return locator.evaluate((element, selector) => Boolean(element.closest(selector)), MODAL_SELECTOR).catch(() => false)
}

// Closes hover menus / popovers left open by earlier steps so they stop covering the target.
// Escape is skipped for elements inside a modal, because it would close that modal.
export async function dismissOverlays(page, { keepModalOpen = false } = {}) {
  await page.mouse.move(1, 1).catch(() => {})
  if (!keepModalOpen) await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(250)
}

/**
 * Clicks like a user: requires the element to be enabled; if it is not clickable where it is,
 * scrolls to it, then closes overlays, and as a last resort clicks it from script.
 * Returns { clicked, enabled, via } and never throws for "could not click".
 */
export async function clickElement(page, locator, { action = 'click', modifiers = [], timeout = EXPLICIT_WAIT_MS } = {}) {
  const enabled = await waitForEnabled(locator, timeout)
  if (!enabled) return { clicked: false, enabled: false, via: 'Element is visible but disabled' }
  const method = action === 'dblclick' ? 'dblclick' : 'click'
  const attempt = async () => locator[method]({ modifiers, timeout: 2000 }).then(() => true, () => false)
  if (await isClickable(locator) && await attempt()) return { clicked: true, enabled, via: '' }
  await scrollToElement(page, locator)
  if (await isClickable(locator) && await attempt()) return { clicked: true, enabled, via: 'Scrolled to the element, then clicked' }
  const inModal = await isInsideModal(locator)
  await dismissOverlays(page, { keepModalOpen: inModal })
  await scrollToElement(page, locator)
  if (await isClickable(locator) && await attempt()) return { clicked: true, enabled, via: inModal ? 'Waited for the modal to settle, scrolled, then clicked' : 'Closed an overlay, scrolled, then clicked' }
  const scripted = await locator.evaluate((element, twice) => {
    element.click()
    if (twice) element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))
    return true
  }, action === 'dblclick').catch(() => false)
  return scripted
    ? { clicked: true, enabled, via: 'Element stayed covered (e.g. sticky header); clicked it from script' }
    : { clicked: false, enabled, via: 'Element could not be clicked' }
}
