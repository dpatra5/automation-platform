import {
  generateSelector,
  generateCssSelector,
  describeElement,
  fingerprintElement,
} from "./selector-engine";
import { RecorderIsland } from "./recorder-island";
import type { AssertionOption, RecordedStep } from "./types";
import type { CheckDraft, PendingCheck } from "./recorder-island";

const DASHBOARD_ORIGINS = ["http://localhost:5173", "http://localhost:5174"];
const HIGHLIGHT_ID = "rewind-pick-highlight";

// This script runs in every frame. Only one of them draws the recorder island;
// the rest just capture. See claimIsland().
const IS_TOP_FRAME = window.top === window;
/** The frame's own URL, sent with each step so replay can find it again. */
const FRAME_URL = IS_TOP_FRAME ? null : location.href;

// The service worker also injects this file into tabs that were already open
// when the extension loaded (manifest injection only covers later loads). The
// flag keeps a tab that received both copies from wiring up two sets of
// listeners and recording every action twice.
declare global {
  interface Window {
    __rewindRecorderLoaded?: boolean;
  }
}

let isRecording = false;
let paused = false;
let authPaused = false;
let listenersAttached = false;
let appOrigin = "";
let assertions: AssertionOption[] = [];
/** True in the one frame that draws the island. */
let hostsIsland = false;

// "Add check" mode: the next click picks an element instead of being recorded.
let picking = false;
let pending: PendingCheck | null = null;

const island = new RecorderIsland({
  onPauseToggle: () => chrome.runtime.sendMessage({ type: "TOGGLE_PAUSE" }),
  onStop: () => stopRecording(),
  onTogglePick: () => (picking || pending ? cancelPick() : startPick()),
  onAddCheck: (draft) => addCheck(draft),
  onCancelCheck: () => cancelPick(),
});

/** Update the island only from the frame that owns it. */
function paint(next: Parameters<typeof island.update>[0]) {
  if (hostsIsland) island.update(next);
}

function describe(step: RecordedStep): string {
  if (step.action === "assert")
    return `check ${step.assertion_type ?? ""}`.slice(0, 60);
  const target = step.value ? `"${step.value}"` : step.selector;
  return `${step.action} ${target}`.slice(0, 60);
}

function send(step: RecordedStep) {
  if (!isRecording || paused || authPaused || picking) return;
  try {
    chrome.runtime.sendMessage({
      type: "RECORD_STEP",
      step: { ...step, frame_url: step.frame_url ?? FRAME_URL },
    });
    paint({ lastStep: describe(step) });
  } catch {
    // Extension was reloaded while the page stayed open.
  }
}

/**
 * The element the user really interacted with.
 *
 * `event.target` stops at the shadow host, so a click inside a web component
 * would be recorded against the whole component. The composed path starts at
 * the real element, which is what the selector engine needs.
 */
function targetOf(event: Event): HTMLElement | null {
  const path = event.composedPath?.();
  const first = path && path.length ? path[0] : event.target;
  return first instanceof HTMLElement ? first : null;
}

function isTextEntry(el: Element): boolean {
  if (el instanceof HTMLTextAreaElement) return true;
  if (!(el instanceof HTMLInputElement)) return false;
  return !["checkbox", "radio", "button", "submit", "file"].includes(el.type);
}

function isToggle(el: Element): el is HTMLInputElement {
  return (
    el instanceof HTMLInputElement && ["checkbox", "radio"].includes(el.type)
  );
}

function step(
  action: string,
  el: Element | null,
  value: string | null,
): RecordedStep {
  const located = el ? generateSelector(el) : null;
  return {
    order_index: -1,
    action,
    selector: located?.selector ?? "",
    selector_strategy: located?.strategy ?? "css",
    value,
    frame_url: FRAME_URL,
    // What the element is, not just where it sat: replay falls back to this
    // when the recorded path stops matching.
    element_meta: el ? fingerprintElement(el) : null,
    // A hover the mouse only made on its way here is not worth replaying;
    // Playwright hovers the element itself before it acts on it.
    supersedes_hover: !!el && isHoverOnSameTarget(el),
  };
}

// ------------------------------------------------------------------ capture

/**
 * Text entry is buffered rather than recorded per keystroke.
 *
 * `change` alone is not enough: a field that is submitted with Enter and
 * cleared by the app never blurs, so no change event ever fires and the typing
 * would be lost. Every `input` updates the buffer, and the buffer is flushed
 * as one `fill` step the moment anything else happens.
 */
