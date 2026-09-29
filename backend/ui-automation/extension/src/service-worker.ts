import type { AssertionOption, RecordedStep, RecordingState } from "./types";

// Kept local, not imported: see the note in types.ts.
const DASHBOARD_ORIGINS = ["http://localhost:5173", "http://localhost:5174"];
const BACKEND_URL = "http://localhost:8000";

/**
 * Enough of the check catalogue to keep the recorder usable when the backend
 * cannot be reached. The real list is fetched when recording starts, so this
 * only ever shows up offline.
 */
const FALLBACK_ASSERTIONS: AssertionOption[] = [
  ["text_contains", "Text contains", "Text", true, true],
  ["text_equals", "Text is exactly", "Text", true, true],
  ["value_equals", "Value is exactly", "Input value", true, true],
  ["value_not_empty", "Value is not empty", "Input value", true, false],
  ["visible", "Is visible", "State", true, false],
  ["hidden", "Is hidden", "State", true, false],
  ["checked", "Is checked", "State", true, false],
  ["url_contains", "URL contains", "Page", false, true],
].map(([key, label, group, needsSelector, needsExpected]) => ({
  key: key as string,
  label: label as string,
  group: group as string,
  hint: "",
  needs_selector: needsSelector as boolean,
  needs_expected: needsExpected as boolean,
  expected_label: "Expected value",
  param_label: "",
  expected_is_number: false,
}));

const INITIAL_STATE: RecordingState = {
  status: "idle",
  projectId: "",
  sessionToken: "",
  steps: [],
  startUrl: "",
  tabId: null,
  tabIds: [],
  startedAt: null,
  paused: false,
  appOrigin: "",
  visitedHosts: [],
  localStorage: {},
  assertions: [],
  picking: false,
  pendingCheck: null,
};

let state: RecordingState = { ...INITIAL_STATE };

// Where the recorded tab has been, so a Back or Forward press can be told
// apart from an ordinary navigation and replayed as itself.
let trail: string[] = [];
let trailCursor = -1;
/** Set by onCommitted, consumed by onUpdated: what kind of navigation this was. */
let pendingNavigation: "reload" | "go_back" | "go_forward" | null = null;

// The frame currently drawing the island, and how good a home it is. The top
// frame wins outright; otherwise the biggest frame with a body does. Keyed by
// tab too: frame ids are only unique within a tab.
let islandFrame: { tabId: number; frameId: number; score: number } | null =
  null;
const TOP_FRAME_SCORE = Number.MAX_SAFE_INTEGER;

/**
 * MV3 shuts the service worker down when idle and restarts it on the next
 * event, so `state` starts empty on every wake-up. Restoring it is async;
 * every handler awaits this first, otherwise the first message after a restart
 * sees an idle session and the recorder tears itself down mid-recording.
 */
const restored: Promise<void> = chrome.storage.session
  .get("rewindState")
  .then((result) => {
    if (result?.rewindState)
      state = { ...INITIAL_STATE, ...result.rewindState };
  })
  .catch(() => {
    /* first run: nothing stored yet */
  });

function persist() {
  chrome.storage.session.set({ rewindState: state });
}

function status(withAssertions = false) {
  return {
    isRecording: state.status === "recording",
    isSaving: state.status === "saving",
    stepCount: state.steps.length,
    startedAt: state.startedAt,
    paused: state.paused,
    appOrigin: state.appOrigin,
    // Pick mode is tab-wide: the element being checked can be in one frame
    // while the island showing the form is in another.
    picking: !!state.picking,
    pendingCheck: state.pendingCheck ?? null,
    // Only sent when the page asks for it: the catalogue is static, and the
    // status poll runs every second.
    assertions: withAssertions ? (state.assertions ?? []) : undefined,
  };
}

function broadcast() {
  if (state.tabId === null) return;
  chrome.tabs
    .sendMessage(state.tabId, { type: "STATUS_CHANGED", status: status() })
    .catch(() => {
      /* tab has no content script yet */
    });
}

