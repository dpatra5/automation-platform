import { Action, AssertionOption, RunStatus } from "../api/types";

export const RUN_STATUS_COLORS: Record<RunStatus, string> = {
  pending: "text-ink-muted bg-canvas border-line",
  running: "text-sky-500 bg-sky-50 border-sky-100",
  passed: "text-mint-500 bg-mint-50 border-mint-100",
  failed: "text-rose-500 bg-rose-50 border-rose-100",
  error: "text-amber-500 bg-amber-50 border-amber-100",
};

/** Lucide icon names, resolved dynamically by the step editor and timeline. */
export const ACTION_ICONS: Record<Action, string> = {
  navigate: "Globe",
  reload: "RotateCw",
  go_back: "ArrowLeft",
  go_forward: "ArrowRight",
  click: "MousePointerClick",
  dblclick: "MousePointerClick",
  right_click: "MousePointer2",
  hover: "Mouse",
  drag: "Move",
  scroll: "MoveVertical",
  fill: "Keyboard",
  type: "Type",
  press_key: "CornerDownLeft",
  select: "List",
  check: "CheckSquare",
  uncheck: "Square",
  upload: "Upload",
  wait: "Clock",
  wait_for_selector: "Eye",
  wait_for_url: "Link",
  switch_tab: "ExternalLink",
  assert: "CircleCheckBig",
};

/** Grouped for the action picker, so 20 options stay navigable. */
export const ACTION_GROUPS: { label: string; actions: Action[] }[] = [
  {
    label: "Navigation",
    actions: ["navigate", "reload", "go_back", "go_forward"],
  },
  {
    label: "Pointer",
    actions: ["click", "dblclick", "right_click", "hover", "drag", "scroll"],
  },
  {
    label: "Input",
    actions: [
      "fill",
      "type",
      "press_key",
      "select",
      "check",
      "uncheck",
      "upload",
    ],
  },
  {
    label: "Wait",
    actions: ["wait", "wait_for_selector", "wait_for_url", "switch_tab"],
  },
  { label: "Verify", actions: ["assert"] },
];

export const ASSERTION_TYPES = [
  { value: "text_contains", label: "Text contains" },
  { value: "text_equals", label: "Text equals" },
  { value: "visible", label: "Is visible" },
  { value: "hidden", label: "Is hidden" },
  { value: "checked", label: "Is checked" },
  { value: "url_contains", label: "URL contains" },
];

/**
 * Enough of the check catalogue to keep the editor usable when the backend
 * cannot be reached. The real list comes from `/integrations/assertions`, so
 * this only ever shows up when that request fails.
 */
export const FALLBACK_ASSERTIONS: AssertionOption[] = [
  ...ASSERTION_TYPES.map(({ value, label }) => ({
    key: value,
    label,
    group: "Common",
    hint: "",
    needs_selector: value !== "url_contains",
    needs_expected: ["text_contains", "text_equals", "url_contains"].includes(
      value,
    ),
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  })),
  // Image assertions fallback
  {
    key: "image_visible",
    label: "Image is visible",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: false,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_hidden",
    label: "Image is hidden",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: false,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_loaded",
    label: "Image has loaded successfully",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: false,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_src_contains",
    label: "Image src contains",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_src_equals",
    label: "Image src is exactly",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Full URL or path",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_alt_text_contains",
    label: "Image alt text contains",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_alt_text_equals",
    label: "Image alt text is exactly",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_alt_text_exists",
    label: "Image has alt text",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: false,
    expected_label: "Expected value",
    param_label: "",
    expected_is_number: false,
  },
  {
    key: "image_width_equals",
    label: "Image width equals",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Width in pixels",
    param_label: "",
    expected_is_number: true,
  },
  {
    key: "image_height_equals",
    label: "Image height equals",
    group: "Image",
    hint: "",
    needs_selector: true,
    needs_expected: true,
    expected_label: "Height in pixels",
    param_label: "",
    expected_is_number: true,
  },
];

// XPath first: it is what the recorder writes, so a step added by hand reads
// the same way as a recorded one.
export const SELECTOR_STRATEGIES = [
  { value: "xpath", label: "XPath" },
  { value: "test_id", label: "Test ID" },
  { value: "role", label: "ARIA role" },
  { value: "text", label: "Text" },
  { value: "css", label: "CSS" },
];

/** Actions whose `value` field is meaningful, and what it means. */
export const VALUE_HINTS: Partial<Record<Action, string>> = {
  navigate: "URL to open",
  fill: "Text to enter",
  type: "Text typed key by key",
  press_key: "Key or combo, e.g. Control+A",
  select: "Option value",
  scroll: "x,y offset",
  drag: "Drop target selector",
  upload: "File path readable by the runner",
  wait: "Milliseconds",
  wait_for_url: "URL or glob, e.g. https://app.test/**",
  switch_tab: "URL of the tab to continue in",
};

export const ACTIONS_WITHOUT_SELECTOR: Action[] = [
  "navigate",
  "reload",
  "go_back",
  "go_forward",
  "wait",
  "wait_for_url",
  "switch_tab",
];

export const humanizeAction = (action: string) => action.replace(/_/g, " ");