let pendingFill: { element: Element; value: string } | null = null;

function flushPendingFill() {
  if (!pendingFill) return;
  const { element, value } = pendingFill;
  pendingFill = null;
  send(step("fill", element, value));
}

function handleInput(e: Event) {
  // `input` crosses the shadow boundary, so the island's own fields reach
  // here. Typing an expected value into the check form is not a step.
  if (RecorderIsland.isOwnEvent(e.target)) return;
  const target = targetOf(e);
  if (!target || !isTextEntry(target)) return;
  if (pendingFill && pendingFill.element !== target) flushPendingFill();
  pendingFill = { element: target, value: (target as HTMLInputElement).value };
}

function handleClick(e: MouseEvent) {
  const target = targetOf(e);
  if (!target || RecorderIsland.isOwnEvent(e.target)) return;
  // "Add check" mode swallows the click: the user is pointing at something,
  // not driving the app.
  if (picking) {
    e.preventDefault();
    e.stopPropagation();
    choosePickTarget(target);
    return;
  }
  // A click into a text field is implied by the fill step that follows it.
  if (isTextEntry(target)) return;
  flushPendingFill();
  // Toggles are recorded by their change event as check/uncheck, which is what
  // Playwright replays reliably regardless of the current state.
  if (isToggle(target)) return;
  sendRevealHover(target);
  send(step("click", target, null));
}

function handleDblClick(e: MouseEvent) {
  const target = targetOf(e);
  if (!target || RecorderIsland.isOwnEvent(e.target)) return;
  // The two clicks that preceded this are dropped by the service worker.
  send(step("dblclick", target, null));
}

function handleContextMenu(e: MouseEvent) {
  const target = targetOf(e);
  if (!target || RecorderIsland.isOwnEvent(e.target)) return;
  flushPendingFill();
  send(step("right_click", target, null));
}

/**
 * Selector for a checkbox or radio, taken *before* it is toggled.
 *
 * By the time `change` fires the app has already reacted — TodoMVC adds
 * `completed` to the row, tabs mark themselves `active`. A selector built then
 * describes the post-click DOM, which replay cannot match because that state
 * only exists after the click it is trying to perform.
 */
let toggleSelector: {
  element: Element;
  selector: string;
  strategy: string;
  meta: string | null;
} | null = null;

function rememberToggleTarget(e: Event) {
  const target = targetOf(e);
  if (!target || !isToggle(target) || RecorderIsland.isOwnEvent(e.target))
    return;
  const { selector, strategy } = generateSelector(target);
  toggleSelector = {
    element: target,
    selector,
    strategy,
    meta: fingerprintElement(target),
  };
}

function handleChange(e: Event) {
  const target = targetOf(e);
  if (!target || RecorderIsland.isOwnEvent(e.target)) return;

  if (isToggle(target)) {
    flushPendingFill();
    const action = target.checked ? "check" : "uncheck";
    const before = toggleSelector?.element === target ? toggleSelector : null;
    toggleSelector = null;
    send(
      before
        ? {
            order_index: -1,
            action,
            selector: before.selector,
            selector_strategy: before.strategy,
            value: null,
            frame_url: FRAME_URL,
            element_meta: before.meta,
          }
        : step(action, target, null),
    );
    return;
  }
  if (target instanceof HTMLSelectElement) {
    flushPendingFill();
    // A multi-select carries every chosen option; the runner splits on "||".
    const chosen = Array.from(target.selectedOptions).map((o) => o.value);
    send(
      step(
        "select",
        target,
        target.multiple ? chosen.join("||") : target.value,
      ),
    );
    return;
  }
  if (target instanceof HTMLInputElement && target.type === "file") {
    // File contents cannot leave the page; record the step so it is visible
    // in the editor, and let the user point it at a path the runner can read.
    send(
      step(
        "upload",
        target,
        Array.from(target.files ?? [])
          .map((f) => f.name)
          .join(", "),
      ),
    );
    return;
  }
  if (isTextEntry(target)) recordTypedValue(target);
}

/**
 * The value a text field settled on, when the tester typed it and nothing has
 * recorded it yet.
 *
 * Only a value still in the buffer is unrecorded. A field submitted with Enter
 * was flushed by that key, and the `change` the browser fires when it later
 * loses focus is confirming that same text rather than new typing - it is what
 * put a duplicate fill after every send.
 */