function isDashboard(url: string | undefined): boolean {
  return !!url && DASHBOARD_ORIGINS.some((origin) => url.startsWith(origin));
}

function isRecordable(url: string | undefined): boolean {
  if (!url) return false;
  if (url.startsWith("chrome://") || url.startsWith("chrome-extension://"))
    return false;
  return !isDashboard(url);
}

/** Every tab this session is allowed to record, the first one plus its spawn. */
function isRecordedTab(tabId: number | undefined): boolean {
  return tabId !== undefined && (state.tabIds ?? []).includes(tabId);
}

function adoptTab(tabId: number) {
  state.tabIds = state.tabIds ?? [];
  if (!state.tabIds.includes(tabId)) state.tabIds.push(tabId);
}

function originOf(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

function noteHost(url: string) {
  const host = originOf(url) ? new URL(url).hostname : "";
  if (host && !state.visitedHosts.includes(host)) state.visitedHosts.push(host);
}

function beginRecording(message: any) {
  state = {
    ...INITIAL_STATE,
    status: "recording",
    projectId: message.projectId,
    sessionToken: message.sessionToken,
    startUrl: message.startUrl || "",
    appOrigin: originOf(message.startUrl || ""),
    startedAt: Date.now(),
    steps: [],
    visitedHosts: [],
    localStorage: {},
    assertions: FALLBACK_ASSERTIONS,
    tabIds: [],
  };
  trail = [];
  trailCursor = -1;
  pendingNavigation = null;
  islandFrame = null;
  persist();
  void loadAssertions();
}

/**
 * Decide which frame draws the recorder island.
 *
 * The top frame wins whenever it has a body to draw into. A shell that is
 * still a frameset has none, so the largest frame that does takes over - which
 * is what keeps the controls reachable on products that stream their whole UI
 * into an iframe.
 */
function claimIsland(message: any, sender: chrome.runtime.MessageSender) {
  const tabId = sender.tab?.id;
  // The dashboard and tabs the flow has moved on from both keep polling, and
  // their top frame would win on score alone - parking the controls on a page
  // that records nothing.
  if (tabId === undefined || !isRecordable(sender.tab?.url))
    return { host: false };
  if (state.tabId !== null && state.tabId !== tabId) return { host: false };
  if (!message.hasBody) return { host: false };

  const frameId = sender.frameId ?? 0;
  const score = message.isTop ? TOP_FRAME_SCORE : (message.area ?? 0);

  const held = islandFrame;
  if (held && held.tabId === tabId) {
    if (held.frameId === frameId) return { host: true };
    if (score <= held.score) return { host: false };
  }

  islandFrame = { tabId, frameId, score };
  if (held) tellIslandToRelease(held);
  return { host: true };
}

function tellIslandToRelease(held: { tabId: number; frameId: number }) {
  chrome.tabs
    .sendMessage(
      held.tabId,
      { type: "ISLAND_HOST", host: false },
      { frameId: held.frameId },
    )
    .catch(() => {
      /* that tab or frame is gone, which is why it is being replaced */
    });
}

/** Take the island back, so the next frame to ask can have it. */
function releaseIsland() {
  const held = islandFrame;
  islandFrame = null;
  if (held) tellIslandToRelease(held);
}

/**
 * The exit-criteria vocabulary, straight from the runner that evaluates it.
 *
 * Fetching it keeps the in-page picker from offering checks the backend has
 * never heard of; a failure just leaves the built-in shortlist in place.
 */
async function loadAssertions() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/integrations/assertions`);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    if (Array.isArray(data?.assertions) && data.assertions.length) {
      state.assertions = data.assertions;
      persist();
      broadcast();
    }
  } catch (e) {
    console.warn(
      "Could not load the check catalogue; using the built-in list.",
      e,
    );
  }
}

// The dashboard reaches us through its content script (see content-script.ts).
// `onMessageExternal` stays for direct chrome.runtime.sendMessage(extensionId).
chrome.runtime.onMessageExternal.addListener(
  (message, _sender, sendResponse) => {
    if (message.type === "START_RECORDING") {
      beginRecording(message);
      sendResponse({ success: true });
    }
    return true;
  },
);

/**
 * Manifest content scripts only run on pages loaded *after* the extension was
 * installed or reloaded. Without this, a dashboard tab that was already open
 * has no relay: pressing "Record new test" does nothing at all, silently.
 */
async function injectIntoOpenTabs() {
  const tabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
  await Promise.all(
    tabs.map(async (tab) => {
      if (!tab.id) return;
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["content.js"],
        });
      } catch {
        // Store pages, PDF viewer, other extensions: nothing we can do or need to.
      }
    }),
  );
}

chrome.runtime.onInstalled.addListener(injectIntoOpenTabs);
chrome.runtime.onStartup.addListener(injectIntoOpenTabs);

// ------------------------------------------------------------- navigation

/**
 * Tell a Back, Forward or Reload press apart from an ordinary navigation.
 *
 * Chrome reports "forward_back" for both directions, so the recorded trail is
 * what decides which one it was. When neither end of the trail matches, the
 * navigation is recorded as a plain `navigate` to the resulting URL, which
 * replays the same way without guessing.
 */
chrome.webNavigation?.onCommitted.addListener(async (details) => {
  if (details.frameId !== 0) return;
  await restored;
  if (state.status !== "recording" || state.paused) return;
  if (state.tabId !== null && state.tabId !== details.tabId) return;
  if (!isRecordable(details.url)) return;

  if (details.transitionType === "reload") {
    pendingNavigation = "reload";
    return;
  }
  if (!details.transitionQualifiers?.includes("forward_back")) {
    pendingNavigation = null;
    return;
  }

  if (trailCursor > 0 && trail[trailCursor - 1] === details.url) {
    trailCursor -= 1;
    pendingNavigation = "go_back";
  } else if (
    trailCursor + 1 < trail.length &&
    trail[trailCursor + 1] === details.url
  ) {
    trailCursor += 1;
    pendingNavigation = "go_forward";
  } else {
    pendingNavigation = null;
  }
});

/**
 * A tab the recorded flow opened, usually a target=_blank link.
 *
 * Adopting it is what keeps a recording whole: without it everything the user
 * does after following an external link is silently dropped, and the replay
 * stops halfway through the journey.
 */
chrome.tabs.onCreated.addListener(async (tab) => {
  await restored;
  if (state.status !== "recording" || tab.id === undefined) return;
  if (!isRecordedTab(tab.openerTabId)) return;
  adoptTab(tab.id);
  persist();
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  await restored;
  if (state.status !== "recording" || state.paused) return;
  if (!isRecordedTab(tabId) || state.tabId === tabId) return;
  // The user went back to a tab by hand; the replay has to follow.
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.url || !isRecordable(tab.url)) return;
  switchToTab(tabId, tab.url);
  persist();
  broadcast();
});

/** Point the recording at another tab, and record that it moved. */
function switchToTab(tabId: number, url: string): boolean {
  if (state.tabId === tabId) return false;
  adoptTab(tabId);
  // The tab being left keeps polling, so it has to be told to put its controls
  // away before the new tab is allowed to claim them.
  releaseIsland();
  state.tabId = tabId;
  // A fresh tab has its own history; the old trail says nothing about it.
  trail = [url];
  trailCursor = 0;
  if (state.steps.length > 0) {
    pushStep({
      order_index: 0,
      action: "switch_tab",
      selector: "",
      selector_strategy: "css",
      value: url,
    });
    return true;
  }
  return false;
}

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  await restored;
  if (state.status !== "recording") return;
  if (!isRecordable(tab.url)) return;
  // The first recordable tab starts the session; after that only tabs the
  // flow itself opened count.
  if (state.tabId !== null && !isRecordedTab(tabId)) return;

  const url = tab.url!;
  const origin = originOf(url);

  if (state.tabId === null) {
    state.tabId = tabId;
    adoptTab(tabId);
    if (!state.startUrl) state.startUrl = url;
    if (!state.appOrigin) state.appOrigin = origin;
  }
  noteHost(url);

  if (state.appOrigin && origin !== state.appOrigin) {
    // An identity provider. Nothing here is recorded — the credentials are the
    // user's, and the IdP's own markup is not part of the app under test. The
    // session it hands back is captured as cookies when recording stops.
    state.wasOffOrigin = true;
    persist();
    broadcast();
    return;
  }

  const returningFromAuth = state.wasOffOrigin;
  state.wasOffOrigin = false;

  if (state.paused) {
    pendingNavigation = null;
    persist();
    return;
  }

  if (returningFromAuth && state.steps.length > 0) {
    // Replay must wait for the redirect chain to land before the next step.
    pushStep({
      order_index: 0,
      action: "wait_for_url",
      selector: "",
      selector_strategy: "css",
      value: `${state.appOrigin}/**`,
    });
  }

  const kind = pendingNavigation;
  pendingNavigation = null;
  // Landing in a different tab is a switch, not a navigation - and the switch
  // step already carries the URL, so no navigate step is needed for it.
  const switched = switchToTab(tabId, url);

  if (switched) {
    // nothing more to record: the switch step says where the flow went
  } else if (kind === "reload" || kind === "go_back" || kind === "go_forward") {
    pushStep({
      order_index: 0,
      action: kind,
      selector: "",
      selector_strategy: "css",
      value: null,
    });
  } else {
    rememberVisit(url);
    // The first page load is the start URL, not a navigate step.
    if (state.steps.length > 0 || state.startUrl !== url) {
      const lastStep = state.steps.at(-1);
      if (
        !lastStep ||
        lastStep.action !== "navigate" ||
        lastStep.value !== url
      ) {
        pushStep({
          order_index: 0,
          action: "navigate",
          selector: "",
          selector_strategy: "css",
          value: url,
        });
      }
    }
  }

  persist();
  broadcast();
});

/** Grow the trail the way a browser's history does: forward entries are lost. */
function rememberVisit(url: string) {
  if (trail[trailCursor] === url) return;
  trail = trail.slice(0, trailCursor + 1);
  trail.push(url);
  trailCursor = trail.length - 1;
}

chrome.tabs.onRemoved.addListener(async (tabId) => {
  await restored;
  state.tabIds = (state.tabIds ?? []).filter((id) => id !== tabId);
  if (state.tabId !== tabId) return;

  // The flow closed the tab it was in - a Save-and-close popup, say. Fall back
  // to whatever recorded tab is still open so the recording carries on.
  state.tabId = null;
  islandFrame = null;
  const survivor = state.tabIds.at(-1);
  if (survivor === undefined || state.status !== "recording") {
    persist();
    return;
  }
  const tab = await chrome.tabs.get(survivor).catch(() => null);
  if (tab?.url && isRecordable(tab.url)) switchToTab(survivor, tab.url);
  persist();
  broadcast();
});

// ------------------------------------------------------------------- steps

function pushStep(step: RecordedStep) {
  state.steps.push({ ...step, order_index: state.steps.length });
}

/** A dblclick is preceded by two clicks on the same element; drop those. */
function collapseDoubleClick(step: RecordedStep) {
  for (let i = 0; i < 2; i++) {
    const previous = state.steps.at(-1);
    if (previous?.action === "click" && previous.selector === step.selector)
      state.steps.pop();
    else break;
  }
}

/**
 * Reading down a long page in bursts is one scroll, not four.
 *
 * Only where the tester came to rest matters; the positions passed through on
 * the way there replay as jumps to nowhere.
 */
function collapseScroll(step: RecordedStep) {
  const previous = state.steps.at(-1);
  if (previous?.action === "scroll" && previous.selector === step.selector)
    state.steps.pop();
}

// Steps that drive an element. Playwright scrolls one into view and hovers it
// before acting, so the gestures that led the tester there add nothing.
const ELEMENT_ACTIONS = new Set([
  "click",
  "dblclick",
  "right_click",
  "hover",
  "fill",
  "type",
  "press_key",
  "select",
  "check",
  "uncheck",
  "upload",
  "drag",
]);

/**
 * Drop the gestures that only led up to this step.
 *
 * A mouse crossing a card on its way to a button, and the scroll that brought
 * the button into view, are noise: they replay against elements that are still
 * animating, and they fail for reasons that have nothing to do with the test.
 * A hover that revealed something elsewhere - a menu the tester then clicked
 * into - is not under the new target, so it stays.
 */
function dropIncidentalGestures(step: RecordedStep, supersedesHover: boolean) {
  if (!ELEMENT_ACTIONS.has(step.action)) return;
  if (supersedesHover && state.steps.at(-1)?.action === "hover") {
    state.steps.pop();
  }
  while (state.steps.at(-1)?.action === "scroll") state.steps.pop();
}
/**
 * Whether this hover lands on the element the step before it already used.
 *
 * The pointer is still resting where the click left it, so the browser reports
 * a hover the tester never made. Playwright hovers an element before acting on
 * it anyway, which makes the step both untrue and pointless - and one more
 * place for the run to stall if the element has since been re-rendered.
 */
function isRedundantHover(step: RecordedStep): boolean {
  if (step.action !== "hover") return false;
  const previous = state.steps.at(-1);
  return (
    !!previous &&
    ELEMENT_ACTIONS.has(previous.action) &&
    previous.action !== "hover" &&
    previous.selector === step.selector
  );
}

// -------------------------------------------------------------- session/save

const SAME_SITE: Record<string, string> = {
  no_restriction: "None",
  lax: "Lax",
  strict: "Strict",
  unspecified: "Lax",
};

/**
 * Build a Playwright storage_state from the cookies of every host visited
 * during the session, plus the localStorage the content script read.
 *
 * This is what makes an SSO-protected app replayable: the run starts with the
 * session the human established, and no password is ever recorded or stored.
 */
async function captureStorageState() {
  let cookies: chrome.cookies.Cookie[] = [];
  try {
    cookies = await chrome.cookies.getAll({});
  } catch (e) {
    console.warn("Could not read cookies:", e);
  }

  const relevant = cookies.filter((c) => {
    const domain = c.domain.replace(/^\./, "");
    return state.visitedHosts.some(
      (host) => host === domain || host.endsWith(`.${domain}`),
    );
  });

  return {
    cookies: relevant.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      // Session cookies have no expiry date; Playwright expects -1 for those.
      expires: c.expirationDate ?? -1,
      httpOnly: c.httpOnly,
      secure: c.secure,
      sameSite: SAME_SITE[c.sameSite] ?? "Lax",
    })),
    origins: Object.entries(state.localStorage).map(([origin, entries]) => ({
      origin,
      localStorage: entries,
    })),
  };
}

