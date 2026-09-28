import React, { useEffect, useRef } from "react";
import { AssertionOption, SelectorStrategy, Step } from "../api/types";
import { SELECTOR_STRATEGIES } from "../utils/constants";

interface Props {
  step: Step;
  options: AssertionOption[];
  onChange: (patch: Partial<Step>) => void;
  idPrefix: string;
}

/** Detect if selector is for an image element (e.g., "img", "img[src]", etc.) */
const isImageSelector = (selector: string): boolean => {
  if (!selector || !selector.trim()) return false;
  const trimmed = selector.trim().toLowerCase();
  // Match: "img" followed by end of string, whitespace, >, or [
  // Also match: //img with same conditions
  return /^(\/\/)?img($|\s|>|\[)/.test(trimmed);
};

/** Group the flat catalogue so a 40-option list stays navigable. */
const groupByGroup = (options: AssertionOption[]) => {
  const groups = new Map<string, AssertionOption[]>();
  for (const option of options) {
    if (!groups.has(option.group)) groups.set(option.group, []);
    groups.get(option.group)!.push(option);
  }
  return [...groups.entries()];
};

/**
 * The plain-language form for one check.
 *
 * A check is three answers — what to look at, what to compare, and what it
 * should be — so the form asks exactly those and hides the fields the chosen
 * check does not use.
 */
export const CheckBuilder = ({ step, options, onChange, idPrefix }: Props) => {
  const prevSelectorRef = useRef<string>("");
  const isImage = isImageSelector(step.selector);
  
  // When selector changes TO an image, auto-suggest image_visible
  useEffect(() => {
    const wasImage = isImageSelector(prevSelectorRef.current);
    prevSelectorRef.current = step.selector;
    
    // If selector just changed TO image and no assertion is set, default to image_visible
    if (isImage && !wasImage && !step.assertion_type) {
      onChange({ assertion_type: "image_visible" });
    }
  }, [step.selector, step.assertion_type, onChange]);

  // Filter to show only image checks when selector is an image, otherwise show all
  const filteredOptions = isImage
    ? options.filter((o) => o.group === "Image")
    : options;

  const spec = options.find((o) => o.key === step.assertion_type);
  const needsSelector = spec ? spec.needs_selector : true;
  const needsExpected = spec ? spec.needs_expected : true;

  return (
    <div className="space-y-3">
      <div>
        <label className="label" htmlFor={`${idPrefix}-check`}>
          Check
        </label>
        <select
          id={`${idPrefix}-check`}
          className="field"
          value={step.assertion_type ?? ""}
          onChange={(e) => onChange({ assertion_type: e.target.value })}
        >
          {groupByGroup(filteredOptions).map(([group, entries]) => (
            <optgroup key={group} label={group}>
              {entries.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {isImage && filteredOptions.length > 0 && (
          <p className="text-[11px] text-blue-600 mt-1">
            💡 Showing image validation options for this element.
          </p>
        )}
        {spec?.hint && (
          <p className="text-[11px] text-ink-muted mt-1">{spec.hint}</p>
        )}
      </div>

      {needsSelector && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-2">
            <label className="label" htmlFor={`${idPrefix}-selector`}>
              Element
            </label>
            <input
              id={`${idPrefix}-selector`}
              type="text"
              className="field font-mono text-xs"
              placeholder=".order-total"
              value={step.selector}
              onChange={(e) => onChange({ selector: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor={`${idPrefix}-strategy`}>
              Found by
            </label>
            <select
              id={`${idPrefix}-strategy`}
              className="field"
              value={step.selector_strategy}
              onChange={(e) =>
                onChange({
                  selector_strategy: e.target.value as SelectorStrategy,
                })
              }
            >
              {SELECTOR_STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {needsExpected && (
          <div>
            <label className="label" htmlFor={`${idPrefix}-expected`}>
              {spec?.expected_label || "Expected value"}
            </label>
            <input
              id={`${idPrefix}-expected`}
              type={spec?.expected_is_number ? "number" : "text"}
              className="field"
              value={step.expected_value ?? ""}
              onChange={(e) => onChange({ expected_value: e.target.value })}
            />
          </div>
        )}
        {spec?.param_label && (
          <div>
            <label className="label" htmlFor={`${idPrefix}-param`}>
              {spec.param_label}
            </label>
            <input
              id={`${idPrefix}-param`}
              type="text"
              className="field font-mono text-xs"
              value={step.value ?? ""}
              onChange={(e) => onChange({ value: e.target.value || null })}
            />
          </div>
        )}
      </div>
    </div>
  );
};

/** One-line summary of a check, for the collapsed row. */
export const describeCheck = (
  step: Step,
  options: AssertionOption[],
): string => {
  const spec = options.find((o) => o.key === step.assertion_type);
  const label =
    spec?.label ?? (step.assertion_type ?? "check").replace(/_/g, " ");
  const target = spec?.needs_selector === false ? "" : step.selector;
  const expected = spec?.needs_expected === false ? "" : step.expected_value;
  return [target, label.toLowerCase(), expected && `"${expected}"`]
    .filter(Boolean)
    .join(" ");
};