function recordTypedValue(target: Element) {
  if (pendingFill?.element !== target) return;
  pendingFill = {
    element: target,
    value: (target as HTMLInputElement).value,
  };
  flushPendingFill();
}

const RECORDED_KEYS = new Set([
  "Enter",
  "Tab",
  "Escape",
  "Backspace",
  "Delete",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "PageUp",
  "PageDown",
  "Home",
  "End",
]);

// Editing shortcuts inside a text field. What they produce is already in the
// field, and the fill step carries it. Replaying them instead would paste
// whatever the clipboard happens to hold at the time - a value copied earlier
// in the run, or something from outside it altogether.
const EDITING_KEYS = new Set(["a", "c", "v", "x", "z", "y"]);

function keyCombo(e: KeyboardEvent): string | null {
  const modifiers: string[] = [];
  if (e.ctrlKey) modifiers.push("Control");
  if (e.metaKey) modifiers.push("Meta");
  if (e.altKey) modifiers.push("Alt");
  if (e.shiftKey && (RECORDED_KEYS.has(e.key) || modifiers.length))
    modifiers.push("Shift");

  // A bare printable key is part of typing and already covered by `fill`.
  if (!modifiers.length && !RECORDED_KEYS.has(e.key)) return null;
  if (modifiers.length && e.key.length === 1)
    return [...modifiers, e.key.toUpperCase()].join("+");
  if (!RECORDED_KEYS.has(e.key)) return null;
  return [...modifiers, e.key].join("+");
}

function isEditingShortcut(e: KeyboardEvent, target: Element | null): boolean {
  if (!target || !isTextEntry(target)) return false;
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return false;
  return EDITING_KEYS.has(e.key.toLowerCase());
}

function handleKeyDown(e: KeyboardEvent) {
  const combo = keyCombo(e);
  if (!combo) return;
  const target = targetOf(e);
  if (RecorderIsland.isOwnEvent(e.target)) return;
  if (isEditingShortcut(e, target)) return;
  // The typing that led up to this key has to be replayed before it.
  flushPendingFill();
  send(
    step(
      "press_key",
      target && target !== document.body ? target : null,
      combo,
    ),
  );
}

let dragSource: Element | null = null;

function handleDragStart(e: DragEvent) {
  dragSource = targetOf(e);
}

function handleDrop(e: DragEvent) {
  const target = targetOf(e);
  const source = dragSource;
  dragSource = null;
  if (!source || !target) return;

  // The runner resolves the drop target with the source's strategy, so the
  // pair has to agree. Plain CSS describes almost anything, so fall back to it
  // rather than dropping the step.
  const from = generateSelector(source);
  const to = generateSelector(target);
  if (from.strategy === to.strategy) {
    send({
      order_index: -1,
      action: "drag",
      selector: from.selector,
      selector_strategy: from.strategy,
      value: to.selector,
      frame_url: FRAME_URL,
      element_meta: fingerprintElement(source),
    });
    return;
  }

  const fromCss = generateCssSelector(source);
  const toCss = generateCssSelector(target);
  if (!fromCss || !toCss) return;
  send({
    order_index: -1,
    action: "drag",
    selector: fromCss,
    selector_strategy: "css",
    value: toCss,
    frame_url: FRAME_URL,
    element_meta: fingerprintElement(source),
  });
}

/**
 * Hovering is only worth recording when the page reacts to it.
 *
 * Menus, tooltips and row actions appear on hover and are clicked next, so a
 * replay that skips the hover cannot reach them. Recording every mouseover
 * would bury the test in noise, so a hover is kept only when the pointer rests
 * on an element and the DOM changes while it does.
 */
let lastMutationAt = 0;
let hoverTimer: number | null = null;
let lastHoverSelector = "";
/** What the last recorded hover was made on, to spot a mouse merely in transit. */
let hoveredElement: Element | null = null;

/**
 * Was the last hover made on the element this step acts on?
 *
 * Only then is it safe to drop: Playwright hovers an element before acting on
 * it anyway. A hover on something further out may be what reveals this element
 * in the first place, so it has to survive.
 */
function isHoverOnSameTarget(element: Element): boolean {
  return (
    !!hoveredElement &&
    (hoveredElement === element || element.contains(hoveredElement))
  );
}

