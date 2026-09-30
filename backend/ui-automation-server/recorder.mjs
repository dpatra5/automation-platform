// Both functions run inside the browser page. They are serialized with toString(),
// so they must stay self-contained: no imports and no references to module scope.

export function installXPathEngine() {
  if (window.__uiAutomationXPath) return

  const XHTML = 'http://www.w3.org/1999/xhtml'
  const TEST_ID_ATTRIBUTES = ['data-testid', 'data-test-id', 'data-test', 'data-cy', 'data-qa', 'data-automation-id']
  const NAMING_ATTRIBUTES = ['name', 'aria-label', 'placeholder', 'title', 'alt', 'for']
  const TEXT_TAGS = new Set(['a', 'button', 'label', 'summary', 'option', 'li', 'td', 'th', 'span', 'p', 'legend', 'dt', 'dd', 'strong', 'em', 'b', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
  const INTERACTIVE = 'a[href], button, input, select, textarea, label, summary, option, [role="button"], [role="link"], [role="menuitem"], [role="tab"], [role="checkbox"], [role="radio"], [role="option"], [role="switch"], [contenteditable="true"], [onclick]'
  const STATE_CLASS = /^(is|has|ui|js)-|^(active|selected|checked|completed|done|open|opened|closed|expanded|collapsed|disabled|enabled|hidden|visible|show|shown|focus|focused|hover|hovered|current|editing|loading|busy|error|invalid|valid|dirty|touched|pending|sticky)$/i
  const MODAL = 'dialog, [role="dialog"], [role="alertdialog"], [aria-modal="true"], .modal'
  const MAX_CANDIDATES = 4
  const MAX_ANCHOR_LOOKUPS = 30

  const literal = (value) => {
    if (!value.includes("'")) return `'${value}'`
    if (!value.includes('"')) return `"${value}"`
    return `concat('${value.split("'").join(`', "'", '`)}')`
  }

  const nodeTest = (element) => element.namespaceURI === XHTML ? element.localName : `*[local-name()=${literal(element.localName)}]`

  const snapshot = (xpath) => {
    try {
      return document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null)
    } catch {
      return null
    }
  }

  const matchesOnly = (xpath, element) => {
    const result = snapshot(xpath)
    return Boolean(result) && result.snapshotLength === 1 && result.snapshotItem(0) === element
  }

  const positionIn = (xpath, element) => {
    const result = snapshot(xpath)
    if (!result) return 0
    for (let index = 0; index < result.snapshotLength; index += 1) {
      if (result.snapshotItem(index) === element) return index + 1
    }
    return 0
  }

  // Framework-generated ids (React useId, Radix, MUI, hashed suffixes) change between renders.
  const isStableId = (id) => Boolean(id) && id.length <= 80 && !/^\d/.test(id) && !/[\s:]/.test(id) && !/\d{4,}/.test(id) &&
    !/^(radix|headlessui|mui|chakra|mantine|downshift|react-select|ember)[-_:]/i.test(id) && !/[-_][a-f0-9]{6,}$/i.test(id)

  // Keeps classes that name what an element is; drops state, utility and CSS-module hash classes.
  const isStructuralClass = (name) => name.length >= 3 && name.length <= 40 && !STATE_CLASS.test(name) &&
    !/[:/[\]().%!@]/.test(name) && !/__[A-Za-z0-9-]{4,}$/.test(name) && !/^(css|sc|jsx|emotion|makeStyles|svelte)-/i.test(name) &&
    !/^_/.test(name) && !/[a-z]\d[a-z0-9]{3,}$/i.test(name) && !/^-?\d/.test(name) &&
    !/^(p|m|w|h|px|py|mx|my|mt|mb|ml|mr|pt|pb|pl|pr|text|bg|border|rounded|shadow|flex|grid|gap|items|justify|font|leading|z|top|left|right|bottom|col|row|d|order|align|float|overflow|opacity)-/.test(name)

  const normalizedText = (element) => (element.textContent || '').replace(/\s+/g, ' ').trim()

  const predicates = (element) => {
    const out = []
    const add = (predicate) => { if (!out.includes(predicate)) out.push(predicate) }
    for (const attribute of TEST_ID_ATTRIBUTES) {
      const value = element.getAttribute(attribute)
      if (value) add(`@${attribute}=${literal(value)}`)
    }
    if (isStableId(element.id)) add(`@id=${literal(element.id)}`)
    for (const attribute of NAMING_ATTRIBUTES) {
      const value = element.getAttribute(attribute)
      if (value && value.length <= 80) add(`@${attribute}=${literal(value)}`)
    }
    // <label for="x">: points at the input through the label text, so a regenerated id still resolves.
    if (element.id && element.labels) {
      const label = [...element.labels].find((item) => item.htmlFor === element.id)
      const labelText = label ? normalizedText(label) : ''
      if (labelText && labelText.length <= 80) add(`@id=//label[normalize-space()=${literal(labelText)}]/@for`)
    }
    const role = element.getAttribute('role')
    if (role) add(`@role=${literal(role)}`)
    const tag = element.localName
    const type = element.getAttribute('type')
    if (tag === 'input' && ['submit', 'button', 'reset'].includes(type) && element.getAttribute('value')) add(`@value=${literal(element.getAttribute('value'))}`)
    const href = element.getAttribute('href')
    if (tag === 'a' && href && href.length <= 120 && !/^(javascript:|#$)/i.test(href)) add(`@href=${literal(href)}`)
    if (type) add(`@type=${literal(type)}`)
    for (const name of [...element.classList].filter(isStructuralClass).slice(0, 2)) {
      add(`contains(concat(' ', normalize-space(@class), ' '), ${literal(` ${name} `)})`)
    }
    return out
  }

  const textPredicate = (element) => {
    const text = normalizedText(element)
    if (!text || text.length > 80) return null
    if (!TEXT_TAGS.has(element.localName) && element.children.length > 0) return null
    return `normalize-space()=${literal(text)}`
  }

  const step = (element) => {
    const test = nodeTest(element)
    const siblings = element.parentElement ? [...element.parentElement.children].filter((sibling) => sibling.localName === element.localName && sibling.namespaceURI === element.namespaceURI) : [element]
    return siblings.length > 1 ? `${test}[${siblings.indexOf(element) + 1}]` : test
  }

  const candidates = (element, limit = MAX_CANDIDATES) => {
    if (!(element instanceof Element)) return []
    const found = []
    const accept = (xpath) => {
      if (found.length < limit && xpath && !found.includes(xpath) && matchesOnly(xpath, element)) found.push(xpath)
      return found.length >= limit
    }
    const test = nodeTest(element)
    const own = predicates(element)
    const text = textPredicate(element)
    const identifying = text ? [...own, text] : own

    for (const predicate of identifying) if (accept(`//${test}[${predicate}]`)) return found
    if (found.length < 2) {
      for (let i = 0; i < identifying.length; i += 1) {
        for (let j = i + 1; j < identifying.length; j += 1) if (accept(`//${test}[${identifying[i]} and ${identifying[j]}]`)) return found
      }
    }

    const label = element.closest('label')
    if (label && label !== element && ['input', 'select', 'textarea'].includes(element.localName)) {
      const labelText = textPredicate(label)
      if (labelText && accept(`//label[${labelText}]//${test}`)) return found
    }

    // Anchor on the nearest ancestor that identifies itself instead of counting from /html.
    const steps = [step(element)]
    let ancestor = element.parentElement
    let lookups = 0
    while (ancestor && ancestor !== document.documentElement && found.length < limit && lookups < MAX_ANCHOR_LOOKUPS) {
      const anchorTest = nodeTest(ancestor)
      for (const predicate of predicates(ancestor).slice(0, 3)) {
        lookups += 1
        const anchor = `//${anchorTest}[${predicate}]`
        for (const ownPredicate of identifying.slice(0, 3)) if (accept(`${anchor}//${test}[${ownPredicate}]`)) return found
        if (accept(`${anchor}/${steps.join('/')}`)) return found
        if (found.length) break
      }
      if (found.length) break
      steps.unshift(step(ancestor))
      if (ancestor.localName === 'body') {
        accept(`//${steps.join('/')}`)
        break
      }
      ancestor = ancestor.parentElement
    }

    if (!found.length) {
      const base = identifying.length ? `//${test}[${identifying[0]}]` : `//${test}`
      const position = positionIn(base, element)
      if (position) found.push(`(${base})[${position}]`)
    }
    return found
  }

  const actionable = (element) => {
    if (!(element instanceof Element)) return element
    return element.closest(INTERACTIVE) || element
  }

  const textOfIds = (ids) => (ids || '').split(/\s+/).map((id) => id && document.getElementById(id)).filter(Boolean).map(normalizedText).join(' ').trim()

  // Roughly the accessible name: what a tester would call the element.
  const displayName = (element) => {
    const aria = (element.getAttribute('aria-label') || '').trim() || textOfIds(element.getAttribute('aria-labelledby'))
    if (aria) return aria.slice(0, 60)
    const label = element.labels?.[0] ? normalizedText(element.labels[0]) : ''
    if (label) return label.slice(0, 60)
    for (const attribute of ['placeholder', 'title', 'alt']) {
      const value = (element.getAttribute(attribute) || '').trim()
      if (value) return value.slice(0, 60)
    }
    if (element.localName === 'input' && ['submit', 'button', 'reset'].includes(element.getAttribute('type')) && element.getAttribute('value')) return element.getAttribute('value').slice(0, 60)
    const text = normalizedText(element)
    if (text && text.length <= 60) return text
    return element.getAttribute('name') || TEST_ID_ATTRIBUTES.map((attribute) => element.getAttribute(attribute)).find(Boolean) || (isStableId(element.id) ? element.id : '')
  }

  const containerOf = (element) => {
    const root = element.closest(MODAL)
    if (!root || root === element) return null
    const heading = root.querySelector('h1, h2, h3, h4, h5, h6, [role="heading"], .modal-title')
    const name = (root.getAttribute('aria-label') || '').trim() || textOfIds(root.getAttribute('aria-labelledby')) || (heading ? normalizedText(heading) : '')
    return { kind: 'modal', name: name.slice(0, 40), xpath: candidates(root, 1)[0] || '' }
  }

  const describe = (element, limit = MAX_CANDIDATES) => {
    if (!(element instanceof Element)) return { selector: '', xpath: '', xpathCandidates: [], tag: '' }
    const xpathCandidates = candidates(element, limit)
    const xpath = xpathCandidates[0] || ''
    return {
      selector: xpath,
      xpath,
      xpathCandidates,
      displayName: displayName(element),
      container: containerOf(element),
      tag: element.localName,
      id: element.getAttribute('id'),
      testId: TEST_ID_ATTRIBUTES.map((attribute) => element.getAttribute(attribute)).find(Boolean) || null,
      role: element.getAttribute('role'),
      label: element.getAttribute('aria-label'),
      name: element.getAttribute('name'),
      text: normalizedText(element).slice(0, 120),
      value: element.value ?? null,
      checked: element.checked ?? null,
      selected: element.selected ?? null,
      attributes: Object.fromEntries([...element.attributes].map((attribute) => [attribute.name, attribute.value])),
    }
  }

  window.__uiAutomationXPath = { candidates, describe, actionable, matchesOnly }
}

export function installRecorder(config) {
  // Popups keep their initial about:blank window object but get a new document, so the guard lives on the document.
  if (document.__uiAutomationRecorder) return
  document.__uiAutomationRecorder = true
  const engine = window.__uiAutomationXPath
  const state = { paused: false, verifying: false }
  const recentHovers = []

  const send = (payload) => {
    if (typeof window.uiAutomationRecord === 'function') return window.uiAutomationRecord(payload)
    return fetch(`http://127.0.0.1:${config.port}/api/sessions/${config.sessionId}/events`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload), keepalive: true,
    }).catch(() => {})
  }

  const isToolbar = (target) => target instanceof Element && Boolean(target.closest('#__ui-automation-toolbar'))
  const textOf = (element) => (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200)

  // Hovers the user rested on that opened the menu holding the clicked element; replay hovers them only if the target is hidden.
  const revealersFor = (element) => {
    const now = Date.now()
    const found = []
    for (let index = recentHovers.length - 1; index >= 0 && found.length < 2; index -= 1) {
      const { element: hovered, at } = recentHovers[index]
      const dwell = (recentHovers[index + 1]?.at ?? now) - at
      if (now - at > 15000 || dwell < 200 || !hovered.isConnected || hovered === element || hovered.contains(element) || element.contains(hovered)) continue
      const menuTrigger = Boolean(hovered.closest('[aria-haspopup], [aria-expanded]'))
      let shared = hovered.parentElement
      while (shared && !shared.contains(element)) shared = shared.parentElement
      const small = shared && shared !== document.body && shared !== document.documentElement && shared.getBoundingClientRect().height < window.innerHeight * 0.6
      if ((menuTrigger || small) && !found.some((item) => item === hovered)) found.unshift(hovered)
    }
    return found.map((hovered) => engine.describe(hovered, 2))
  }

  const record = (action, target, details = {}, { promote = false } = {}) => {
    if (state.paused || isToolbar(target)) return
    const element = promote ? engine.actionable(target) : target
    const extra = action === 'click' || action === 'dblclick' ? { reveal: revealersFor(element) } : {}
    send({ type: 'action', action, ...details, ...extra, pageUrl: location.href, element: engine.describe(element, 4) })
  }

  const modifiers = (event) => ({ alt: event.altKey, ctrl: event.ctrlKey, shift: event.shiftKey, meta: event.metaKey })
  const listen = (type, handler) => document.addEventListener(type, handler, true)

  listen('click', (event) => record('click', event.target, { button: event.button, x: event.clientX, y: event.clientY, modifiers: modifiers(event) }, { promote: true }))
  listen('dblclick', (event) => record('dblclick', event.target, { x: event.clientX, y: event.clientY }, { promote: true }))
  listen('mouseover', (event) => {
    if (state.paused || !(event.target instanceof Element) || isToolbar(event.target)) return
    recentHovers.push({ element: event.target, at: Date.now() })
    if (recentHovers.length > 30) recentHovers.shift()
  })
  listen('input', (event) => record('input', event.target, { value: event.target?.value ?? '' }))
  listen('change', (event) => record('change', event.target, { value: event.target?.value ?? '', selected: event.target?.selectedOptions?.[0]?.text ?? null }))
  listen('keydown', (event) => record('keydown', event.target, { key: event.key, code: event.code, modifiers: modifiers(event) }))
  listen('dragstart', (event) => record('dragstart', event.target))
  listen('drop', (event) => record('drop', event.target))
  listen('submit', (event) => record('submit', event.target))

  // Verify mode: the next click is not passed to the page; it records an assertion on the clicked element instead.
  const verifyStyle = document.createElement('style')
  verifyStyle.textContent = '[data-ui-automation-verify]{outline:2px solid #22c55e !important;outline-offset:2px !important;cursor:crosshair !important}'
  let verifyHover = null
  const clearVerifyHover = () => { verifyHover?.removeAttribute('data-ui-automation-verify'); verifyHover = null }
  const block = (event) => {
    if (!state.verifying || isToolbar(event.target)) return
    event.preventDefault()
    event.stopImmediatePropagation()
    if (event.type !== 'click' || !(event.target instanceof Element)) return
    const element = textOf(event.target) || !engine.actionable(event.target) ? event.target : engine.actionable(event.target)
    send({ type: 'action', action: 'assert', pageUrl: location.href, expectedText: textOf(element), expectedValue: element.value ?? null, element: engine.describe(element, 4) })
    setVerifying(false)
  }
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'dblclick']) window.addEventListener(type, block, true)
  window.addEventListener('mouseover', (event) => {
    if (!state.verifying || !(event.target instanceof Element) || isToolbar(event.target)) return
    clearVerifyHover()
    verifyHover = event.target
    verifyHover.setAttribute('data-ui-automation-verify', '')
  }, true)
  let setVerifying = (on) => { state.verifying = on; if (!on) clearVerifyHover() }

  if (window === window.top) {
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') send({ type: 'tab-visible' }) })
    const reportLoad = () => send({ type: 'page-load', pageUrl: location.href, navType: performance.getEntriesByType('navigation')[0]?.type || '' })
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', reportLoad, { once: true })
    else reportLoad()
  }

  let lastSnapshot = ''
  const snapshot = (type) => {
    const html = document.documentElement.outerHTML.slice(0, 200000)
    if (html === lastSnapshot) return
    lastSnapshot = html
    send({ type, pageUrl: location.href, html })
  }
  let mutationTimer = null
  const observer = new MutationObserver(() => {
    if (state.paused || mutationTimer) return
    mutationTimer = setTimeout(() => { mutationTimer = null; snapshot('dom-change') }, 2000)
  })
  // Init scripts can run before the parser has created <html>.
  const observe = () => observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true })
  if (document.documentElement) observe()
  else document.addEventListener('readystatechange', observe, { once: true })
  window.addEventListener('load', () => snapshot('dom'))

  const mountToolbar = () => {
    if (window !== window.top || !document.body || document.getElementById('__ui-automation-toolbar')) return
    document.head?.appendChild(verifyStyle)
    const toolbar = document.createElement('div')
    toolbar.id = '__ui-automation-toolbar'
    toolbar.innerHTML = '<strong>UI Automation</strong><span id="__ui-status">Recording</span><button data-action="verify" title="Click, then click an element to check its text on every run">Verify</button><button data-action="dialog-policy" data-value="accept" title="How alert/confirm/prompt dialogs are answered while recording">Dialogs: Accept</button><button data-action="pause">Pause</button><button data-action="resume" hidden>Resume</button><button data-action="stop">Stop</button>'
    Object.assign(toolbar.style, { position: 'fixed', zIndex: '2147483647', bottom: '16px', right: '16px', display: 'flex', gap: '8px', alignItems: 'center', padding: '10px 12px', borderRadius: '10px', background: '#101323', color: '#fff', font: '13px Segoe UI, sans-serif', boxShadow: '0 8px 24px #0005' })
    const status = toolbar.querySelector('#__ui-status')
    const verifyButton = toolbar.querySelector('[data-action="verify"]')
    const show = (paused) => {
      toolbar.querySelector('[data-action="pause"]').hidden = paused
      toolbar.querySelector('[data-action="resume"]').hidden = !paused
      status.textContent = paused ? 'Paused' : 'Recording'
    }
    const baseSetVerifying = setVerifying
    setVerifying = (on) => {
      baseSetVerifying(on)
      verifyButton.textContent = on ? 'Cancel verify' : 'Verify'
      status.textContent = on ? 'Click an element to verify' : state.paused ? 'Paused' : 'Recording'
    }
    toolbar.querySelectorAll('button').forEach((button) => {
      Object.assign(button.style, { border: '0', borderRadius: '6px', padding: '5px 8px', cursor: 'pointer' })
      button.addEventListener('click', () => {
        const action = button.dataset.action
        if (action === 'verify') {
          setVerifying(!state.verifying)
          return
        }
        if (action === 'dialog-policy') {
          button.dataset.value = button.dataset.value === 'accept' ? 'dismiss' : 'accept'
          button.textContent = `Dialogs: ${button.dataset.value === 'accept' ? 'Accept' : 'Dismiss'}`
          send({ type: 'control', action, value: button.dataset.value })
          return
        }
        if (action === 'pause' || action === 'resume') {
          state.paused = action === 'pause'
          show(state.paused)
        }
        send({ type: 'control', action })
      })
    })
    document.body.appendChild(toolbar)
  }
  if (document.body) mountToolbar()
  else document.addEventListener('DOMContentLoaded', mountToolbar, { once: true })
}

export const xpathEngineScript = `(${installXPathEngine.toString()})();`

export const recorderScript = (sessionId, port) => `${xpathEngineScript}\n(${installRecorder.toString()})(${JSON.stringify({ sessionId, port })});`
