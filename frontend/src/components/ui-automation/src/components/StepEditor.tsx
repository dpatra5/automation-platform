import React, { useEffect, useMemo, useState } from "react";
import { Action, AssertionOption, SelectorStrategy, Step } from "../api/types";
import {
  ACTION_GROUPS,
  ACTION_ICONS,
  ACTIONS_WITHOUT_SELECTOR,
  SELECTOR_STRATEGIES,
  VALUE_HINTS,
  humanizeAction,
} from "../utils/constants";
import { useAssertions } from "../hooks/useAssertions";
import { CheckBuilder, describeCheck } from "./CheckBuilder";
import * as Icons from "lucide-react";
import {
  Trash2,
  Edit2,
  Check,
  X,
  Plus,
  ArrowUp,
  ArrowDown,
  Save,
  Flag,
} from "lucide-react";

interface Props {
  steps: Step[];
  onUpdate: (steps: Partial<Step>[]) => void;
  isSaving?: boolean;
}

const stepKey = (step: Step, index: number) =>
  step.id || `${step.is_exit_criteria ? "exit" : "flow"}-${index}`;

/**
 * What the recorder called this step's element.
 *
 * The selector says where the element sat, which reads as noise once the page
 * has been rebuilt around it. The label is what the tester saw, and it is what
 * replay falls back to, so it is worth showing beside the selector.
 */
const elementLabel = (step: Step): string => {
  if (!step.element_meta) return "";
  try {
    const meta = JSON.parse(step.element_meta);
    return String(meta?.name || meta?.text || "").slice(0, 60);
  } catch {
    return "";
  }
};

export const ActionIcon = ({
  action,
  className = "",
}: {
  action: Action;
  className?: string;
}) => {
  const name = ACTION_ICONS[action] || "MousePointerClick";
  const Icon = (Icons as any)[name] || Icons.MousePointerClick;
  return <Icon className={className} />;
};

const blankStep = (): Step => ({
  order_index: 0,
  action: "click",
  selector: "",
  selector_strategy: "xpath",
  value: null,
  assertion_type: null,
  expected_value: null,
  is_exit_criteria: false,
});

const blankCriterion = (defaultCheck: string): Step => ({
  ...blankStep(),
  action: "assert",
  assertion_type: defaultCheck,
  expected_value: "",
  is_exit_criteria: true,
});

// ----------------------------------------------------------------- one row

interface RowProps {
  step: Step;
  index: number;
  total: number;
  options: AssertionOption[];
  isEditing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onApply: (step: Step) => void;
  onDelete: () => void;
  onMove: (delta: number) => void;
}

