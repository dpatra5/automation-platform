/**
 * The floating recorder island.
 *
 * Injected into the page being recorded so the session is always visible and
 * always stoppable, without hunting for the extension icon. Lives in a shadow
 * root so the host page's CSS cannot restyle or hide it, and carries a marker
 * attribute the event capture uses to ignore its own clicks.
 *
 * Built without `innerHTML` and styled through a constructed stylesheet: pages
 * that set `require-trusted-types-for 'script'` throw on innerHTML, and pages
 * with a strict `style-src` drop an injected <style> element. Either one would
 * leave the user recording with no way to stop.
 */

import type { AssertionOption, PickedTarget } from "./types";

export const ISLAND_ID = "rewind-recorder-island";

/**
 * An element the user picked, waiting for a check to be chosen for it.
 *
 * Held by the service worker rather than the frame that picked it: in an app
 * that streams its UI into an iframe, the element and the island that shows
 * this form live in different documents.
 */
export type PendingCheck = PickedTarget;

export interface CheckDraft {
  assertionType: string;
  expected: string;
  param: string;
  isExitCriteria: boolean;
}

export interface IslandState {
  stepCount: number;
  startedAt: number | null;
  paused: boolean;
  /** On an identity provider or login page: capture is suspended. */
  authPaused: boolean;
  lastStep: string;
  saving: boolean;
  error: string;
  /** Waiting for the user to click the element they want to check. */
  picking: boolean;
  pending: PendingCheck | null;
  assertions: AssertionOption[];
}

export interface IslandHandlers {
  onPauseToggle: () => void;
  onStop: () => void;
  /** Enter or leave "click the element you want to check" mode. */
  onTogglePick: () => void;
  onAddCheck: (draft: CheckDraft) => void;
  onCancelCheck: () => void;
}

const STYLES = `
:host { all: initial; }
.shell {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  z-index: 2147483647;
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  font: 500 13px/1.3 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1e293b;
}
.wrap {
  display: flex; align-items: center; gap: 14px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.16);
  backdrop-filter: blur(8px);
  user-select: none;
}
.wrap.paused { background: rgba(254, 252, 232, 0.97); border-color: #fde68a; }
.wrap.auth   { background: rgba(239, 246, 255, 0.97); border-color: #bfdbfe; }
.wrap.picking { background: rgba(245, 243, 255, 0.98); border-color: #ddd6fe; }
.dot {
  width: 9px; height: 9px; border-radius: 50%; background: #ef4444; flex: none;
  animation: pulse 1.4s ease-in-out infinite;
}
.wrap.paused .dot { background: #d97706; animation: none; }
.wrap.auth .dot { background: #2563eb; animation: none; }
.wrap.picking .dot { background: #7c3aed; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.25; } }
.label { font-weight: 600; letter-spacing: 0.01em; white-space: nowrap; }
.timer { font-variant-numeric: tabular-nums; color: #475569; min-width: 42px; }
.count { color: #475569; white-space: nowrap; }
.last {
  color: #64748b; max-width: 190px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; font-weight: 400;
}
.sep { width: 1px; height: 18px; background: #e2e8f0; flex: none; }
button {
  font: inherit; font-weight: 600; cursor: pointer;
  border-radius: 999px; padding: 6px 14px; border: 1px solid transparent;
  transition: background 120ms ease, color 120ms ease;
  /* "Add check" becomes "Cancel check" in place; wrapping would make the pill
     taller and jump the whole island. */
  white-space: nowrap; flex: none;
  min-width: fit-content; line-height: 1.3; box-sizing: border-box;
}
button:disabled { opacity: 0.55; cursor: default; }
.check { background: #ede9fe; color: #6d28d9; border-color: #ddd6fe; }
.check:hover:not(:disabled) { background: #ddd6fe; }
.pause { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
.pause:hover:not(:disabled) { background: #e2e8f0; }
.stop { background: #ef4444; color: #fff; }
.stop:hover:not(:disabled) { background: #dc2626; }
.err { color: #b91c1c; max-width: 220px; font-weight: 500; }

.panel {
  width: min(460px, calc(100vw - 32px));
  background: #fff; border: 1px solid #e2e8f0; border-radius: 16px;
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.18);
  padding: 14px 16px; display: none; flex-direction: column; gap: 10px;
  max-height: 60vh; overflow: auto;
}
.panel.open { display: flex; }
.panel h4 { margin: 0; font-size: 13px; font-weight: 700; }
.target {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; color: #475569; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 8px;
  word-break: break-all;
}
.row { display: flex; flex-direction: column; gap: 4px; }
.row label { font-size: 11px; font-weight: 600; color: #64748b; }
select, input[type="text"] {
  font: inherit; width: 100%; box-sizing: border-box;
  padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 9px;
  background: #fff; color: #0f172a;
}
select:focus, input[type="text"]:focus { outline: 2px solid #a5b4fc; outline-offset: -1px; }
.hint { font-size: 11px; color: #94a3b8; font-weight: 400; }
.toggle { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #334155; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.add { background: #4f46e5; color: #fff; }
.add:hover:not(:disabled) { background: #4338ca; }
.cancel { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
`;

