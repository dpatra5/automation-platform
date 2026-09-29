import { SelectorStrategy } from "./types";

type SearchRoot = Document | ShadowRoot;

/** The document or shadow root an element actually lives in. */
function rootOf(element: Element): SearchRoot {
  const root = element.getRootNode();
  return root instanceof ShadowRoot ? root : document;
}

function inShadow(element: Element): boolean {
  return element.getRootNode() instanceof ShadowRoot;
}

/** Put on an element to be automated against; the safest thing to match on. */
const TEST_ID_ATTRIBUTES = [
  "data-testid",
  "data-test-id",
  "data-test",
  "data-cy",
  "data-qa",
];

/**
 * Attributes that say what an element is for.
 *
 * Unlike a class list these survive a restyle, and unlike a position they
 * survive the list around them being re-ordered or re-rendered.
 */
const IDENTIFYING_ATTRIBUTES = [
  "aria-label",
  "name",
  "placeholder",
  "title",
  "alt",
  "for",
  "href",
];

function escapeAttr(value: string): string {
  return value.replace(/["\\]/g, (c) => `\\${c}`);
}

/**
 * Ids a framework generated, which differ on the next render.
 *
 * React's `useId` emits `:r0:`, Radix prefixes it, MUI counts upwards, and
 * CSS-in-JS appends a hash - none of them describe the element.
 */
function isStableId(id: string | null | undefined): id is string {
  if (!id || id.length > 100) return false;
  if (/^\d/.test(id) || /\s/.test(id)) return false;
  if (id.includes(":")) return false;
  if (/^(radix|headlessui|mui|chakra|mantine|downshift)[-:]/i.test(id))
    return false;
  if (/-(?:css|sc)-/.test(id)) return false;
  return !/[-_][a-f0-9]{6,}$/i.test(id);
}

// ------------------------------------------------------------------- xpath

/**
 * A value wrapped so XPath 1.0 will accept it.
 *
 * XPath 1.0 has no escape character inside a string literal, so a label
 * containing both kinds of quote has to be assembled with `concat()`. Labels
 * like `Don't "save"` are rare and entirely legal, and a selector that threw
 * when it met one would take the whole step with it.
 */
function xpathLiteral(value: string): string {
  if (!value.includes("'")) return `'${value}'`;
  if (!value.includes('"')) return `"${value}"`;
  const parts = value.split("'").map((part) => `'${part}'`);
  return `concat(${parts.join(`, "'", `)})`;
}

/** Whether an XPath matches exactly one node, and that node is this element. */
function resolvesTo(xpath: string, element: Element): boolean {
  try {
    const result = document.evaluate(
      xpath,
      document,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null,
    );
    return result.snapshotLength === 1 && result.snapshotItem(0) === element;
  } catch {
    return false;
  }
}

/** The element's position among the siblings sharing its tag, and how many. */
function xpathIndex(element: Element): { index: number; of: number } {
  const parent = element.parentElement;
  if (!parent) return { index: 1, of: 1 };
  let index = 1;
  let of = 0;
  for (let sib = parent.firstElementChild; sib; sib = sib.nextElementSibling) {
    if (sib.tagName !== element.tagName) continue;
    of += 1;
    if (sib === element) index = of;
  }
  return { index, of };
}

/** One location step: `button`, or `div[3]` where the tag repeats. */
function xpathStep(element: Element): string {
  const tag = element.tagName.toLowerCase();
  const { index, of } = xpathIndex(element);
  return of > 1 ? `${tag}[${index}]` : tag;
}

// How many predicates one element is worth trying. Every one costs a
// `document.evaluate` over the whole document and this runs on the tester's
// click; past the first few they are attributes that narrow nothing down.
const MAX_PREDICATES = 4;

// How many document-wide lookups the climb for an anchor may spend. Most
// ancestors carry nothing to anchor on and cost nothing; this bounds the ones
// that do, so recording a click never stalls the page the tester is using.
const MAX_ANCHOR_LOOKUPS = 24;

/** `contains(...)` over a class list, the form that survives extra classes. */
function classPredicate(name: string): string {
  return `contains(concat(' ', normalize-space(@class), ' '), ${xpathLiteral(` ${name} `)})`;
}

/** The classes that name what an element is, rather than how it looks. */
function structuralClasses(element: Element): string[] {
  const raw = element.getAttribute("class");
  if (!raw) return [];
  return raw.split(/\s+/).filter(isStructuralClass).slice(0, 2);
}

/** Predicates that say what an element is, the most telling first. */
function xpathPredicates(element: Element): string[] {
  const out: string[] = [];
  for (const attr of TEST_ID_ATTRIBUTES) {
    const value = element.getAttribute(attr);
    if (value) out.push(`@${attr}=${xpathLiteral(value)}`);
  }
  if (isStableId(element.id)) out.push(`@id=${xpathLiteral(element.id)}`);
  for (const attr of IDENTIFYING_ATTRIBUTES) {
    const value = element.getAttribute(attr);
    if (value && value.length <= 100) {
      out.push(`@${attr}=${xpathLiteral(value)}`);
    }
  }
  const role = element.getAttribute("role");
  if (role) out.push(`@role=${xpathLiteral(role)}`);
  const type = element.getAttribute("type");
  if (type) out.push(`@type=${xpathLiteral(type)}`);
  // Last: a class says the least about what an element is, but a container
  // named `custom-scroll` is still a better anchor than counting to it.
  out.push(...structuralClasses(element).map(classPredicate));
  return out.slice(0, MAX_PREDICATES);
}

/** `//button[@id='save']` for an element carrying something to name it by. */
function namedXPath(element: Element): string | null {
  const tag = element.tagName.toLowerCase();
  const predicates = xpathPredicates(element);
  for (const predicate of predicates) {
    const xpath = `//${tag}[${predicate}]`;
    if (resolvesTo(xpath, element)) return xpath;
    // One attribute is often shared - every row's delete button is
    // `@type='button'` - so a second one is asked to settle it.
    for (const other of predicates) {
      if (other === predicate) continue;
      const both = `//${tag}[${predicate} and ${other}]`;
      if (resolvesTo(both, element)) return both;
    }
  }
  return null;
}

// Tags whose visible text is what the tester was aiming at. Text on a `div`
// includes everything nested inside it, so it names the wrapper as readily as
// the control and cannot tell the two apart.
const TEXT_ADDRESSABLE = new Set([
  "BUTTON",
  "A",
  "LABEL",
  "SUMMARY",
  "OPTION",
  "TD",
  "TH",
  "LI",
  "SPAN",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
]);

/** `//button[normalize-space()='Save']`, when the text is the element's own. */
function textXPath(element: Element): string | null {
  if (!TEXT_ADDRESSABLE.has(element.tagName)) return null;
  const text = clean(
    (element as HTMLElement).innerText || element.textContent,
    60,
  );
  if (!text || text.length > 60) return null;
  const tag = element.tagName.toLowerCase();
  for (const xpath of [
    `//${tag}[normalize-space()=${xpathLiteral(text)}]`,
    `//${tag}[normalize-space(text())=${xpathLiteral(text)}]`,
  ]) {
    if (resolvesTo(xpath, element)) return xpath;
  }
  return null;
}

/**
 * The path to an element, anchored on the nearest ancestor that names itself.
 *
 * An absolute path breaks the moment anything wraps the page in one more
 * `div`, which is what a layout change or a framework upgrade does. Climbing
 * until something identifiable is found gives `//div[@id='orders']/tr[3]/td[2]`
 * rather than a chain from `/html`, so only the part that has to count counts.
 *
 * The climb is capped by how many lookups it is allowed, not by depth: most
 * ancestors carry nothing to anchor on and cost nothing to pass, and the
 * element worth anchoring on is often near the root.
 */
function anchoredXPath(element: Element): string {
  const steps: string[] = [];
  let node: Element | null = element;
  let lookups = 0;

  while (node && node.nodeType === Node.ELEMENT_NODE) {
    const tag = node.tagName.toLowerCase();
    if (tag === "html") break;

    for (const predicate of xpathPredicates(node)) {
      if (lookups >= MAX_ANCHOR_LOOKUPS) break;
      lookups += 1;
      const anchor = `//${tag}[${predicate}]`;
      const xpath = steps.length ? `${anchor}/${steps.join("/")}` : anchor;
      if (resolvesTo(xpath, element)) return xpath;
    }

    steps.unshift(xpathStep(node));
    if (tag === "body") break;
    node = node.parentElement;
  }
  return `/html/${steps.join("/")}`;
}

/**
 * The XPath a step is recorded with.
 *
 * Tried in the order a person would read the element: the attribute that
 * exists to identify it, then what it says, then where it sits relative to the
 * nearest thing that identifies itself. The answer is always an XPath, so
 * every step reads the same way and can be pasted straight into the browser's
 * console to see what it picks out.
 */
export function generateXPath(element: Element): string {
  return namedXPath(element) ?? textXPath(element) ?? anchoredXPath(element);
}

export function generateSelector(element: Element): {
  selector: string;
  strategy: SelectorStrategy;
} {
  // XPath cannot cross a shadow boundary, so an element inside a web component
  // is described by the CSS path Playwright pierces open roots with. Everything
  // else is recorded as XPath: one notation for every step, and one the tester
  // can read, paste into the browser's console and check for themselves.
  if (inShadow(element)) {
    return { selector: getStableCssPath(element), strategy: "css" };
  }
  return { selector: generateXPath(element), strategy: "xpath" };
}

function isUnique(selector: string, root: SearchRoot = document): boolean {
  try {
    return root.querySelectorAll(selector).length === 1;
  } catch {
    return false;
  }
}

/**
 * Classes that describe the element's current state rather than what it is.
 *
 * Baking one of these into a selector makes the step unreplayable: a recorded
 * `li.completed > input.toggle` can only be found *after* the click that adds
 * `completed`, which is the click we are trying to replay.
 */
const STATE_CLASS =
  /^(is|has|ui|js)-|^(active|selected|checked|completed|done|open|opened|closed|expanded|collapsed|disabled|enabled|hidden|visible|shown|show|focus|focused|hover|hovered|current|editing|dragging|highlighted|loading|busy|error|invalid|valid|dirty|touched|pending|sticky|scrolled)$/i;

/**
 * Classes that only say how an element looks.
 *
 * A utility framework hands one element dozens of them, and a chain of
 * `rounded-2xl.overflow-hidden.bg-white\/80` breaks on the next restyle while
 * saying nothing about what the element is or does.
 */
const UTILITY_WORDS = new Set([
  "group",
  "peer",
  "container",
  "sr-only",
  "truncate",
  "antialiased",
  "italic",
  "underline",
  "uppercase",
  "lowercase",
  "capitalize",
  "block",
  "flex",
  "grid",
  "table",
  "contents",
  "hidden",
  "absolute",
  "relative",
  "fixed",
  "static",
  "visible",
  "invisible",
  "clearfix",
  "row",
  "col",
]);

const UTILITY_PREFIXES = new Set([
  "p",
  "px",
  "py",
  "pt",
  "pr",
  "pb",
  "pl",
  "m",
  "mx",
  "my",
  "mt",
  "mr",
  "mb",
  "ml",
  "w",
  "h",
  "min",
  "max",
  "size",
  "aspect",
  "columns",
  "text",
  "bg",
  "border",
  "rounded",
  "shadow",
  "outline",
  "ring",
  "divide",
  "gap",
  "space",
  "items",
  "justify",
  "self",
  "place",
  "content",
  "order",
  "col",
  "row",
  "grid",
  "flex",
  "basis",
  "grow",
  "shrink",
  "inline",
  "box",
  "z",
  "opacity",
  "transition",
  "duration",
  "delay",
  "ease",
  "animate",
  "cursor",
  "select",
  "pointer",
  "backdrop",
  "filter",
  "blur",
  "mix",
  "font",
  "leading",
  "tracking",
  "whitespace",
  "break",
  "indent",
  "line",
  "object",
  "align",
  "overflow",
  "inset",
  "top",
  "right",
  "bottom",
  "left",
  "stroke",
  "fill",
  "from",
  "via",
  "to",
  "decoration",
  "caret",
  "accent",
  "scale",
  "rotate",
  "translate",
  "skew",
  "origin",
  "list",
  "float",
  "clear",
  "scroll",
  "snap",
  "touch",
  "will",
  "isolate",
]);

function isStylingClass(name: string): boolean {
  // Variants (`hover:`), opacity (`bg-white/80`) and arbitrary values
  // (`h-[150px]`) are styling by construction.
  if (/[:/[\]()]/.test(name)) return true;
  const lowered = name.toLowerCase();
  return (
    UTILITY_WORDS.has(lowered) || UTILITY_PREFIXES.has(lowered.split("-")[0])
  );
}

function isStructuralClass(name: string): boolean {
  if (!name) return false;
  if (STATE_CLASS.test(name)) return false;
  if (isStylingClass(name)) return false;
  // Auto-generated / hashed class names change on every build.
  if (/^(css|sc)-[a-z0-9]{5,}$/i.test(name)) return false;
  return !name.startsWith("tailwind-");
}

/**
 * A CSS path for the element, crossing shadow boundaries where needed.
 *
 * Playwright's CSS engine pierces open shadow roots on a descendant
 * combinator, so each shadow scope contributes its own `>`-joined path and the
 * scopes are joined with a space. That is what makes a web-component app -
 * and anything built on one - replayable.
 */
function getStableCssPath(element: Element): string {
  let path = pathWithinRoot(element);
  let root = element.getRootNode();

  while (root instanceof ShadowRoot) {
    const host = root.host;
    path = `${pathWithinRoot(host)} ${path}`;
    root = host.getRootNode();
  }
  return path;
}

/** The `>`-joined path to an element within its own document or shadow root. */
function pathWithinRoot(element: Element): string {
  const root = rootOf(element);
  const path: string[] = [];
  let current: Element | null = element;
  let anchored = false;

  while (current && current.nodeType === Node.ELEMENT_NODE) {
    const tag = current.tagName.toLowerCase();

    if (isStableId(current.id)) {
      path.unshift(`${tag}#${CSS.escape(current.id)}`);
      anchored = true;
    } else {
      const identity = identityOf(current);
      // Position is the last resort: it is what breaks when the app re-orders
      // or re-renders the list this element sits in.
      path.unshift(identity ? tag + identity : tag + positionOf(current));
      anchored = anchored || Boolean(identity);
    }

    // Being the only match today is not enough. `div:nth-of-type(16) > div >
    // div` says nothing about where it starts, so on a page that has grown a
    // row it still matches - just something else. Keep climbing until part of
    // the path names an element instead of counting one.
    if (anchored && isUnique(path.join(" > "), root)) return path.join(" > ");

    current = current.parentElement;
  }

  return path.join(" > ");
}

function positionOf(element: Element): string {
  let index = 1;
  let sibling = element.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === element.tagName) index++;
    sibling = sibling.previousElementSibling;
  }
  return index > 1 || element.nextElementSibling
    ? `:nth-of-type(${index})`
    : "";
}