const mutationWatcher =
  typeof MutationObserver !== "undefined"
    ? new MutationObserver((records) => {
        lastMutationAt = Date.now();
        for (const record of records) {
          for (const node of record.addedNodes) {
            if (node instanceof Element) appearedAt.set(node, lastMutationAt);
          }
        }
      })
    : null;

const HOVER_DWELL_MS = 450;
// How recently an element must have appeared for a hover to be what revealed
// it. Long enough for a slow menu, short enough not to blame an old hover.
const REVEAL_WINDOW_MS = 5000;
/** When each element was added to the page, for spotting what a hover revealed. */
const appearedAt = new WeakMap<Element, number>();
/** When the pointer entered each element it is currently inside. */
const pointerEnteredAt = new WeakMap<Element, number>();
/**
 * The element under the pointer and everything above it.
 *
 * `:hover` would say the same thing, but it never matches when the mouse is
 * driven programmatically - including by Rewind's own replay - so the state is
 * kept here instead.
 */
let pointerPath: Element[] = [];

function notePointer(target: Element) {
  const now = Date.now();
  const path: Element[] = [];
  for (let node: Element | null = target; node; node = node.parentElement) {
    path.push(node);
  }
  const before = new Set(pointerPath);
  for (const node of path) {
    if (!before.has(node)) pointerEnteredAt.set(node, now);
  }
  pointerPath = path;
}

function appearedWithinWindow(element: Element, cutoff: number): boolean {
  const at = appearedAt.get(element);
  return at !== undefined && at >= cutoff;
}

/**
 * The element whose hover brought `target` into being, if one did.
 *
 * A menu built on `mouseenter` does not exist until the pointer rests on its
 * parent, and the pointer landing on the new item cancels the dwell that would
 * have recorded that. Replay has to put the pointer back before it can reach
 * anything inside, so the anchor is recorded as a hover of its own.
 */
function hoverAnchorFor(target: Element): Element | null {
  const appeared = appearedAt.get(target);
  if (appeared === undefined || appeared < Date.now() - REVEAL_WINDOW_MS) {
    return null;
  }
  for (
    let node: Element | null = target.parentElement;
    node && node !== document.body;
    node = node.parentElement
  ) {
    if (appearedWithinWindow(node, appeared)) continue; // arrived with the target
    const entered = pointerEnteredAt.get(node);
    // The pointer has to have been resting here *before* the target appeared,
    // otherwise something else - a slow fetch, say - put it on the page.
    if (!pointerPath.includes(node) || entered === undefined) return null;
    return entered <= appeared ? node : null;
  }
  return null;
}

/** Record the hover that revealed `target`, when one is needed and missing. */
function sendRevealHover(target: Element) {
  const anchor = hoverAnchorFor(target);
  if (!anchor) return;
  const located = generateSelector(anchor);
  if (located.selector === lastHoverSelector) return;
  lastHoverSelector = located.selector;
  hoveredElement = anchor;
  send({
    order_index: -1,
    action: "hover",
    selector: located.selector,
    selector_strategy: located.strategy,
    value: null,
    frame_url: FRAME_URL,
    element_meta: fingerprintElement(anchor),
  });
}

function handleMouseOver(e: MouseEvent) {
  const target = targetOf(e);
  if (!target || picking || RecorderIsland.isOwnEvent(e.target)) return;
  notePointer(target);
  if (isTextEntry(target) || isToggle(target)) return;

  if (hoverTimer !== null) window.clearTimeout(hoverTimer);
  const enteredAt = Date.now();
  hoverTimer = window.setTimeout(() => {
    hoverTimer = null;
    if (!target.isConnected || lastMutationAt < enteredAt) return;
    // The pointer has to still be here; `:hover` cannot be asked, because it
    // never matches when the mouse is driven programmatically.
    if (!pointerPath.includes(target)) return;
    const located = generateSelector(target);
    if (located.selector === lastHoverSelector) return;
    lastHoverSelector = located.selector;
    hoveredElement = target;
    send({
      order_index: -1,
      action: "hover",
      selector: located.selector,
      selector_strategy: located.strategy,
      value: null,
      frame_url: FRAME_URL,
      element_meta: fingerprintElement(target),
    });
  }, HOVER_DWELL_MS);
}

/**
 * Scroll position, for the window and for any scrollable container.
 *
 * A regression that only shows below the fold, or inside a virtualised list,
 * is invisible to a replay that never scrolls there. Only the resting position
 * is kept - not every frame of the gesture.
 */
const scrollTimers = new Map<EventTarget, number>();
const lastScroll = new Map<EventTarget, string>();

