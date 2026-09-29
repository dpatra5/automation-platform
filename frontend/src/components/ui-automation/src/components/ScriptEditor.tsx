import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AlertTriangle, Check, RotateCcw, Save } from "lucide-react";
import { useScript, useUpdateScript } from "../hooks/useTestCases";
import { SkeletonLoader } from "./SkeletonLoader";

interface Props {
  testCaseId: string;
}

// Both text layers have to agree on these to the pixel, or the caret drifts
// away from the characters painted under it. They mirror `leading-5` and
// `py-3` on TEXT_LAYER below.
const LINE_HEIGHT = 20;
const PADDING_Y = 12;
// Short scripts should not leave a screenful of empty box below them, and long
// ones should not push the page's own scrollbar out of reach.
const MIN_HEIGHT = 180;
const MAX_HEIGHT = 620;
const INDENT = "    ";

/** Every rule that decides where a character lands, shared by both layers. */
const TEXT_LAYER =
  "m-0 border-0 font-mono text-xs leading-5 py-3 px-3 whitespace-pre";

/**
 * The script's own vocabulary, in the order it has to be read.
 *
 * A `#` inside a selector is part of the string, not the start of a comment.
 * The scan runs left to right, so whichever of the two starts first takes the
 * text and neither can swallow the other.
 */