/** What distinguishes an element from its siblings, without styling or position. */
function identityOf(element: Element): string {
  for (const attr of IDENTIFYING_ATTRIBUTES) {
    const value = element.getAttribute(attr);
    if (value && value.length <= 100) {
      return `[${attr}="${escapeAttr(value)}"]`;
    }
  }
  const role = element.getAttribute("role");
  if (role) return `[role="${escapeAttr(role)}"]`;

  if (element.className && typeof element.className === "string") {
    const classes = element.className.split(/\s+/).filter(isStructuralClass);
    if (classes.length > 0) {
      // Escaped per class: utility frameworks emit names containing characters
      // that are selector syntax, such as `w-1/2` or `md:flex`.
      return `.${classes.map((c) => CSS.escape(c)).join(".")}`;
    }
  }
  return "";
}

function getAbsoluteXPath(element: Element): string {
  if (element.tagName === "BODY") {
    return "/html/body";
  }
  if (!element.parentElement) {
    return `/${element.tagName.toLowerCase()}`;
  }

  let index = 1;
  let sibling = element.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === element.tagName) {
      index++;
    }
    sibling = sibling.previousElementSibling;
  }

  const parentPath = getAbsoluteXPath(element.parentElement);
  return `${parentPath}/${element.tagName.toLowerCase()}[${index}]`;
}