function handleScroll(e: Event) {
  const target = e.target;
  if (!target || picking) return;
  if (target instanceof Element && RecorderIsland.isOwnEvent(target)) return;

  const existing = scrollTimers.get(target);
  if (existing !== undefined) window.clearTimeout(existing);

  scrollTimers.set(
    target,
    window.setTimeout(() => {
      scrollTimers.delete(target);

      const isWindow =
        target === document ||
        target === document.documentElement ||
        target === window;
      const x = Math.round(
        isWindow ? window.scrollX : (target as Element).scrollLeft,
      );
      const y = Math.round(
        isWindow ? window.scrollY : (target as Element).scrollTop,
      );
      const offset = `${x},${y}`;
      if (lastScroll.get(target) === offset) return;
      lastScroll.set(target, offset);

      if (isWindow) {
        send(step("scroll", null, offset));
        return;
      }
      const element = target as Element;
      if (!element.isConnected) return;
      send(step("scroll", element, offset));
    }, 400),
  );
}

function attachListeners() {
  if (listenersAttached) return;
  listenersAttached = true;
  // Both precede the state change a `change` event reports.
  document.addEventListener("pointerdown", rememberToggleTarget, true);
  document.addEventListener("keydown", rememberToggleTarget, true);
  document.addEventListener("input", handleInput, true);
  document.addEventListener("click", handleClick, true);
  document.addEventListener("dblclick", handleDblClick, true);
  document.addEventListener("contextmenu", handleContextMenu, true);
  document.addEventListener("change", handleChange, true);
  document.addEventListener("keydown", handleKeyDown, true);
  document.addEventListener("dragstart", handleDragStart, true);
  document.addEventListener("drop", handleDrop, true);
  document.addEventListener("mouseover", handleMouseOver, true);
  document.addEventListener("mousemove", handlePickMove, true);
  // Capturing on window catches container scrolls too: scroll does not bubble,
  // but it does travel down through the capture phase.
  window.addEventListener("scroll", handleScroll, true);
  // A form that navigates on submit would otherwise take the typing with it.
  window.addEventListener("beforeunload", flushPendingFill, true);
  mutationWatcher?.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
  });
}

// -------------------------------------------------------------- exit checks

/** Checks worth offering first, given what the user actually clicked. */
function suggestFor(element: Element): {
  suggested: string[];
  defaultKey: string;
  expected: string;
} {
  const tag = element.tagName.toLowerCase();

  if (element instanceof HTMLSelectElement) {
    const label = element.selectedOptions[0]?.textContent?.trim() ?? "";
    return {
      suggested: [
        "selected_label_equals",
        "selected_value_equals",
        "option_count_equals",
        "visible",
      ],
      defaultKey: "selected_label_equals",
      expected: label,
    };
  }
  if (
    element instanceof HTMLInputElement &&
    ["checkbox", "radio"].includes(element.type)
  ) {
    return {
      suggested: ["checked", "unchecked", "enabled", "disabled"],
      defaultKey: element.checked ? "checked" : "unchecked",
      expected: "",
    };
  }
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement
  ) {
    return {
      suggested: [
        "value_equals",
        "value_not_empty",
        "value_contains",
        "value_length_at_least",
        "editable",
      ],
      defaultKey: "value_equals",
      expected: element.value ?? "",
    };
  }
  if (["button", "a"].includes(tag)) {
    return {
      suggested: [
        "visible",
        "enabled",
        "disabled",
        "text_equals",
        "text_contains",
      ],
      defaultKey: "visible",
      expected: (element.textContent || "").trim().slice(0, 80),
    };
  }
  return {
    suggested: [
      "text_contains",
      "text_equals",
      "visible",
      "hidden",
      "exists",
      "count_equals",
    ],
    defaultKey: "text_contains",
    expected: (element.textContent || "").trim().slice(0, 80),
  };
}

function highlight(): HTMLElement {
  let node = document.getElementById(HIGHLIGHT_ID);
  if (node) return node;
  node = document.createElement("div");
  node.id = HIGHLIGHT_ID;
  // pointer-events:none keeps it out of every event path, so it can never be
  // mistaken for the element the user is aiming at.
  node.style.cssText =
    "position:fixed;z-index:2147483646;pointer-events:none;border:2px solid #7c3aed;" +
    "background:rgba(124,58,237,0.10);border-radius:4px;transition:all 60ms ease;display:none";
  (document.body ?? document.documentElement).appendChild(node);
  return node;
}