const TOKENS =
  /(#[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(def|pass|None|True|False|import|from|return)\b|\b(page)\b|\b(\d+(?:\.\d+)?)\b|\b([A-Za-z_]\w*)(?=\s*\()/g;

const TOKEN_CLASS = [
  "text-ink-muted italic", // comment
  "text-mint-600", // string
  "text-lilac-600 font-semibold", // keyword
  "text-sky-600", // page
  "text-amber-600", // number
  "text-primary-600", // call
];

/** One line of script, split into coloured spans. */
const colour = (line: string): React.ReactNode[] => {
  const out: React.ReactNode[] = [];
  let last = 0;
  TOKENS.lastIndex = 0;
  let match = TOKENS.exec(line);
  while (match) {
    if (match.index > last) out.push(line.slice(last, match.index));
    const found = match;
    const group = TOKEN_CLASS.findIndex((_, i) => found[i + 1] !== undefined);
    out.push(
      <span key={match.index} className={TOKEN_CLASS[group]}>
        {match[0]}
      </span>,
    );
    last = match.index + match[0].length;
    match = TOKENS.exec(line);
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
};

/** The line a parse error points at, so the editor can mark it. */
const failingLine = (message: string): number | null => {
  const match = /line\s+(\d+)/i.exec(message);
  const line = match ? Number(match[1]) : Number.NaN;
  return Number.isFinite(line) && line > 0 ? line : null;
};

const errorText = (error: unknown): string => {
  const detail = (error as any)?.response?.data;
  if (typeof detail?.message === "string") return detail.message;
  if (typeof detail?.detail === "string") return detail.detail;
  return (error as any)?.message || "The script could not be saved.";
};

/**
 * The recorded steps as an editable script.
 *
 * Not a preview: what is saved here replaces the steps the runner replays, and
 * every block is labelled with the step it belongs to so a failure in the run
 * report can be traced to a line. A script that cannot be read back is
 * reported by line number rather than being saved in part.
 *
 * The colours are painted on a layer behind a transparent textarea, so editing
 * stays native: selection, undo, the caret and screen readers all still belong
 * to a real form control.
 */
export const ScriptEditor = ({ testCaseId }: Props) => {
  const { data: script, isLoading } = useScript(testCaseId);
  const save = useUpdateScript();
  const [draft, setDraft] = useState("");
  const [edited, setEdited] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const input = useRef<HTMLTextAreaElement>(null);
  const painted = useRef<HTMLPreElement>(null);
  const gutter = useRef<HTMLPreElement>(null);
  /** Where to put the caret after an edit this component made itself. */
  const caret = useRef<number | null>(null);

  // Adopt the server's version whenever it changes and nothing local is pending.
  useEffect(() => {
    if (script !== undefined && !edited) setDraft(script);
  }, [script, edited]);

  useEffect(() => {
    if (caret.current === null || !input.current) return;
    input.current.selectionStart = caret.current;
    input.current.selectionEnd = caret.current;
    caret.current = null;
  }, [draft]);

  const lines = useMemo(() => draft.split("\n"), [draft]);
  const rendered = useMemo(() => lines.map(colour), [lines]);
  const badLine = error ? failingLine(error) : null;
  const height = Math.min(
    MAX_HEIGHT,
    Math.max(MIN_HEIGHT, lines.length * LINE_HEIGHT + PADDING_Y * 2),
  );

  const edit = (next: string, at?: number) => {
    if (at !== undefined) caret.current = at;
    setDraft(next);
    setEdited(true);
    setSaved(false);
  };

  const onSave = useCallback(() => {
    setError("");
    save.mutate(
      { id: testCaseId, script: draft },
      {
        onSuccess: () => {
          setEdited(false);
          setSaved(true);
        },
        onError: (err) => setError(errorText(err)),
      },
    );
  }, [draft, save, testCaseId]);

  // The confirmation fades on its own; its timer must not outlive the component.
  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 2500);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const revert = () => {
    setDraft(script ?? "");
    setEdited(false);
    setSaved(false);
    setError("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (edited && !save.isPending) onSave();
      return;
    }
    // Python is its indentation, so Tab has to indent rather than leave the field.
    if (e.key !== "Tab") return;
    e.preventDefault();
    const { selectionStart: start, selectionEnd: end } = e.currentTarget;
    if (!e.shiftKey) {
      edit(
        draft.slice(0, start) + INDENT + draft.slice(end),
        start + INDENT.length,
      );
      return;
    }
    const before = draft.slice(0, start);
    const removed = before.length - before.replace(/ {1,4}$/, "").length;
    if (removed) {
      edit(before.slice(0, -removed) + draft.slice(start), start - removed);
    }
  };

  /** Both passive layers follow the textarea, which is the one that scrolls. */
  const onScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    const { scrollTop, scrollLeft } = e.currentTarget;
    if (painted.current) {
      painted.current.scrollTop = scrollTop;
      painted.current.scrollLeft = scrollLeft;
    }
    if (gutter.current) gutter.current.scrollTop = scrollTop;
  };

  if (isLoading) return <SkeletonLoader className="h-96" />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-muted max-w-md">
          Every block is one step, labelled with the number shown on the Steps
          tab. Edit a line and save to change what the run does.
        </p>
        <div className="flex items-center gap-2">
          {saved && (
            <span className="chip bg-mint-50 border-mint-100 text-mint-600">
              <Check className="w-3.5 h-3.5" /> Saved
            </span>
          )}
          {edited && !saved && (
            <span className="chip bg-amber-50 border-amber-100 text-amber-600">
              Unsaved changes
            </span>
          )}
          <button
            type="button"
            onClick={revert}
            disabled={!edited || save.isPending}
            className="btn-secondary !py-2 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Revert
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!edited || save.isPending}
            className="btn-primary !py-2 text-xs"
          >
            <Save className="w-3.5 h-3.5" />
            {save.isPending ? "Saving…" : "Save script"}
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-xs text-rose-500"
        >
          <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
          <span>{error}</span>
        </div>
      )}

      <div
        className="flex rounded-xl border border-line bg-surface overflow-hidden"
        style={{ height }}
      >
        <pre
          ref={gutter}
          aria-hidden="true"
          className={`${TEXT_LAYER} !px-2 w-12 shrink-0 select-none overflow-hidden border-r border-line bg-canvas text-right text-ink-muted`}
        >
          {lines.map((_, i) => (
            <div
              key={i}
              className={`min-h-5 ${badLine === i + 1 ? "text-rose-500 font-bold" : ""}`}
            >
              {i + 1}
            </div>
          ))}
        </pre>

        <div className="relative flex-1 overflow-hidden">
          <pre
            ref={painted}
            aria-hidden="true"
            className={`${TEXT_LAYER} absolute inset-0 overflow-hidden text-ink`}
          >
            {rendered.map((tokens, i) => (
              <div
                key={i}
                className={`min-h-5 ${badLine === i + 1 ? "bg-rose-50" : ""}`}
              >
                {tokens}
              </div>
            ))}
          </pre>
          <textarea
            ref={input}
            value={draft}
            wrap="off"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            aria-label="Test script"
            onScroll={onScroll}
            onKeyDown={onKeyDown}
            onChange={(e) => edit(e.target.value)}
            className={`${TEXT_LAYER} absolute inset-0 h-full w-full resize-none overflow-auto bg-transparent text-transparent caret-ink outline-none selection:bg-primary-100`}
          />
        </div>
      </div>
    </div>
  );
};