/**
 * A selector the runner can resolve with the plain CSS strategy.
 *
 * Drag records a pair - source and drop target - and the runner resolves both
 * with the source's strategy. Forcing both onto CSS is what lets a drag be
 * recorded when the two elements would otherwise be described differently.
 */
export function generateCssSelector(element: Element): string | null {
  for (const attr of ["data-testid", "data-test", "data-cy"]) {
    const val = element.getAttribute(attr);
    if (val) {
      const selector = `[${attr}="${val}"]`;
      if (isUnique(selector, rootOf(element))) return selector;
    }
  }
  const cssPath = getStableCssPath(element);
  return cssPath || null;
}

/** A short, human label for an element, used by the check builder. */
export function describeElement(element: Element): string {
  const tag = element.tagName.toLowerCase();
  const label =
    element.getAttribute("aria-label") ||
    (element as HTMLInputElement).placeholder ||
    element.getAttribute("name") ||
    (element.textContent || "").trim().replace(/\s+/g, " ");
  return label ? `${tag} · ${label.slice(0, 40)}` : tag;
}

// --------------------------------------------------------- what an element is

/**
 * The roles a tag carries without being told, for the tags people click on.
 *
 * Only the ones worth searching by: a role shared by half the page ("generic",
 * "presentation") narrows nothing down and would make the fallback worse than
 * the selector it is standing in for.
 */
