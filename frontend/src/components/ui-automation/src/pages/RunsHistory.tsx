import React, { useMemo, useState } from "react";
import { useDeleteRuns, useRuns } from "../hooks/useRuns";
import { useBatches } from "../hooks/useBatches";
import { Link } from "react-router-dom";
import { StatusBadge } from "../components/StatusBadge";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatDuration, formatDate } from "../utils/formatters";
import { RunStatus, TestRun } from "../api/types";
import { History, Layers, Trash2 } from "lucide-react";

const FILTERS: { value: RunStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "error", label: "Errored" },
  { value: "running", label: "Running" },
];

const durationOf = (started: string | null, finished: string | null) =>
  started && finished
    ? new Date(finished).getTime() - new Date(started).getTime()
    : null;

const SequencesTable = () => {
  const { data: batches, isLoading } = useBatches();

  if (isLoading) return <SkeletonLoader className="h-16" count={3} />;
  if (!batches?.length) {
    return (
      <EmptyState
        icon={Layers}
        title="No sequences yet"
        description="Tick several test cases on a project and run them one after another to get a consolidated report."
      />
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line bg-canvas text-[11px] uppercase tracking-wide text-ink-muted">
              <th className="px-5 py-3 font-semibold">Sequence</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold">Test cases</th>
              <th className="px-5 py-3 font-semibold">Duration</th>
              <th className="px-5 py-3 font-semibold">Jira</th>
              <th className="px-5 py-3 font-semibold">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {batches.map((batch) => {
              const passed = batch.runs.filter(
                (r) => r.status === "passed",
              ).length;
              return (
                <tr
                  key={batch.id}
                  className="hover:bg-canvas transition-colors"
                >
                  <td className="px-5 py-3.5">
                    <Link
                      to={`/sequences/${batch.id}`}
                      className="text-sm font-semibold text-primary-600 hover:underline"
                    >
                      {batch.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusBadge status={batch.status} />
                  </td>
                  <td className="px-5 py-3.5 text-sm text-ink-soft tabular-nums">
                    {passed}/{batch.runs.length}
                  </td>
                  <td className="px-5 py-3.5 text-sm font-mono text-ink-soft">
                    {formatDuration(
                      durationOf(batch.started_at, batch.finished_at),
                    ) ?? "—"}
                  </td>
                  <td className="px-5 py-3.5 text-xs text-ink-muted">
                    {batch.jira_issue_key ?? "—"}
                  </td>
                  <td className="px-5 py-3.5 text-sm text-ink-muted">
                    {formatDate(batch.started_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const RunsHistory = () => {
  const [view, setView] = useState<"runs" | "sequences">("runs");
  const [status, setStatus] = useState<RunStatus | "">("");
  const { data: runs, isLoading } = useRuns(status ? { status } : undefined);
  const remove = useDeleteRuns();
  const [selected, setSelected] = useState<string[]>([]);
  const [confirming, setConfirming] = useState<string[] | null>(null);
  const [deleteError, setDeleteError] = useState("");

  // A run being written to right now cannot be deleted out from under itself.
  const isLive = (run: TestRun) =>
    run.status === "running" || run.status === "pending";
  const deletable = useMemo(
    () => (runs ?? []).filter((run) => !isLive(run)),
    [runs],
  );
  const chosen = useMemo(
    () => selected.filter((id) => deletable.some((run) => run.id === id)),
    [selected, deletable],
  );
  const allChosen = deletable.length > 0 && chosen.length === deletable.length;

  const confirmDelete = () => {
    const ids = confirming ?? [];
    setDeleteError("");
    remove.mutate(ids, {
      onSuccess: () => {
        setSelected((current) => current.filter((id) => !ids.includes(id)));
        setConfirming(null);
      },
      onError: (e: any) =>
        setDeleteError(
          e?.response?.data?.message || "Could not delete those runs.",
        ),
    });
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          Run history
        </h1>
        <p className="text-sm text-ink-muted mt-1">
          Every replay, newest first.
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <div className="flex gap-1 p-1 rounded-2xl bg-surface border border-line w-fit">
          {(["runs", "sequences"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setView(value)}
              className={`px-4 py-2 rounded-xl text-sm font-semibold capitalize transition-colors ${
                view === value
                  ? "bg-primary-50 text-primary-600"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {value}
            </button>
          ))}
        </div>

        {view === "runs" && (
          <div className="flex gap-1 p-1 rounded-2xl bg-surface border border-line w-fit">
            {FILTERS.map((filter) => (
              <button
                key={filter.label}
                onClick={() => setStatus(filter.value)}
                className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors ${
                  status === filter.value
                    ? "bg-primary-50 text-primary-600"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        )}
        {view === "runs" && chosen.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
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
              <Trash2 className="w-3.5 h-3.5" /> Delete {chosen.length}
            </button>
          </div>
        )}
      </div>

      {view === "sequences" ? (
        <SequencesTable />
      ) : isLoading ? (
        <SkeletonLoader className="h-16" count={5} />
      ) : runs?.length === 0 ? (
        <EmptyState
          icon={History}
          title="Nothing here yet"
          description="Runs show up as soon as you replay a test case."
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line bg-canvas text-[11px] uppercase tracking-wide text-ink-muted">
                  <th className="pl-5 pr-2 py-3">
                    <input
                      type="checkbox"
                      checked={allChosen}
                      disabled={deletable.length === 0}
                      onChange={() =>
                        setSelected(allChosen ? [] : deletable.map((r) => r.id))
                      }
                      aria-label="Select every run that can be deleted"
                      className="w-4 h-4 accent-primary-500"
                    />
                  </th>
                  <th className="px-5 py-3 font-semibold">Run</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Steps</th>
                  <th className="px-5 py-3 font-semibold">Duration</th>
                  <th className="px-5 py-3 font-semibold">Trigger</th>
                  <th className="px-5 py-3 font-semibold">Started</th>
                  <th className="px-5 py-3">
                    <span className="sr-only">Delete</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {runs?.map((run) => {
                  const duration =
                    run.finished_at && run.started_at
                      ? new Date(run.finished_at).getTime() -
                        new Date(run.started_at).getTime()
                      : null;
                  const passed = run.step_results.filter(
                    (s) => s.status === "passed",
                  ).length;

                  return (
                    <tr
                      key={run.id}
                      className="group hover:bg-canvas transition-colors"
                    >
                      <td className="pl-5 pr-2 py-3.5">
                        <input
                          type="checkbox"
                          checked={chosen.includes(run.id)}
                          disabled={isLive(run)}
                          onChange={() =>
                            setSelected((current) =>
                              current.includes(run.id)
                                ? current.filter((x) => x !== run.id)
                                : [...current, run.id],
                            )
                          }
                          aria-label={`Select run ${run.id.slice(0, 8)}`}
                          className="w-4 h-4 accent-primary-500 disabled:opacity-30"
                        />
                      </td>
                      <td className="px-5 py-3.5">
                        <Link
                          to={`/runs/${run.id}`}
                          className="font-mono text-xs text-primary-600 hover:underline"
                        >
                          {run.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="px-5 py-3.5 text-sm text-ink-soft tabular-nums">
                        {passed}/{run.step_results.length}
                      </td>
                      <td className="px-5 py-3.5 text-sm font-mono text-ink-soft">
                        {duration !== null ? formatDuration(duration) : "—"}
                      </td>
                      <td className="px-5 py-3.5 text-sm text-ink-muted capitalize">
                        {run.trigger_source}
                      </td>
                      <td className="px-5 py-3.5 text-sm text-ink-muted">
                        {formatDate(run.started_at)}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <button
                          type="button"
                          onClick={() => setConfirming([run.id])}
                          disabled={isLive(run)}
                          aria-label={`Delete run ${run.id.slice(0, 8)}`}
                          title={
                            isLive(run)
                              ? "This run is still going"
                              : "Delete this run"
                          }
                          className="p-1.5 rounded-lg text-ink-muted opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:text-rose-500 hover:bg-rose-50 disabled:opacity-0"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => {
            setConfirming(null);
            setDeleteError("");
          }}
        />
      )}
    </div>
  );
};
