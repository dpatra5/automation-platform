// Types only. Anything with a runtime value must be declared in the entry file
// that uses it: a module shared by two entries becomes a separate chunk, and an
// MV3 content script is a classic script that cannot `import`.

export type SelectorStrategy = "test_id" | "role" | "text" | "css" | "xpath";

export interface RecordedStep {
  order_index: number;
  action: string;
  selector: string;
  selector_strategy: string;
  value: string | null;
  /** Only for `assert` steps: which check to make. */
  assertion_type?: string | null;
  /** Only for `assert` steps: what the check compares against. */
  expected_value?: string | null;
  /** Set when the element lives in an iframe, so replay can find it again. */
  frame_url?: string | null;
  /**
   * JSON describing the element itself - tag, role, label, and other ways to
   * reach it - so replay survives the page being rebuilt around it.
   */
  element_meta?: string | null;
  /** Exit criteria run after every recorded step, whatever their position. */
  is_exit_criteria?: boolean;
  /**
   * The preceding hover was the mouse on its way to this element.
   *
   * Consumed by the service worker and never stored: it decides whether that
   * hover is worth keeping, not what the step does.
   */
  supersedes_hover?: boolean;
}

/** An element picked for a check, held tab-wide while the form is filled in. */
export interface PickedTarget {
  description: string;
  selector: string;
  strategy: string;
  suggested: string[];
  defaultKey: string;
  defaultExpected: string;
  frameUrl: string | null;
  /** The element's fingerprint, carried onto the check's step. */
  elementMeta?: string | null;
}

/** One entry of the backend's assertion catalogue, as the picker renders it. */
export interface AssertionOption {
  key: string;
  label: string;
  group: string;
  hint: string;
  needs_selector: boolean;
  needs_expected: boolean;
  expected_label: string;
  param_label: string;
  expected_is_number: boolean;
}

export interface StorageEntry {
  name: string;
  value: string;
}

export interface RecordingState {
  status: "idle" | "recording" | "saving";
  projectId: string;
  sessionToken: string;
  steps: RecordedStep[];
  startUrl: string;
  /** The tab the recording is currently driving. */
  tabId: number | null;
  /** Every tab in the session: the first one plus the ones it opened. */
  tabIds: number[];
  /** Epoch ms, drives the island's elapsed timer. */
  startedAt: number | null;
  paused: boolean;
  /** Origin of the app under test; anything else is treated as a sign-in detour. */
  appOrigin: string;
  /** True while the recorded tab sits on an identity provider. */
  wasOffOrigin?: boolean;
  /** Hostnames seen this session, used to pick the cookies worth keeping. */
  visitedHosts: string[];
  /** localStorage per origin, collected when recording stops. */
  localStorage: Record<string, StorageEntry[]>;
  /** The backend's check catalogue, fetched once per session. */
  assertions?: AssertionOption[];
  /** Waiting for the user to click the element they want to check. */
  picking?: boolean;
  /** The element they clicked, until the check is added or cancelled. */
  pendingCheck?: PickedTarget | null;
}