const IMPLICIT_ROLES: Record<string, string> = {
  button: "button",
  select: "combobox",
  textarea: "textbox",
  h1: "heading",
  h2: "heading",
  h3: "heading",
  h4: "heading",
  h5: "heading",
  h6: "heading",
  img: "img",
  table: "table",
  ul: "list",
  ol: "list",
  li: "listitem",
  nav: "navigation",
  form: "form",
  dialog: "dialog",
  option: "option",
  progress: "progressbar",
  summary: "button",
};

const INPUT_ROLES: Record<string, string> = {
  button: "button",
  submit: "button",
  reset: "button",
  image: "button",
  checkbox: "checkbox",
  radio: "radio",
  range: "slider",
  number: "spinbutton",
  search: "searchbox",
  email: "textbox",
  tel: "textbox",
  text: "textbox",
  url: "textbox",
  password: "textbox",
};

function clean(value: string | null | undefined, max = 120): string {
  return (value || "").replace(/\s+/g, " ").trim().slice(0, max);
}

/** What the element counts as, the way a screen reader would announce it. */
function roleOf(element: Element): string {
  const explicit = element.getAttribute("role");
  if (explicit) return explicit.trim().split(/\s+/)[0];

  const tag = element.tagName.toLowerCase();
  if (tag === "a") return element.hasAttribute("href") ? "link" : "";
  if (tag === "input") {
    return INPUT_ROLES[(element as HTMLInputElement).type] || "textbox";
  }
  return IMPLICIT_ROLES[tag] || "";
}