const StepRow = ({
  step,
  index,
  total,
  options,
  isEditing,
  onEdit,
  onCancel,
  onApply,
  onDelete,
  onMove,
}: RowProps) => {
  const [draft, setDraft] = useState<Step>(step);
  const key = stepKey(step, index);

  useEffect(() => {
    if (isEditing) setDraft(step);
  }, [isEditing, step]);

  const isCheck = draft.action === "assert";
  const needsSelector = !ACTIONS_WITHOUT_SELECTOR.includes(draft.action);
  const patch = (changes: Partial<Step>) =>
    setDraft((current) => ({ ...current, ...changes }));

  return (
    <div
      className={`rounded-xl border p-3 group ${
        step.is_exit_criteria
          ? "border-lilac-100 bg-lilac-50/40"
          : "border-line bg-surface"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="flex flex-col gap-0.5 pt-1">
          <button
            onClick={() => onMove(-1)}
            disabled={index === 0}
            aria-label={`Move ${index + 1} up`}
            className="text-ink-muted hover:text-primary-500 disabled:opacity-25"
          >
            <ArrowUp className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onMove(1)}
            disabled={index === total - 1}
            aria-label={`Move ${index + 1} down`}
            className="text-ink-muted hover:text-primary-500 disabled:opacity-25"
          >
            <ArrowDown className="w-3.5 h-3.5" />
          </button>
        </div>

        <div
          className={`w-8 h-8 shrink-0 rounded-lg grid place-items-center ${
            step.is_exit_criteria
              ? "bg-lilac-100 text-lilac-500"
              : "bg-primary-50 text-primary-500"
          }`}
        >
          <ActionIcon action={step.action} className="w-4 h-4" />
        </div>

        <div className="flex-1 min-w-0">
          {isEditing ? (
            <div className="space-y-3">
              {!step.is_exit_criteria && (
                <div>
                  <label className="label" htmlFor={`action-${key}`}>
                    Action
                  </label>
                  <select
                    id={`action-${key}`}
                    className="field"
                    value={draft.action}
                    onChange={(e) =>
                      patch({ action: e.target.value as Action })
                    }
                  >
                    {ACTION_GROUPS.map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.actions.map((a) => (
                          <option key={a} value={a}>
                            {humanizeAction(a)}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
              )}

              {isCheck ? (
                <CheckBuilder
                  step={draft}
                  options={options}
                  onChange={patch}
                  idPrefix={key}
                />
              ) : (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="sm:col-span-2">
                      <label className="label" htmlFor={`selector-${key}`}>
                        Selector
                      </label>
                      <input
                        id={`selector-${key}`}
                        type="text"
                        className="field font-mono text-xs disabled:opacity-50"
                        disabled={!needsSelector}
                        placeholder={
                          needsSelector
                            ? "//button[@id='submit']"
                            : "not used by this action"
                        }
                        value={draft.selector}
                        onChange={(e) => patch({ selector: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="label" htmlFor={`strategy-${key}`}>
                        Found by
                      </label>
                      <select
                        id={`strategy-${key}`}
                        className="field disabled:opacity-50"
                        disabled={!needsSelector}
                        value={draft.selector_strategy}
                        onChange={(e) =>
                          patch({
                            selector_strategy: e.target
                              .value as SelectorStrategy,
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
                  <div>
                    <label className="label" htmlFor={`value-${key}`}>
                      {VALUE_HINTS[draft.action] || "Value"}
                    </label>
                    <input
                      id={`value-${key}`}
                      type="text"
                      className="field"
                      value={draft.value ?? ""}
                      onChange={(e) => patch({ value: e.target.value || null })}
                    />
                  </div>
                </>
              )}

              <div>
                <label className="label" htmlFor={`frame-${key}`}>
                  Inside iframe (URL)
                </label>
                <input
                  id={`frame-${key}`}
                  type="text"
                  className="field font-mono text-xs"
                  placeholder="leave empty for the main page"
                  value={draft.frame_url ?? ""}
                  onChange={(e) => patch({ frame_url: e.target.value || null })}
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={onCancel}
                  className="btn-secondary !py-1.5 text-xs"
                >
                  <X className="w-3.5 h-3.5" /> Cancel
                </button>
                <button
                  onClick={() => onApply(draft)}
                  className="btn-primary !py-1.5 text-xs"
                >
                  <Check className="w-3.5 h-3.5" /> Apply
                </button>
              </div>
            </div>
          ) : (
            <div className="py-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-ink-muted">
                  {index + 1}
                </span>
                <span className="text-sm font-semibold text-ink capitalize">
                  {step.action === "assert"
                    ? "Check"
                    : humanizeAction(step.action)}
                </span>
                {step.action === "assert" ? (
                  <span className="text-sm text-ink-soft truncate max-w-[420px]">
                    {describeCheck(step, options)}
                  </span>
                ) : (
                  step.selector && (
                    <span
                      className="mono-chip truncate max-w-[240px]"
                      title={step.selector}
                    >
                      {step.selector}
                    </span>
                  )
                )}
                {step.frame_url && (
                  <span
                    className="chip bg-canvas border-line text-ink-muted"
                    title={step.frame_url}
                  >
                    in iframe
                  </span>
                )}
                {step.action !== "assert" && elementLabel(step) && (
                  <span
                    className="chip bg-canvas border-line text-ink-muted"
                    title="What the recorder called this element"
                  >
                    {elementLabel(step)}
                  </span>
                )}
              </div>
              {step.action !== "assert" && step.value && (
                <div className="text-sm text-ink-soft mt-1 truncate">
                  "{step.value}"
                </div>
              )}
            </div>
          )}
        </div>

        {!isEditing && (
          <div className="flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            <button
              onClick={onEdit}
              aria-label={`Edit ${index + 1}`}
              className="p-1.5 rounded-lg text-ink-muted hover:text-primary-600 hover:bg-primary-50"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={onDelete}
              aria-label={`Delete ${index + 1}`}
              className="p-1.5 rounded-lg text-ink-muted hover:text-rose-500 hover:bg-rose-50"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// --------------------------------------------------------------- the editor

export const StepEditor = ({ steps: incoming, onUpdate, isSaving }: Props) => {
  const { options, defaultKey } = useAssertions();
  const [steps, setSteps] = useState<Step[]>(incoming);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Adopt server state whenever it changes and nothing local is pending.
  useEffect(() => {
    if (!hasChanges && !editingKey) setSteps(incoming);
  }, [incoming, hasChanges, editingKey]);

  const flow = useMemo(() => steps.filter((s) => !s.is_exit_criteria), [steps]);
  const criteria = useMemo(
    () => steps.filter((s) => s.is_exit_criteria),
    [steps],
  );

  /** Each section is numbered on its own; the runner sorts criteria last. */
  const commit = (nextFlow: Step[], nextCriteria: Step[]) => {
    setSteps([
      ...nextFlow.map((s, i) => ({
        ...s,
        order_index: i,
        is_exit_criteria: false,
      })),
      ...nextCriteria.map((s, i) => ({
        ...s,
        order_index: i,
        is_exit_criteria: true,
      })),
    ]);
    setHasChanges(true);
  };

  const renderSection = (list: Step[], isExit: boolean) => {
    const setList = (next: Step[]) =>
      isExit ? commit(flow, next) : commit(next, criteria);
    return list.map((step, index) => {
      const key = stepKey(step, index);
      return (
        <StepRow
          key={key}
          step={step}
          index={index}
          total={list.length}
          options={options}
          isEditing={editingKey === key}
          onEdit={() => setEditingKey(key)}
          onCancel={() => setEditingKey(null)}
          onApply={(updated) => {
            setList(list.map((s, i) => (i === index ? updated : s)));
            setEditingKey(null);
          }}
          onDelete={() => setList(list.filter((_, i) => i !== index))}
          onMove={(delta) => {
            const target = index + delta;
            if (target < 0 || target >= list.length) return;
            const next = [...list];
            [next[index], next[target]] = [next[target], next[index]];
            setList(next);
          }}
        />
      );
    });
  };

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        {flow.length === 0 ? (
          <p className="text-sm text-ink-muted py-4 text-center">
            No steps yet. Add one below to start building the flow.
          </p>
        ) : (
          renderSection(flow, false)
        )}

        <button
          onClick={() => commit([...flow, blankStep()], criteria)}
          className="btn-secondary !py-2 text-xs"
        >
          <Plus className="w-4 h-4" /> Add step
        </button>
      </section>

      <section className="space-y-2 pt-4 border-t border-line">
        <div className="flex items-center gap-2">
          <Flag className="w-4 h-4 text-lilac-500" />
          <h3 className="text-sm font-semibold text-ink">Exit criteria</h3>
          <span className="chip bg-lilac-50 text-lilac-500 border-lilac-100">
            {criteria.length}
          </span>
        </div>
        <p className="text-xs text-ink-muted leading-relaxed max-w-xl">
          What has to be true once the flow has run. These are checked after the
          last step, and the run only passes when every one of them holds.
        </p>

        {renderSection(criteria, true)}

        <button
          onClick={() =>
            commit(flow, [...criteria, blankCriterion(defaultKey)])
          }
          className="btn-secondary !py-2 text-xs"
        >
          <Plus className="w-4 h-4" /> Add exit criterion
        </button>
      </section>

      {hasChanges && (
        <div className="flex justify-end gap-2 pt-3 border-t border-line">
          <button
            onClick={() => {
              setSteps(incoming);
              setHasChanges(false);
            }}
            className="btn-secondary !py-2 text-xs"
          >
            <X className="w-4 h-4" /> Discard
          </button>
          <button
            onClick={() => {
              onUpdate(steps);
              setHasChanges(false);
            }}
            disabled={isSaving}
            className="btn-primary !py-2 text-xs"
          >
            <Save className="w-4 h-4" /> {isSaving ? "Saving…" : "Save changes"}
          </button>
        </div>
      )}
    </div>
  );
};