function handlePickMove(e: MouseEvent) {
  if (!picking) return;
  // Ownership is judged on the retargeted `e.target`: the composed path points
  // inside the island's shadow root, where the id no longer matches.
  if (RecorderIsland.isOwnEvent(e.target)) return;
  const target = targetOf(e);
  if (!target) return;
  const box = target.getBoundingClientRect();
  const node = highlight();
  node.style.display = "block";
  node.style.top = `${box.top}px`;
  node.style.left = `${box.left}px`;
  node.style.width = `${box.width}px`;
  node.style.height = `${box.height}px`;
}

/**
 * Pick mode is tab-wide, not frame-wide.
 *
 * The island lives in the top frame, but in a product that streams its UI into
 * an iframe the element being checked is in another document entirely. The
 * service worker therefore holds the mode and the picked target, and every
 * frame reads them from the shared status.
 */
function startPick() {
  chrome.runtime.sendMessage({ type: "SET_PICKING", picking: true });
  paint({ picking: true, pending: null, error: "" });
}

function cancelPick() {
  chrome.runtime.sendMessage({ type: "SET_PICKING", picking: false });
  clearHighlight();
  paint({ picking: false, pending: null });
}

function clearHighlight() {
  const node = document.getElementById(HIGHLIGHT_ID);
  if (node) node.style.display = "none";
}

function choosePickTarget(element: Element) {
  const located = generateSelector(element);
  const { suggested, defaultKey, expected } = suggestFor(element);
  picking = false;
  clearHighlight();
  chrome.runtime.sendMessage({
    type: "PICK_TARGET",
    target: {
      description: describeElement(element),
      selector: located.selector,
      strategy: located.strategy,
      suggested,
      defaultKey,
      defaultExpected: expected,
      frameUrl: FRAME_URL,
      elementMeta: fingerprintElement(element),
    },
  });
}

function addCheck(draft: CheckDraft) {
  if (!pending) return;
  const spec = assertions.find((a) => a.key === draft.assertionType);
  const target = pending;
  chrome.runtime.sendMessage({ type: "SET_PICKING", picking: false });

  chrome.runtime.sendMessage({
    type: "RECORD_STEP",
    step: {
      order_index: -1,
      action: "assert",
      // Page-level checks (URL, title) do not belong to an element.
      selector: spec && !spec.needs_selector ? "" : target.selector,
      selector_strategy: target.strategy,
      value: draft.param || null,
      assertion_type: draft.assertionType,
      expected_value: spec && !spec.needs_expected ? null : draft.expected,
      is_exit_criteria: draft.isExitCriteria,
      // A check on an element inside a frame has to be replayed there too.
      frame_url:
        spec && !spec.needs_selector ? null : (target.frameUrl ?? null),
      element_meta:
        spec && !spec.needs_selector ? null : (target.elementMeta ?? null),
    } satisfies RecordedStep,
  });
  paint({
    pending: null,
    picking: false,
    lastStep: `check ${spec?.label ?? draft.assertionType}`,
  });
}

// ------------------------------------------------------------------ session

/** localStorage for this origin, in Playwright storage_state shape. */
function readLocalStorage(): { name: string; value: string }[] {
  try {
    return Object.keys(localStorage).map((name) => ({
      name,
      value: localStorage.getItem(name) ?? "",
    }));
  } catch {
    return []; // Blocked by the page's storage policy.
  }
}

function stopRecording() {
  flushPendingFill(); // Whatever was typed last still belongs in the recording.
  paint({ saving: true, error: "" });
  
  let callbackFired = false;
  const messageTimeout = setTimeout(() => {
    if (!callbackFired) {
      callbackFired = true;
      paint({
        saving: false,
        error: "Recording save timed out. Please try again.",
      });
    }
  }, 10000); // 10 second timeout
  
  chrome.runtime.sendMessage(
    {
      type: "STOP_RECORDING",
      origin: location.origin,
      localStorage: readLocalStorage(),
    },
    (response) => {
      if (callbackFired) return;
      callbackFired = true;
      clearTimeout(messageTimeout);
      
      if (chrome.runtime.lastError || !response?.success) {
        paint({
          saving: false,
          error: response?.error || "Could not save — is the backend running?",
        });
        return;
      }
      teardown();
    },
  );
}