/** The text of the `<label>` that names this control, if one does. */
function labelText(element: Element): string {
  const root = rootOf(element);
  if (element.id) {
    const explicit = root.querySelector(
      `label[for="${escapeAttr(element.id)}"]`,
    );
    if (explicit) return clean(explicit.textContent);
  }
  const wrapping = element.closest("label");
  return wrapping ? clean(wrapping.textContent) : "";
}

/** The element's own visible text, without a whole subtree of it. */
function ownText(element: Element): string {
  const text = clean(
    (element as HTMLElement).innerText || element.textContent,
    160,
  );
  return text.length <= 120 ? text : "";
}

/**
 * What the tester would call this element.
 *
 * The same order the accessibility tree uses, so the name recorded here is the
 * one Playwright's `get_by_role(..., name=)` and `get_by_label` will match.
 */
function accessibleName(element: Element): string {
  const aria = clean(element.getAttribute("aria-label"));
  if (aria) return aria;

  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const root = rootOf(element);
    const named = labelledBy
      .split(/\s+/)
      .map((id) => root.getElementById?.(id)?.textContent ?? "")
      .join(" ");
    const text = clean(named);
    if (text) return text;
  }

  const label = labelText(element);
  if (label) return label;

  const attribute = clean(
    element.getAttribute("placeholder") ||
      element.getAttribute("title") ||
      element.getAttribute("alt"),
  );
  if (attribute) return attribute;

  if (element instanceof HTMLInputElement) {
    return ["button", "submit", "reset"].includes(element.type)
      ? clean(element.value)
      : "";
  }
  return ownText(element);
}

/**
 * Whether a peer is worth reading a name off, judged as cheaply as possible.
 *
 * `accessibleName` reaches for `innerText`, which forces layout. Doing that
 * for every div on a busy page is felt as lag while the tester is still
 * clicking, so the obvious misses are dropped on text alone first.
 */
function couldBeNamed(peer: Element, name: string): boolean {
  if (peer.hasAttribute("aria-label") || peer.hasAttribute("aria-labelledby")) {
    return true;
  }
  const text = peer.textContent;
  return !!text && text.length <= 200 && text.includes(name);
}

/**
 * Which of the elements sharing this name and tag it is, and how many there are.
 *
 * Rows of identical controls - a "Delete" per line, a "No" per question - are
 * told apart by nothing else. The total matters as much as the position: a
 * transcript that grows between the recording and the run renumbers them all,
 * but the one that was last is still the one at the end.
 */