async function submitRecording(): Promise<{
  success: boolean;
  error?: string;
}> {
  state.status = "saving";
  persist();
  broadcast();

  try {
    const storageState = await captureStorageState();
    const res = await fetch(`${BACKEND_URL}/api/v1/recordings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_token: state.sessionToken,
        project_id: state.projectId,
        name: `Recording ${new Date().toLocaleString()}`,
        start_url: state.startUrl,
        steps: state.steps,
        storage_state: storageState,
      }),
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(
        `Server returned ${res.status}${detail ? `: ${detail.slice(0, 140)}` : ""}`,
      );
    }
    const data = await res.json();

    chrome.tabs.create({
      url: `${DASHBOARD_ORIGINS[0]}/test-cases/${data.id}`,
    });
    state = { ...INITIAL_STATE };
    chrome.storage.session.remove("rewindState");
    return { success: true };
  } catch (err: any) {
    console.error("Failed to submit recording:", err);
    // Don't lose the recording - keep state so the user can retry.
    state.status = "recording";
    persist();
    broadcast();
    return { success: false, error: err?.message || "Unknown error" };
  }
}

// ---------------------------------------------------------------- messages

async function handleMessage(
  message: any,
  sender: chrome.runtime.MessageSender,
): Promise<any> {
  await restored;

  switch (message.type) {
    case "PING":
      // Lets the dashboard prove the extension is installed and reachable.
      return { installed: true };

    case "START_RECORDING":
      // Relayed from the dashboard page by the content script.
      if (!isDashboard(sender.origin ?? sender.url)) {
        return { success: false, error: "Not the Rewind dashboard" };
      }
      beginRecording(message);
      return { success: true };

    case "RECORD_STEP":
      recordStep(message, sender);
      return undefined;

    case "TOGGLE_PAUSE":
      if (state.status !== "recording") return { paused: false };
      state.paused = !state.paused;
      persist();
      broadcast();
      return { paused: state.paused };

    case "STOP_RECORDING":
      if (state.status !== "recording")
        return { success: false, error: "Not recording" };
      if (state.steps.length === 0)
        return { success: false, error: "Nothing recorded yet." };
      // The content script hands over the localStorage of the page it runs on;
      // the popup has no page, so it stops without one.
      if (message.origin && Array.isArray(message.localStorage)) {
        state.localStorage[message.origin] = message.localStorage;
      }
      return await submitRecording();

    case "GET_STATUS":
      return status(!!message.needAssertions);

    case "CLAIM_ISLAND":
      if (state.status !== "recording") return { host: false };
      return claimIsland(message, sender);

    case "SET_PICKING":
      if (state.status !== "recording") return { picking: false };
      state.picking = !!message.picking;
      if (!state.picking) state.pendingCheck = null;
      persist();
      broadcast();
      return { picking: state.picking };

    case "PICK_TARGET":
      if (state.status !== "recording" || !state.picking) return undefined;
      // Held here rather than in the frame that picked it: the island showing
      // the form usually lives in a different document.
      state.pendingCheck = message.target ?? null;
      state.picking = false;
      persist();
      broadcast();
      return { ok: true };

    default:
      return undefined;
  }
}

function recordStep(message: any, sender: chrome.runtime.MessageSender) {
  if (state.status !== "recording" || state.paused) return;
  const senderTabId = sender.tab?.id ?? null;
  // Ignore events from the dashboard and from tabs we are not recording.
  if (senderTabId === null || !isRecordable(sender.tab?.url)) return;
  if (state.tabId === null) {
    state.tabId = senderTabId;
    adoptTab(senderTabId);
  }
  if (state.tabId !== senderTabId) return;
  // Never record anything that happened on an identity provider. Only the top
  // document decides that: a frame legitimately serves a different origin.
  if (
    sender.frameId === 0 &&
    state.appOrigin &&
    originOf(sender.tab?.url ?? "") !== state.appOrigin
  )
    return;

  const incoming = message.step ?? {};
  const step: RecordedStep = {
    ...incoming,
    // Preserve empty string values (don't coerce to null)
    value: incoming.value !== undefined ? incoming.value : null,
    assertion_type: incoming.assertion_type ?? null,
    expected_value: incoming.expected_value ?? null,
    frame_url: incoming.frame_url ?? null,
    is_exit_criteria: !!incoming.is_exit_criteria,
  };
  // Decides what to discard behind it, and is not part of the step itself.
  const supersedesHover = !!step.supersedes_hover;
  delete step.supersedes_hover;

  if (isRedundantHover(step)) return;

  if (step.action === "dblclick") collapseDoubleClick(step);
  if (step.action === "scroll") collapseScroll(step);
  dropIncidentalGestures(step, supersedesHover);
  pushStep(step);
  persist();
  broadcast();
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse);
  return true; // The reply is always async: state has to be restored first.
});