function teardown() {
  isRecording = false;
  picking = false;
  pending = null;
  mutationWatcher?.disconnect();
  document.getElementById(HIGHLIGHT_ID)?.remove();
  if (hostsIsland) island.unmount();
  hostsIsland = false;
}

// ------------------------------------------------------- island ownership

/**
 * Ask the service worker whether this frame should draw the island.
 *
 * The top frame wins whenever it has a body to draw into. Products that still
 * use a frameset for their shell have no such body, so the largest frame that
 * does takes over - the controls stay reachable on any site, without the page
 * having to cooperate.
 */
function claimIsland() {
  if (hostsIsland || !isRecording) return;
  try {
    chrome.runtime.sendMessage(
      {
        type: "CLAIM_ISLAND",
        isTop: IS_TOP_FRAME,
        hasBody: !!RecorderIsland.drawableBody(),
        area: window.innerWidth * window.innerHeight,
      },
      (reply) => {
        if (chrome.runtime.lastError || !reply?.host) return;
        hostsIsland = true;
        island.mount();
      },
    );
  } catch {
    // Extension context invalidated.
  }
}

function releaseIsland() {
  if (!hostsIsland) return;
  hostsIsland = false;
  island.unmount();
}

// ------------------------------------------------------------------- status

function applyStatus(status: any) {
  if (!status?.isRecording && !status?.isSaving) {
    if (isRecording) teardown();
    isRecording = false;
    return;
  }

  isRecording = true;
  paused = !!status.paused;
  appOrigin = status.appOrigin || "";
  // Off the app's own origin the user is at an identity provider. Nothing is
  // recorded there: no credentials, no IdP-specific clicks. The session cookie
  // it produces is captured at the end instead.
  authPaused = !!appOrigin && location.origin !== appOrigin;
  if (Array.isArray(status.assertions) && status.assertions.length) {
    assertions = status.assertions;
  }

  // Pick mode and the picked element are tab-wide: the click can land in one
  // frame while the island that shows the form lives in another.
  picking = !!status.picking;
  pending = status.pendingCheck ?? null;
  if (!picking) clearHighlight();

  attachListeners();
  claimIsland();
  paint({
    stepCount: status.stepCount ?? 0,
    startedAt: status.startedAt ?? null,
    paused,
    authPaused,
    saving: !!status.isSaving,
    picking,
    pending,
    assertions,
  });
}

function pollStatus() {
  try {
    chrome.runtime.sendMessage(
      { type: "GET_STATUS", needAssertions: assertions.length === 0 },
      (status) => {
        if (chrome.runtime.lastError) return;
        applyStatus(status);
      },
    );
  } catch {
    // Extension context invalidated (reload/update).
  }
}

/**
 * The dashboard runs in a normal page and cannot reach the service worker, so
 * it posts to its own window and this script relays it. Only the dashboard's
 * own origin is trusted: this script runs on every site.
 */
function handleWindowMessage(event: MessageEvent) {
  if (event.source !== window) return;
  if (!DASHBOARD_ORIGINS.includes(event.origin)) return;

  if (event.data?.type === "REWIND_PING") {
    // Proof for the dashboard that the extension is installed *and* present in
    // this tab, so it can say so instead of failing silently.
    window.postMessage({ type: "REWIND_PONG" }, event.origin);
    return;
  }

  if (event.data?.type !== "START_RECORDING_FROM_APP") return;

  const origin = event.origin;
  chrome.runtime.sendMessage(
    {
      type: "START_RECORDING",
      projectId: event.data.projectId,
      sessionToken: event.data.sessionToken,
      startUrl: event.data.startUrl || "",
    },
    (response) => {
      window.postMessage(
        {
          type: "REWIND_RECORDING_STARTED",
          ok: !chrome.runtime.lastError && !!response?.success,
          error: chrome.runtime.lastError?.message || response?.error || "",
        },
        origin,
      );
    },
  );
}

function bootstrap() {
  if (window.__rewindRecorderLoaded) return;
  window.__rewindRecorderLoaded = true;

  // The dashboard relay only makes sense in the page the user is looking at.
  if (IS_TOP_FRAME) window.addEventListener("message", handleWindowMessage);

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "STATUS_CHANGED") applyStatus(message.status);
    // A better-placed frame took the island over.
    if (message.type === "ISLAND_HOST" && !message.host) releaseIsland();
  });

  pollStatus();
  setInterval(pollStatus, 1000);
}

bootstrap();
