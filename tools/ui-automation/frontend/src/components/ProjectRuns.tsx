import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Clock, History, Trash2 } from "lucide-react";
import { TestRun } from "../api/types";
import { useDeleteRuns, useRuns } from "../hooks/useRuns";
import { StatusBadge } from "./StatusBadge";
import { SkeletonLoader } from "./SkeletonLoader";
import { EmptyState } from "./EmptyState";
import { ConfirmDialog } from "./ConfirmDialog";
import { formatDate, formatDuration } from "../utils/formatters";

interface Props {
  projectId: string;
}

const durationOf = (run: TestRun) =>
  run.started_at && run.finished_at
    ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
    : null;

/** A run being written to right now cannot be deleted out from under itself. */
const isLive = (run: TestRun) =>
  run.status === "running" || run.status === "pending";

const errorText = (error: unknown): string => {
  const detail = (error as any)?.response?.data;
  if (typeof detail?.message === "string") return detail.message;
  return (error as any)?.message || "Could not delete those runs.";
};

/**
 * Every replay recorded under one project, with the means to clear them out.
 *
 * Runs accumulate faster than anything else in Rewind - each one carries a
 * video, a trace and a screenshot per step - so the list has to offer more than
 * deleting them one at a time.
 */
export const ProjectRuns = ({ projectId }: Props) => {
  const { data: runs, isLoading } = useRuns({ project_id: projectId });
  const remove = useDeleteRuns();
  const [selected, setSelected] = useState<string[]>([]);
  const [confirming, setConfirming] = useState<string[] | null>(null);
  const [error, setError] = useState("");

  const deletable = useMemo(
    () => (runs ?? []).filter((run) => !isLive(run)),
    [runs],
  );
  // A selection made before a run finished, or before another tab deleted one,
  // must not leave the "all" checkbox stuck or the count wrong.
  const chosen = useMemo(
    () => selected.filter((id) => deletable.some((run) => run.id === id)),
    [selected, deletable],
  );
  const allChosen = deletable.length > 0 && chosen.length === deletable.length;

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );

  const confirmDelete = () => {
    const ids = confirming ?? [];
    setError("");
    remove.mutate(ids, {
      onSuccess: () => {
        setSelected((current) => current.filter((id) => !ids.includes(id)));
        setConfirming(null);
      },
      onError: (e) => setError(errorText(e)),
    });
  };

  if (isLoading) return <SkeletonLoader className="h-16" count={3} />;

  if (!runs?.length) {
    return (
      <EmptyState
        icon={History}
        title="No runs yet"
        description="Replay a test case and its result will show up here."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs text-ink-muted cursor-pointer">
          <input
            type="checkbox"
            checked={allChosen}
            disabled={deletable.length === 0}
            onChange={() =>
              setSelected(allChosen ? [] : deletable.map((run) => run.id))
            }
            aria-label="Select every run that can be deleted"
            className="w-4 h-4 accent-primary-500"
          />
          Select all
        </label>
        <span className="flex-1" />
        {chosen.length > 0 && (
          <>
            <span className="text-xs text-ink-muted">
              {chosen.length} selected
            </span>
            <button
              type="button"
              onClick={() => setSelected([])}
              className="btn-ghost text-xs"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => setConfirming(chosen)}
              className="btn-danger !py-2 text-xs"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete {chosen.length}
            </button>
          </>
        )}
      </div>

      <div className="card divide-y divide-line overflow-hidden">
        {runs.map((run) => (
          <div
            key={run.id}
            className="group flex items-center gap-3 px-4 py-3 hover:bg-canvas transition-colors"
          >
            <input
              type="checkbox"
              checked={chosen.includes(run.id)}
              disabled={isLive(run)}
              onChange={() => toggle(run.id)}
              aria-label={`Select run ${run.id.slice(0, 8)}`}
              className="w-4 h-4 shrink-0 accent-primary-500 disabled:opacity-30"
            />
            <Link
              to={`/runs/${run.id}`}
              className="flex flex-1 items-center gap-3 min-w-0"
            >
              <StatusBadge status={run.status} />
              <span className="font-mono text-[11px] text-ink-muted">
                {run.id.slice(0, 8)}
              </span>
              <span className="flex-1" />
              <span className="hidden sm:flex items-center gap-1.5 text-xs text-ink-muted">
                <Clock className="w-3.5 h-3.5" />
                {formatDate(run.started_at)}
              </span>
              <span className="w-16 text-right font-mono text-xs text-ink-muted">
                {formatDuration(durationOf(run)) ?? "—"}
              </span>
            </Link>
            <button
              type="button"
              onClick={() => setConfirming([run.id])}
              disabled={isLive(run)}
              aria-label={`Delete run ${run.id.slice(0, 8)}`}
              title={
                isLive(run) ? "This run is still going" : "Delete this run"
              }
              className="p-1.5 rounded-lg text-ink-muted opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:text-rose-500 hover:bg-rose-50 disabled:opacity-0"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      {confirming && (
        <ConfirmDialog
          title={
            confirming.length === 1 ? "Delete this run?" : "Delete these runs?"
          }
          body={
            <>
              {confirming.length === 1
                ? "This run"
                : `These ${confirming.length} runs`}{" "}
              and all their evidence — screenshots, video, trace and logs — will
              be removed from disk. This cannot be undone.
            </>
          }
          confirmLabel={
            confirming.length === 1
              ? "Delete run"
              : `Delete ${confirming.length}`
          }
          isBusy={remove.isPending}
          error={error}
          onConfirm={confirmDelete}
          onCancel={() => {
            setConfirming(null);
            setError("");
          }}
        />
      )}
    </div>
  );
};
