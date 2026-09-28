import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  useTestCase,
  useUpdateTestCase,
  useUpdateSteps,
  useTriggerRun,
} from "../hooks/useTestCases";
import { useRuns } from "../hooks/useRuns";
import { useAuthProfile } from "../hooks/useProjects";
import { StepEditor } from "../components/StepEditor";
import { ScriptEditor } from "../components/ScriptEditor";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { StatusBadge } from "../components/StatusBadge";
import {
  ArrowLeft,
  Play,
  Pencil,
  Save,
  Clock,
  X,
  ShieldAlert,
  ShieldCheck,
  Code2,
  ListOrdered,
} from "lucide-react";
import { formatDate, formatDuration } from "../utils/formatters";

export const TestCaseDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: testCase, isLoading } = useTestCase(id!);
  const updateTestCase = useUpdateTestCase();
  const updateSteps = useUpdateSteps();
  const triggerRun = useTriggerRun();
  const { data: runs, isLoading: runsLoading } = useRuns({ test_case_id: id });
  const { data: authProfile } = useAuthProfile(testCase?.project_id ?? "");

  const [isEditing, setIsEditing] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });
  const [view, setView] = useState<"steps" | "script">("steps");
  const [silentMode, setSilentMode] = useState(false);

  useEffect(() => {
    if (testCase && !isEditing) {
      setForm({ name: testCase.name, description: testCase.description || "" });
    }
  }, [testCase, isEditing]);

  const handleRun = () => {
    triggerRun.mutate(
      { id: id!, silentMode },
      { onSuccess: (run) => navigate(`/runs/${run.id}`) }
    );
  };

  if (isLoading) return <SkeletonLoader className="h-96" />;
  if (!testCase) return <p className="text-ink-muted">Test case not found.</p>;

  return (
    <div className="space-y-6">
      <Link
        to={`/projects/${testCase.project_id}`}
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-primary-600 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to project
      </Link>

      <header className="card p-6">
        <div className="flex flex-wrap gap-5 justify-between items-start">
          {isEditing ? (
            <div className="flex-1 min-w-0 space-y-3 max-w-xl">
              <div>
                <label className="label" htmlFor="tc-name">
                  Name
                </label>
                <input
                  id="tc-name"
                  type="text"
                  className="field"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div>
                <label className="label" htmlFor="tc-desc">
                  Description
                </label>
                <textarea
                  id="tc-desc"
                  rows={2}
                  className="field resize-none"
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    updateTestCase.mutate(
                      { id: id!, data: form },
                      { onSuccess: () => setIsEditing(false) },
                    )
                  }
                  disabled={updateTestCase.isPending}
                  className="btn-primary !py-2 text-xs"
                >
                  <Save className="w-3.5 h-3.5" />{" "}
                  {updateTestCase.isPending ? "Saving…" : "Save"}
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="btn-secondary !py-2 text-xs"
                >
                  <X className="w-3.5 h-3.5" /> Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-ink">
                  {testCase.name}
                </h1>
                <button
                  onClick={() => setIsEditing(true)}
                  aria-label="Edit test case"
                  className="btn-ghost !p-1.5"
                >
                  <Pencil className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm text-ink-muted mt-1.5">
                {testCase.description || "No description"}
              </p>
              {testCase.start_url && (
                <p className="mono-chip inline-block mt-3">
                  {testCase.start_url}
                </p>
              )}
            </div>
          )}

          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-3">
              <button
                onClick={handleRun}
                disabled={triggerRun.isPending}
                className="btn-primary"
              >
                <Play className="w-4 h-4 fill-current" />
                {triggerRun.isPending ? "Starting…" : "Run now"}
              </button>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={silentMode}
                  onChange={(e) => setSilentMode(e.target.checked)}
                  disabled={triggerRun.isPending}
                  className="w-4 h-4 rounded border-line bg-surface text-primary-600"
                />
                <span className="text-sm font-medium text-ink">Silent mode</span>
              </label>
            </div>
            <span className="text-xs text-ink-muted">
              {silentMode
                ? "Opens in new tab with existing login session"
                : "Opens Chrome and replays every step"}
            </span>
            {silentMode && (
              <div className="mt-2 text-xs bg-blue-50 border border-blue-200 rounded-lg p-2 text-blue-700 max-w-sm">
                <p className="font-semibold mb-1">💡 To use Silent Mode:</p>
                <p>Open Chrome with: <code className="bg-blue-100 px-1 rounded">chrome --remote-debugging-port=9222</code></p>
                <p className="mt-1">Then run your test - it will open in a new tab in that browser.</p>
              </div>
            )}
          </div>
        </div>

        {authProfile && (
          <div
            className={`mt-5 flex items-start gap-2 rounded-xl border px-4 py-3 text-xs ${
              authProfile.is_usable
                ? "bg-mint-50 border-mint-100 text-mint-600"
                : "bg-amber-50 border-amber-100 text-amber-600"
            }`}
          >
            {authProfile.is_usable ? (
              <ShieldCheck className="w-4 h-4 shrink-0 mt-px" />
            ) : (
              <ShieldAlert className="w-4 h-4 shrink-0 mt-px" />
            )}
            <span>
              {authProfile.is_usable ? (
                <>
                  This run starts signed in
                  {authProfile.expires_at
                    ? ` — session valid until ${formatDate(authProfile.expires_at)}`
                    : ""}
                  .
                </>
              ) : (
                <>
                  The saved sign-in has expired. Runs will stop before opening
                  the browser — record the flow again to refresh it.
                </>
              )}
            </span>
          </div>
        )}
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-xl border border-line bg-surface p-1">
              {(["steps", "script"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setView(tab)}
                  aria-pressed={view === tab}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition-colors ${
                    view === tab
                      ? "bg-primary-50 text-primary-600"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {tab === "steps" ? (
                    <ListOrdered className="w-3.5 h-3.5" />
                  ) : (
                    <Code2 className="w-3.5 h-3.5" />
                  )}
                  {tab}
                </button>
              ))}
            </div>
            <span className="chip bg-canvas border-line text-ink-muted">
              {testCase.steps?.length || 0}
            </span>
          </div>
          <div className="card p-4">
            {view === "steps" ? (
              <StepEditor
                steps={testCase.steps || []}
                isSaving={updateSteps.isPending}
                onUpdate={(steps) => updateSteps.mutate({ id: id!, steps })}
              />
            ) : (
              <ScriptEditor testCaseId={id!} />
            )}
          </div>
        </section>

        <aside className="space-y-4">
          <h2 className="text-base font-semibold text-ink">Recent runs</h2>
          <div className="card overflow-hidden">
            {runsLoading ? (
              <div className="p-4">
                <SkeletonLoader className="h-14" count={3} />
              </div>
            ) : runs?.length === 0 ? (
              <p className="p-5 text-sm text-ink-muted text-center">
                No runs yet. Press Run now to replay this test in Chrome.
              </p>
            ) : (
              <div className="divide-y divide-line max-h-[420px] overflow-y-auto">
                {runs?.map((run) => {
                  const duration =
                    run.finished_at && run.started_at
                      ? new Date(run.finished_at).getTime() -
                        new Date(run.started_at).getTime()
                      : null;
                  return (
                    <Link
                      key={run.id}
                      to={`/runs/${run.id}`}
                      className="flex flex-col gap-2 px-4 py-3.5 hover:bg-canvas transition-colors"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <StatusBadge status={run.status} />
                        <span className="text-[11px] font-mono text-ink-muted">
                          {run.id.slice(0, 8)}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-ink-muted">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" />
                          {formatDate(run.started_at)}
                        </span>
                        {duration !== null && (
                          <span className="font-mono">
                            {formatDuration(duration)}
                          </span>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
};