function formatElapsed(startedAt: number | null): string {
  if (!startedAt) return "0:00";
  const total = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

function el(tag: string, className: string, text = ""): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function field(labelText: string, control: HTMLElement): HTMLElement {
  const row = el("div", "row");
  const label = document.createElement("label");
  label.textContent = labelText;
  row.append(label, control);
  return row;
}

/**
 * Which element a pending check is about, as a value rather than an object.
 *
 * The status poll runs every second and its reply crosses a message boundary,
 * so the pending check arrives as a fresh object each time even when nothing
 * has changed. Comparing by identity made every poll rebuild the form - which
 * closed the open dropdown a second after the user opened it, and threw away
 * whatever they had typed.
 */
function checkKey(pending: PendingCheck | null): string {
  if (!pending) return "";
  return [
    pending.selector,
    pending.strategy,
    pending.frameUrl ?? "",
    pending.defaultKey,
    pending.description,
  ].join("\u0000");
}

/**
 * Write to the DOM only when the value actually differs.
 *
 * The island repaints once a second. Re-assigning a class or a caption that
 * has not changed still counts as a mutation, and a mutation anywhere around
 * an open `<select>` is enough for Chrome to dismiss its popup - which is
 * exactly what the check form did while the user was reading it.
 */
function setText(node: HTMLElement | undefined, text: string) {
  if (node && node.textContent !== text) node.textContent = text;
}

function setClass(node: HTMLElement | undefined, value: string) {
  if (node && node.className !== value) node.className = value;
}

function setDisabled(node: HTMLElement | undefined, disabled: boolean) {
  const button = node as HTMLButtonElement | undefined;
  if (button && button.disabled !== disabled) button.disabled = disabled;
}

export class RecorderIsland {
  private host: HTMLElement | null = null;
  private root: ShadowRoot | null = null;
  private parts: Record<string, HTMLElement> = {};
  private ticker: number | null = null;
  /** Identifies the pending check already drawn, so the form is built once. */
  private drawnKey = "";
  /** What the user has entered so far, so a rebuild cannot discard it. */
  private draft: CheckDraft | null = null;
  private state: IslandState = {
    stepCount: 0,
    startedAt: null,
    paused: false,
    authPaused: false,
    lastStep: "",
    saving: false,
    error: "",
    picking: false,
    pending: null,
    assertions: [],
  };

  constructor(private readonly handlers: IslandHandlers) {}

  /** True when the event came from the island itself, so it must not be recorded. */
  static isOwnEvent(target: EventTarget | null): boolean {
    return target instanceof Element && target.id === ISLAND_ID;
  }

  /**
   * Where the island can actually be drawn.
   *
   * A frameset shell still answers `document.body` - with the `<frameset>`
   * element. Anything appended there is never rendered, so it counts as no
   * body at all and the island goes to a frame that has one.
   */
  static drawableBody(): HTMLElement | null {
    const body = document.body;
    return body && body.localName === "body" ? body : null;
  }

  mount() {
    if (this.host) return;
    const parent = RecorderIsland.drawableBody();
    if (!parent) {
      // Ran before the document had a body; retry once it exists.
      document.addEventListener("DOMContentLoaded", () => this.mount(), {
        once: true,
      });
      return;
    }

    this.host = document.createElement("div");
    this.host.id = ISLAND_ID;
    // Open, so the buttons stay reachable by automation (including Rewind's
    // own end-to-end check). The host page can already see the element either way.
    this.root = this.host.attachShadow({ mode: "open" });
    this.applyStyles(this.root);
    this.root.appendChild(this.build());
    parent.appendChild(this.host);

    // Only the clock needs its own tick; everything else redraws on update().
    this.ticker = window.setInterval(() => this.paint(), 1000);
    this.paint();
  }

  unmount() {
    if (this.ticker !== null) window.clearInterval(this.ticker);
    this.ticker = null;
    this.host?.remove();
    this.host = null;
    this.root = null;
    this.parts = {};
    this.drawnKey = "";
    this.draft = null;
  }

  get isMounted(): boolean {
    return this.host !== null && this.host.isConnected;
  }

  update(next: Partial<IslandState>) {
    this.state = { ...this.state, ...next };
    // Single-page apps can wipe the body out from under us. Put the same host
    // back rather than building a new one: rebuilding would take the open
    // check form - and whatever the user had typed into it - with it.
    if (this.host && !this.host.isConnected) this.reattach();
    if (!this.host) this.mount();
    this.paint();
  }

  /** Re-append the existing island after the page replaced its body. */
  private reattach() {
    const parent = RecorderIsland.drawableBody();
    if (parent && this.host) parent.appendChild(this.host);
    else this.unmount();
  }

  private applyStyles(root: ShadowRoot) {
    // Constructed stylesheets bypass the page's style-src CSP entirely.
    if (
      typeof CSSStyleSheet !== "undefined" &&
      "replaceSync" in CSSStyleSheet.prototype
    ) {
      try {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(STYLES);
        root.adoptedStyleSheets = [sheet];
        return;
      } catch {
        // Fall through to a style element.
      }
    }
    const style = document.createElement("style");
    style.textContent = STYLES;
    root.appendChild(style);
  }

  private build(): HTMLElement {
    const shell = el("div", "shell");
    const wrap = el("div", "wrap");

    this.parts = {
      shell,
      wrap,
      dot: el("span", "dot"),
      label: el("span", "label"),
      timer: el("span", "timer"),
      count: el("span", "count"),
      last: el("span", "last"),
      err: el("span", "err"),
      check: el("button", "check", "Add check"),
      pause: el("button", "pause"),
      stop: el("button", "stop", "Stop"),
      panel: el("div", "panel"),
    };

    for (const name of ["check", "pause", "stop"]) {
      (this.parts[name] as HTMLButtonElement).type = "button";
      this.parts[name].setAttribute("data-rewind", name);
    }
    this.parts.check.addEventListener("click", () =>
      this.handlers.onTogglePick(),
    );
    this.parts.pause.addEventListener("click", () =>
      this.handlers.onPauseToggle(),
    );
    this.parts.stop.addEventListener("click", () => this.handlers.onStop());

    wrap.append(
      this.parts.dot,
      this.parts.label,
      this.parts.timer,
      el("span", "sep"),
      this.parts.count,
      this.parts.last,
      this.parts.err,
      el("span", "sep"),
      this.parts.check,
      this.parts.pause,
      this.parts.stop,
    );
    shell.append(this.parts.panel, wrap);
    return shell;
  }

  // ------------------------------------------------------------ check form

  private buildPanel(pending: PendingCheck) {
    const panel = this.parts.panel;
    panel.replaceChildren();
    const draft = this.draft;

    const select = document.createElement("select");
    select.setAttribute("data-rewind", "check-type");
    this.fillChecks(select, pending);
    if (draft?.assertionType) select.value = draft.assertionType;

    const expected = document.createElement("input");
    expected.type = "text";
    expected.setAttribute("data-rewind", "check-expected");
    expected.value = draft ? draft.expected : pending.defaultExpected;

    const param = document.createElement("input");
    param.type = "text";
    param.setAttribute("data-rewind", "check-param");
    param.value = draft?.param ?? "";

    const expectedRow = field("Expected value", expected);
    const paramRow = field("Extra detail", param);
    const hint = el("div", "hint");

    const exitToggle = document.createElement("input");
    exitToggle.type = "checkbox";
    exitToggle.checked = draft ? draft.isExitCriteria : true;
    exitToggle.setAttribute("data-rewind", "check-exit");
    const toggleRow = el("label", "toggle");
    toggleRow.append(
      exitToggle,
      document.createTextNode("Check at the end of the run"),
    );

    const add = el("button", "add", "Add check") as HTMLButtonElement;
    const cancel = el("button", "cancel", "Cancel") as HTMLButtonElement;
    add.type = "button";
    cancel.type = "button";
    add.setAttribute("data-rewind", "check-add");
    cancel.setAttribute("data-rewind", "check-cancel");
    const actions = el("div", "actions");
    actions.append(cancel, add);

    const read = (): CheckDraft => ({
      assertionType: select.value,
      expected: expected.value,
      param: param.value,
      isExitCriteria: exitToggle.checked,
    });
    // Held outside the DOM as well: the island is redrawn whenever the page
    // it is pinned to replaces its body, and losing a half-filled form to
    // that is indistinguishable from the recorder throwing the input away.
    const remember = () => {
      this.draft = read();
    };

    const refresh = () => {
      const spec = this.state.assertions.find((a) => a.key === select.value);
      expectedRow.style.display =
        !spec || spec.needs_expected ? "flex" : "none";
      paramRow.style.display = spec?.param_label ? "flex" : "none";
      (paramRow.firstElementChild as HTMLElement).textContent =
        spec?.param_label || "Extra detail";
      (expectedRow.firstElementChild as HTMLElement).textContent =
        spec?.expected_label || "Expected value";
      hint.textContent = spec?.hint || "";
    };

    select.addEventListener("change", () => {
      remember();
      refresh();
    });
    for (const input of [expected, param]) {
      input.addEventListener("input", remember);
    }
    exitToggle.addEventListener("change", remember);
    cancel.addEventListener("click", () => this.handlers.onCancelCheck());
    add.addEventListener("click", () => this.handlers.onAddCheck(read()));

    panel.append(
      el("h4", "", "What should be true here?"),
      el("div", "target", pending.description || pending.selector),
      field("Check", select),
      hint,
      expectedRow,
      paramRow,
      toggleRow,
      actions,
    );
    refresh();
    remember();
  }

  /** Group the catalogue, with the checks that suit this element pinned on top. */
  private fillChecks(select: HTMLSelectElement, pending: PendingCheck) {
    const options = this.state.assertions;
    const byKey = new Map(options.map((o) => [o.key, o]));

    const suggested = pending.suggested
      .map((k) => byKey.get(k))
      .filter((o): o is AssertionOption => !!o);
    if (suggested.length) {
      const group = document.createElement("optgroup");
      group.label = "Suggested for this element";
      for (const option of suggested)
        group.append(new Option(option.label, option.key));
      select.append(group);
    }

    const groups = new Map<string, AssertionOption[]>();
    for (const option of options) {
      if (!groups.has(option.group)) groups.set(option.group, []);
      groups.get(option.group)!.push(option);
    }
    for (const [name, entries] of groups) {
      const group = document.createElement("optgroup");
      group.label = name;
      for (const option of entries)
        group.append(new Option(option.label, option.key));
      select.append(group);
    }

    select.value =
      pending.defaultKey || suggested[0]?.key || options[0]?.key || "";
  }

  // --------------------------------------------------------------- drawing

  private paint() {
    if (!this.parts.wrap) return;
    const {
      stepCount,
      startedAt,
      paused,
      authPaused,
      lastStep,
      saving,
      error,
      picking,
      pending,
    } = this.state;

    setClass(
      this.parts.wrap,
      `wrap${paused ? " paused" : ""}${authPaused ? " auth" : ""}${picking ? " picking" : ""}`,
    );

    let label = "Recording";
    if (saving) label = "Saving…";
    else if (picking) label = "Click the element to check";
    else if (authPaused) label = "Sign-in page — not recorded";
    else if (paused) label = "Paused";

    setText(this.parts.label, label);
    setText(this.parts.timer, formatElapsed(startedAt));
    setText(this.parts.count, `${stepCount} step${stepCount === 1 ? "" : "s"}`);
    setText(this.parts.last, lastStep);
    setText(this.parts.err, error);

    setText(
      this.parts.check,
      picking || pending ? "Cancel check" : "Add check",
    );
    setDisabled(this.parts.check, saving || authPaused);

    setText(this.parts.pause, paused ? "Resume" : "Pause");
    setDisabled(this.parts.pause, saving || authPaused);
    setDisabled(this.parts.stop, saving);

    this.syncPanel(pending);
  }

  /** Draw the check form once per picked element, and clear it when it goes. */
  private syncPanel(pending: PendingCheck | null) {
    const key = checkKey(pending);
    if (pending && key !== this.drawnKey) {
      // A different element was picked, so the form starts over.
      this.draft = null;
      this.drawnKey = key;
      this.buildPanel(pending);
    } else if (!pending && this.drawnKey) {
      this.drawnKey = "";
      this.draft = null;
      this.parts.panel.replaceChildren();
    }
    setClass(this.parts.panel, `panel${pending ? " open" : ""}`);
  }
}