function peersNamed(
  element: Element,
  name: string,
): { index: number; of: number } {
  if (!name) return { index: 0, of: 0 };
  try {
    const peers = Array.from(
      rootOf(element).querySelectorAll(element.tagName.toLowerCase()),
    );
    // A chat chip is a div among thousands of divs, so the tag on its own says
    // nothing about how much work this is. What matters is how many share the
    // name, and a position within hundreds of those is not worth trusting.
    if (peers.length > 5000) return { index: 0, of: 0 };
    const named = peers.filter(
      (peer) => couldBeNamed(peer, name) && accessibleName(peer) === name,
    );
    const index = named.indexOf(element);
    if (index < 0 || named.length > 300) return { index: 0, of: 0 };
    return { index, of: named.length };
  } catch {
    return { index: 0, of: 0 };
  }
}

/** How replay can look an element up; mirrors Playwright's locator family. */
export interface FingerprintCandidate {
  by:
    | "test_id"
    | "role"
    | "label"
    | "placeholder"
    | "alt"
    | "title"
    | "text"
    | "css"
    | "xpath";
  value: string;
  /** Only for `role`: the accessible name that narrows it down. */
  name?: string;
}

export interface ElementFingerprint {
  tag: string;
  role?: string;
  name?: string;
  text?: string;
  index?: number;
  /** How many elements shared that name when this was recorded. */
  of?: number;
  candidates: FingerprintCandidate[];
}

function candidatesFor(element: Element): FingerprintCandidate[] {
  const out: FingerprintCandidate[] = [];
  const seen = new Set<string>();
  const push = (candidate: FingerprintCandidate) => {
    const key = `${candidate.by}|${candidate.value}|${candidate.name ?? ""}`;
    if (!candidate.value || seen.has(key)) return;
    seen.add(key);
    out.push(candidate);
  };

  const tag = element.tagName.toLowerCase();

  for (const attr of TEST_ID_ATTRIBUTES) {
    push({ by: "test_id", value: element.getAttribute(attr) || "" });
  }
  if (isStableId(element.id)) {
    push({ by: "css", value: `${tag}#${CSS.escape(element.id)}` });
  }

  const role = roleOf(element);
  const name = accessibleName(element);
  if (role && name) push({ by: "role", value: role, name });

  push({ by: "label", value: clean(element.getAttribute("aria-label")) });
  push({ by: "label", value: labelText(element) });
  push({
    by: "placeholder",
    value: clean(element.getAttribute("placeholder")),
  });
  push({ by: "alt", value: clean(element.getAttribute("alt")) });
  push({ by: "title", value: clean(element.getAttribute("title")) });

  for (const attr of IDENTIFYING_ATTRIBUTES) {
    const value = element.getAttribute(attr);
    if (value && value.length <= 100) {
      push({ by: "css", value: `${tag}[${attr}="${escapeAttr(value)}"]` });
    }
  }

  const text = ownText(element);
  if (text && text.length <= 60) push({ by: "text", value: text });

  push({ by: "css", value: getStableCssPath(element) });
  if (!inShadow(element)) {
    push({ by: "xpath", value: getAbsoluteXPath(element) });
  }
  return out.slice(0, 12);
}

/**
 * What the element is, alongside the selector that says where it was.
 *
 * A recorded path describes the page as it stood: one new wrapper, one extra
 * row, one renamed utility class, and `div:nth-of-type(10) > div` matches
 * nothing - while the control is still on screen and still obvious to whoever
 * is watching the replay. This is what lets the runner find it anyway, and
 * what lets it name the element in an error instead of quoting a path.
 *
 * Returned as JSON so it drops straight into the step's `element_meta`.
 */
export function fingerprintElement(element: Element): string | null {
  try {
    const name = accessibleName(element);
    const text = ownText(element);
    const peers = peersNamed(element, name);
    const meta: ElementFingerprint = {
      tag: element.tagName.toLowerCase(),
      role: roleOf(element) || undefined,
      name: name || undefined,
      text: text && text !== name ? text : undefined,
      index: peers.index || undefined,
      of: peers.of > 1 ? peers.of : undefined,
      candidates: candidatesFor(element),
    };
    return JSON.stringify(meta);
  } catch {
    // A fingerprint is a bonus; never let it cost the step it describes.
    return null;
  }
}
