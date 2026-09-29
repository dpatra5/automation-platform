import React, { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";

interface Props {
  title: string;
  /** What exactly is about to go, and what cannot be got back. */
  body: React.ReactNode;
  confirmLabel: string;
  isBusy?: boolean;
  error?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A last stop before something is deleted for good.
 *
 * Deleting a project takes its recordings, its runs and every screenshot and
 * video with it, and none of that is recoverable, so it is worth one deliberate
 * click. Cancel is focused rather than the destructive button, and Escape
 * closes.
 */
export const ConfirmDialog = ({
  title,
  body,
  confirmLabel,
  isBusy,
  error,
  onConfirm,
  onCancel,
}: Props) => {
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancel.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isBusy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isBusy, onCancel]);

  return (
    <dialog
      open
      aria-label={title}
      className="fixed inset-0 z-50 w-full h-full max-w-none max-h-none bg-ink/40 backdrop-blur-sm p-4 flex items-center justify-center"
    >
      <div className="card w-full max-w-md p-6 shadow-pop">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-start gap-3">
            <span className="w-9 h-9 shrink-0 rounded-xl bg-rose-50 text-rose-500 grid place-items-center">
              <AlertTriangle className="w-4 h-4" />
            </span>
            <h2 className="text-lg font-semibold text-ink pt-1">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            aria-label="Close"
            className="btn-ghost !p-1.5"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="text-sm text-ink-soft leading-relaxed">{body}</div>

        {error && (
          <p role="alert" className="mt-4 text-sm text-rose-500">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            ref={cancel}
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="btn-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isBusy}
            className="btn bg-rose-500 text-white hover:bg-rose-600"
          >
            {isBusy ? "Deleting…" : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
};
