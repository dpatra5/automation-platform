import React from "react";
import { Link, useParams } from "react-router-dom";
import { useBatch } from "../hooks/useBatches";
import { StatusBadge } from "../components/StatusBadge";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { JiraSyncNote } from "../components/JiraSyncNote";
import { formatDate, formatDuration } from "../utils/formatters";
import { ArrowLeft, Clock, ExternalLink, FileText, Layers } from "lucide-react";

const durationOf = (started: string | null, finished: string | null) =>
  started && finished
    ? new Date(finished).getTime() - new Date(started).getTime()
    : null;

export const BatchDetail = () => {
  const { id } = useParams<{ id: string }>();
  const { data: batch, isLoading } = useBatch(id!);

  if (isLoading) return <SkeletonLoader className="h-96" />;
  if (!batch) return <p className="text-ink-muted">Sequence not found.</p>;

  const runs = batch.runs ?? [];
  const passed = runs.filter((r) => r.status === "passed").length;
  const done = runs.filter(
    (r) => !["pending", "running"].includes(r.status),
  ).length;
  const isRunning = batch.status === "running" || batch.status === "pending";
  const totalSteps = runs.reduce((sum, r) => sum + r.step_results.length, 0);
  const passedSteps = runs.reduce(
    (sum, r) =>
      sum + r.step_results.filter((s) => s.status === "passed").length,
    0,
  );

  return (
    <div className="space-y-6">
      <Link
        to="/history"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-primary-600 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to run history
      </Link>

      <header className="card p-6">
        <div className="flex flex-wrap gap-4 justify-between items-start">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <Layers className="w-5 h-5 text-primary-500" />
              <h1 className="text-2xl font-bold tracking-tight text-ink">
                {batch.name}
              </h1>
              <StatusBadge status={batch.status} />
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-muted mt-3">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                {formatDuration(
                  durationOf(batch.started_at, batch.finished_at),
                ) ?? "in progress"}
              </span>
              <span>Started {formatDate(batch.started_at)}</span>
              <span className="mono-chip">{batch.id.slice(0, 8)}</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-2xl font-bold tabular-nums text-ink">
                {passed}/{runs.length}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-ink-muted">
                test cases passed
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold tabular-nums text-ink">
                {passedSteps}/{totalSteps}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-ink-muted">
                steps passed
              </div>
            </div>
            {batch.report_path && (
              <a
                href={`/${batch.report_path}`}
                target="_blank"
                rel="noreferrer"
                className="btn-secondary"
              >
                <FileText className="w-4 h-4" /> Report{" "}
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>

        {isRunning && (
          <p className="mt-5 rounded-xl bg-sky-50 border border-sky-100 px-4 py-3 text-sm text-sky-600">
            Running one test case at a time — {done} of {runs.length} finished.
            The consolidated report is written once the last one is done.
          </p>
        )}

        {batch.error_message && (
          <pre className="mt-5 rounded-xl bg-rose-50 border border-rose-100 px-4 py-3 text-xs text-rose-600 font-mono whitespace-pre-wrap overflow-x-auto">
            {batch.error_message}
          </pre>
        )}

        <JiraSyncNote
          className="mt-5"
          issueKey={batch.jira_issue_key}
          status={batch.jira_status}
          error={batch.jira_error}
        />
      </header>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line bg-canvas text-[11px] uppercase tracking-wide text-ink-muted">
              <th className="px-5 py-3 font-semibold">#</th>
              <th className="px-5 py-3 font-semibold">Run</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold">Steps</th>
              <th className="px-5 py-3 font-semibold">Duration</th>
              <th className="px-5 py-3 font-semibold">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.map((run, index) => (
              <tr
                key={run.id}
                className="hover:bg-canvas transition-colors align-top"
              >
                <td className="px-5 py-3.5 text-sm text-ink-muted tabular-nums">
                  {index + 1}
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
                  {run.step_results.filter((s) => s.status === "passed").length}
                  /{run.step_results.length}
                </td>
                <td className="px-5 py-3.5 text-sm font-mono text-ink-soft">
                  {formatDuration(
                    durationOf(run.started_at, run.finished_at),
                  ) ?? "—"}
                </td>
                <td className="px-5 py-3.5 text-xs text-ink-muted max-w-sm">
                  {run.error_message ? (
                    <span className="text-rose-600">
                      {run.error_message.split("\n")[0]}
                    </span>
                  ) : (
                    "Completed"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
