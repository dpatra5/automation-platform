import React, { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  useProject,
  useAuthProfile,
  useDeleteProject,
} from "../hooks/useProjects";
import { useTestCases, useCreateTestCase } from "../hooks/useTestCases";
import { useRequestSessionToken } from "../hooks/useRecordings";
import { useCreateBatch } from "../hooks/useBatches";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { EmptyState } from "../components/EmptyState";
import { SessionCard } from "../components/SessionCard";
import { JiraCard } from "../components/JiraCard";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProjectRuns } from "../components/ProjectRuns";
import { formatDate } from "../utils/formatters";
import {
  EXTENSION_MISSING_HELP,
  startRecording,
} from "../utils/extension";
import {
  Globe,
  Circle,
  ChevronRight,
  ListChecks,
  ListPlus,
  Puzzle,
  AlertTriangle,
  ListOrdered,
  History,
  Trash2,
} from "lucide-react";

export const ProjectDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading: projectLoading } = useProject(id!);
  const { data: testCases, isLoading: testsLoading } = useTestCases(id!);
  const { data: authProfile, isLoading: authLoading } = useAuthProfile(id!);
  const sessionToken = useRequestSessionToken();
  const createBatch = useCreateBatch();
  const createTestCase = useCreateTestCase();
  const deleteProject = useDeleteProject();
  const [notice, setNotice] = useState<{
    tone: "info" | "error";
    text: string;
  } | null>(null);
  const [hasExtension, setHasExtension] = useState<boolean | null>(null);
  // Selection order is the run order, so this is a list rather than a set.
  const [selected, setSelected] = useState<string[]>([]);
  const [view, setView] = useState<"tests" | "runs">("tests");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [creatingTestCase, setCreatingTestCase] = useState(false);
  const [newTestCaseName, setNewTestCaseName] = useState("");
  const [newTestCaseUrl, setNewTestCaseUrl] = useState("");

  const removeProject = () => {
    setDeleteError("");
    deleteProject.mutate(id!, {
      onSuccess: () => navigate("/projects"),
      onError: (e: any) =>
        setDeleteError(
          e?.response?.data?.message || "Could not delete this project.",
        ),
    });
  };

  const toggleSelected = (testCaseId: string) => {
    setSelected((current) =>
      current.includes(testCaseId)
        ? current.filter((x) => x !== testCaseId)
        : [...current, testCaseId],
    );
  };

  const runSequence = () => {
    createBatch.mutate(
      { test_case_ids: selected },
      {
        onSuccess: (batch) => {
          setSelected([]);
          navigate(`/sequences/${batch.id}`);
        },
        onError: (e: any) =>
          setNotice({
            tone: "error",
            text: e?.response?.data?.message || "Could not start the sequence.",
          }),
      },
    );
  };

  const openNewTestCase = () => {
    setNewTestCaseName("");
    setNewTestCaseUrl(project?.base_url || "");
    setCreatingTestCase(true);
  };

  const handleRecordNew = () => {
    // Opened inside the click handler: a popup opened later, after the token
    // request resolves, is blocked as not user-initiated.
    const appTab = window.open("", "_blank");

    sessionToken.mutate(id!, {
      onSuccess: async (data) => {
        const result = await startRecording({
          sessionToken: data.token,
          projectId: id!,
          startUrl: project?.base_url || "",
        });

        if (!result.ok) {
          appTab?.close();
          setHasExtension(false);
          setNotice({
            tone: "error",
            text: result.error || EXTENSION_MISSING_HELP,
          });
          return;
        }

        setHasExtension(true);
        if (project?.base_url && appTab)
          appTab.location.href = project.base_url;
        setNotice({
          tone: "info",
          text: appTab
            ? "Recording started. The Rewind bar at the bottom of that tab shows the timer and the stop button."
            : `Recording started. Open ${project?.base_url} to begin — the Rewind bar appears at the bottom of the page.`,
        });
      },
      onError: () => {
        appTab?.close();
        setNotice({
          tone: "error",
          text: "Could not reach the backend to start a session.",
        });
      },
    });
  };

  const submitNewTestCase = () => {
    if (!newTestCaseName.trim()) return;
    createTestCase.mutate(
      {
        project_id: id!,
        name: newTestCaseName.trim(),
        start_url: newTestCaseUrl.trim() || project?.base_url,
      },
      {
        onSuccess: (tc) => {
          setCreatingTestCase(false);
          navigate(`/test-cases/${tc.id}`);
        },
        onError: (e: any) =>
          setNotice({
            tone: "error",
            text: e?.response?.data?.message || "Could not create the test case.",
          }),
      },
    );
  };

  if (projectLoading) return <SkeletonLoader className="h-64" />;
  if (!project) return <p className="text-ink-muted">Project not found.</p>;

  return (
    <div className="space-y-6">
      <header className="card p-6">
        <div className="flex flex-wrap gap-5 justify-between items-start">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              {project.name}
            </h1>
            <p className="text-sm text-ink-muted mt-1.5 max-w-2xl">
              {project.description || "No description"}
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-4">
              <a
                href={project.base_url}
                target="_blank"
                rel="noreferrer"
                className="chip bg-canvas border-line text-ink-soft hover:text-primary-600"
              >
                <Globe className="w-3.5 h-3.5" />
                {project.base_url}
              </a>
              <span className="text-xs text-ink-muted">
                Created {formatDate(project.created_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <button
                onClick={handleRecordNew}
                disabled={sessionToken.isPending}
                className="btn-secondary"
              >
                <Circle className="w-3.5 h-3.5 fill-current" />
                {sessionToken.isPending ? "Starting…" : "Record new test"}
              </button>
              <button
                onClick={openNewTestCase}
                className="btn-primary"
              >
                <ListPlus className="w-3.5 h-3.5" />
                New test case
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                aria-label="Delete project"
                title="Delete this project"
                className="btn-ghost !p-2 hover:text-rose-500 hover:bg-rose-50"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            {hasExtension === false && (
              <span className="chip bg-amber-50 border-amber-100 text-amber-500">
                <Puzzle className="w-3.5 h-3.5" />
                Extension not detected
              </span>
            )}
          </div>
        </div>

        {notice && (
          <div
            className={`mt-5 flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${
              notice.tone === "error"
                ? "bg-amber-50 border-amber-100 text-amber-600"
                : "bg-primary-50 border-primary-100 text-primary-700"
            }`}
          >
            {notice.tone === "error" && (
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            )}
            <span>{notice.text}</span>
          </div>
        )}
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-xl border border-line bg-surface p-1">
              {(
                [
                  { id: "tests", label: "Test cases", icon: ListChecks },
                  { id: "runs", label: "Runs", icon: History },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setView(tab.id)}
                  aria-pressed={view === tab.id}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    view === tab.id
                      ? "bg-primary-50 text-primary-600"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  <tab.icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              ))}
            </div>
            {view === "tests" && (
              <span className="chip bg-canvas border-line text-ink-muted">
                {testCases?.length || 0}
              </span>
            )}
            <span className="flex-1" />
            {view === "tests" && selected.length > 0 && (
              <>
                <button
                  onClick={() => setSelected([])}
                  className="btn-ghost text-xs"
                >
                  Clear
                </button>
                <button
                  onClick={runSequence}
                  disabled={createBatch.isPending}
                  className="btn-primary !py-2 text-xs"
                >
                  <ListOrdered className="w-4 h-4" />
                  {createBatch.isPending
                    ? "Starting…"
                    : `Run ${selected.length} in sequence`}
                </button>
              </>
            )}
          </div>

          {view === "runs" ? (
            <ProjectRuns projectId={id!} />
          ) : testsLoading ? (
            <SkeletonLoader className="h-16" count={3} />
          ) : testCases?.length === 0 ? (
            <EmptyState
              icon={ListPlus}
              title="No test cases yet"
              description="Click New test case, give it a name and a start URL, then add steps."
            />
          ) : (
            <>
              <p className="text-xs text-ink-muted">
                Tick several test cases to replay them one after another and get
                a single consolidated report.
              </p>
              <div className="card divide-y divide-line overflow-hidden">
                {testCases?.map((tc) => {
                  const position = selected.indexOf(tc.id);
                  return (
                    <div
                      key={tc.id}
                      className="flex items-center gap-3 px-4 py-4 hover:bg-canvas transition-colors group"
                    >
                      <label className="flex items-center gap-2 shrink-0 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={position >= 0}
                          onChange={() => toggleSelected(tc.id)}
                          aria-label={`Include ${tc.name} in the sequence`}
                          className="w-4 h-4 accent-primary-500"
                        />
                        {position >= 0 && (
                          <span className="chip bg-primary-50 text-primary-600 border-primary-100 tabular-nums">
                            {position + 1}
                          </span>
                        )}
                      </label>

                      <Link
                        to={`/test-cases/${tc.id}`}
                        className="flex flex-1 items-center gap-4 min-w-0"
                      >
                        <span className="w-9 h-9 shrink-0 rounded-xl bg-primary-50 text-primary-500 grid place-items-center">
                          <ListChecks className="w-4 h-4" />
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block font-semibold text-sm text-ink group-hover:text-primary-600 transition-colors truncate">
                            {tc.name}
                          </span>
                          <span className="block text-xs text-ink-muted truncate mt-0.5">
                            {tc.steps?.length || 0} steps ·{" "}
                            {tc.start_url || "no start URL"}
                          </span>
                        </span>
                        <span className="text-xs text-ink-muted hidden sm:block">
                          {formatDate(tc.created_at)}
                        </span>
                        <ChevronRight className="w-4 h-4 text-ink-muted group-hover:text-primary-500" />
                      </Link>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>

        <aside className="space-y-4">
          <SessionCard
            projectId={id!}
            profile={authProfile}
            isLoading={authLoading}
          />
          <JiraCard project={project} />

          <div className="card p-5">
            <h3 className="text-sm font-semibold text-ink mb-3">
              Building a test case
            </h3>
            <ol className="space-y-2.5 text-xs text-ink-muted leading-relaxed list-decimal list-inside">
              <li>
                Press{" "}
                <span className="font-medium text-ink-soft">
                  Record new test
                </span>{" "}
                to capture a flow with the Chrome extension, or{" "}
                <span className="font-medium text-ink-soft">
                  New test case
                </span>{" "}
                to build one by hand.
              </li>
              <li>
                In a recorded flow, press{" "}
                <span className="font-medium text-ink-soft">Add check</span> on
                the floating bar to add an exit criterion, then{" "}
                <span className="font-medium text-ink-soft">Stop</span> to
                finish.
              </li>
              <li>
                For a hand-built one, use{" "}
                <span className="font-medium text-ink-soft">Add step</span> to
                build the flow action by action, or edit it as a script.
              </li>
              <li>
                Run it on its own, or tick several test cases here and run them
                as a sequence.
              </li>
            </ol>
          </div>
        </aside>
      </div>

      {creatingTestCase && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 px-4">
          <div className="card w-full max-w-md p-6 space-y-4">
            <h3 className="text-base font-semibold text-ink">New test case</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">
                  Name
                </label>
                <input
                  type="text"
                  autoFocus
                  value={newTestCaseName}
                  onChange={(e) => setNewTestCaseName(e.target.value)}
                  placeholder="e.g. Add and complete todo"
                  className="field w-full"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">
                  Start URL
                </label>
                <input
                  type="text"
                  value={newTestCaseUrl}
                  onChange={(e) => setNewTestCaseUrl(e.target.value)}
                  placeholder={project.base_url}
                  className="field w-full"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCreatingTestCase(false)}
                className="btn-ghost"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitNewTestCase}
                disabled={!newTestCaseName.trim() || createTestCase.isPending}
                className="btn-primary"
              >
                {createTestCase.isPending ? "Creating…" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete "${project.name}"?`}
          body={
            <>
              Its {testCases?.length || 0} test case
              {testCases?.length === 1 ? "" : "s"}, every run recorded against
              them and all their evidence — screenshots, video, traces and logs
              — will be deleted from disk, along with the saved sign-in for this
              project. This cannot be undone.
            </>
          }
          confirmLabel="Delete project"
          isBusy={deleteProject.isPending}
          error={deleteError}
          onConfirm={removeProject}
          onCancel={() => {
            setConfirmingDelete(false);
            setDeleteError("");
          }}
        />
      )}
    </div>
  );
};
