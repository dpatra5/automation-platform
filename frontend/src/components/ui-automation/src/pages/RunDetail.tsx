import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useDeleteRuns, useRun } from "../hooks/useRuns";
import { useTestCase } from "../hooks/useTestCases";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { EvidenceViewer } from "../components/EvidenceViewer";
import { Filmstrip } from "../components/Filmstrip";
import { JiraSyncNote } from "../components/JiraSyncNote";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatDuration, formatDate } from "../utils/formatters";
import {
  ArrowLeft,
  Clock,
  Video,
  Terminal,
  Network,
  Download,
  ListChecks,
  HelpCircle,
  Layers,
  Trash2,
} from "lucide-react";

type Tab = "timeline" | "video" | "console" | "network";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "timeline", label: "Timeline", icon: ListChecks },
  { id: "video", label: "Replay", icon: Video },
  { id: "console", label: "Console", icon: Terminal },
  { id: "network", label: "Network", icon: Network },
];

/** Log files are static artifacts; fetch them straight from the artifacts route. */
const useLogFile = (
  path: string | undefined,
  missingMessage: string,
  reloadKey: unknown,
) => {
  const [content, setContent] = useState("Loading…");

  useEffect(() => {
    if (!path) {
      setContent(missingMessage);
      return;
    }
    let cancelled = false;
    fetch(`/${path}`)
      .then((r) => r.text())
      .then((text) => {
        if (!cancelled) setContent(text || "(empty)");
      })
      .catch(() => {
        if (!cancelled) setContent("Could not load this log.");
      });
    return () => {
      cancelled = true;
    };
  }, [path, missingMessage, reloadKey]);

  return content;
};

/**
 * A downloaded trace.zip is meaningless on its own — it only opens in the
 * Playwright trace viewer, so say that right next to the download.
 */
const TraceButton = ({ path }: { path: string }) => {
  const [showHelp, setShowHelp] = useState(false);
  const fileName = path.split("/").pop() ?? "trace.zip";

  useEffect(() => {
    if (!showHelp) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowHelp(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [showHelp]);

  return (
    <div className="relative">
      <div className="flex">
        <a href={`/${path}`} download className="btn-secondary !rounded-r-none">
          <Download className="w-4 h-4" /> Trace
        </a>
        <button
          onClick={() => setShowHelp((v) => !v)}
          aria-label="How to open a trace"
          aria-expanded={showHelp}
          className="btn-secondary !rounded-l-none !px-2 border-l-0"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
      </div>

      {showHelp && (
        <div className="absolute right-0 top-full mt-2 w-80 z-20 card p-4 shadow-pop text-left">
          <p className="text-xs text-ink-soft leading-relaxed">
            A trace is a zip the Playwright viewer reads — unzipping it by hand
            shows only its raw parts. Open it with:
          </p>
          <pre className="mt-2 mb-3 p-2.5 rounded-lg bg-canvas border border-line font-mono text-[11px] text-ink-soft overflow-x-auto">
            npx playwright show-trace {fileName}
          </pre>
          <p className="text-xs text-ink-soft leading-relaxed">
            or drop the file on{" "}
            <a
              href="https://trace.playwright.dev"
              target="_blank"
              rel="noreferrer"
              className="text-primary-600 font-medium hover:underline"
            >
              trace.playwright.dev
            </a>{" "}
            — it runs locally in your browser and uploads nothing.
          </p>
        </div>
      )}
    </div>
  );
};

export const RunDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading } = useRun(id!);
  const { data: testCase } = useTestCase(run?.test_case_id ?? "");
  const remove = useDeleteRuns();

  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("timeline");
  const [confirming, setConfirming] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const consoleLog = run?.evidences?.find((e) => e.type === "console_log");
  const networkLog = run?.evidences?.find((e) => e.type === "network_log");
  const video = run?.evidences?.find((e) => e.type === "video");
  const trace = run?.evidences?.find((e) => e.type === "trace");

  const consoleContent = useLogFile(
    consoleLog?.file_path,
    "No console output was captured.",
    run?.status,
  );
  const networkContent = useLogFile(
    networkLog?.file_path,
    "No network activity was captured.",
    run?.status,
  );

  if (isLoading) return <SkeletonLoader className="h-96" />;
  if (!run) return <p className="text-ink-muted">Run not found.</p>;

  const isRunning = run.status === "running" || run.status === "pending";
  const duration =
    run.finished_at && run.started_at
      ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
      : null;

  const passed = run.step_results.filter((s) => s.status === "passed").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <Link
          to={`/test-cases/${run.test_case_id}`}
          className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-primary-600 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to test case
        </Link>
        {run.batch_id && (
          <Link
            to={`/sequences/${run.batch_id}`}
            className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-primary-600 transition-colors"
          >
            <Layers className="w-4 h-4" /> Part of a sequence
          </Link>
        )}
      </div>

      <header className="card p-6">
        <div className="flex flex-wrap gap-4 justify-between items-start">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-ink">
                {testCase?.name || "Test run"}
              </h1>
              <StatusBadge status={run.status} />
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-muted mt-3">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                {duration !== null ? formatDuration(duration) : "in progress"}
              </span>
              <span>Started {formatDate(run.started_at)}</span>
              <span className="capitalize">Trigger: {run.trigger_source}</span>
              <span className="mono-chip">{run.id.slice(0, 8)}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-2xl font-bold tabular-nums text-ink">
                {passed}/{testCase?.steps?.length ?? run.step_results.length}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-ink-muted">
                steps passed
              </div>
            </div>
            {trace && <TraceButton path={trace.file_path} />}
            <button
              type="button"
              onClick={() => setConfirming(true)}
              disabled={isRunning}
              aria-label="Delete run"
              title={isRunning ? "This run is still going" : "Delete this run"}
              className="btn-ghost !p-2 hover:text-rose-500 hover:bg-rose-50"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {isRunning && (
          <p className="mt-5 rounded-xl bg-sky-50 border border-sky-100 px-4 py-3 text-sm text-sky-600">
            Chrome is open and replaying this test. Steps appear here as they
            finish.
          </p>
        )}

        {run.error_message && (
          <pre className="mt-5 rounded-xl bg-rose-50 border border-rose-100 px-4 py-3 text-xs text-rose-600 font-mono whitespace-pre-wrap overflow-x-auto">
            {run.error_message}
          </pre>
        )}

        <JiraSyncNote
          className="mt-5"
          issueKey={run.jira_issue_key}
          status={run.jira_status}
          error={run.jira_error}
        />
      </header>

      <div className="flex gap-1 p-1 rounded-2xl bg-surface border border-line w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-colors ${
              activeTab === tab.id
                ? "bg-primary-50 text-primary-600"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            <tab.icon className="w-4 h-4" /> {tab.label}
          </button>
        ))}
      </div>

      <div className="min-h-[380px]">
        {activeTab === "timeline" && (
          <RunTimeline
            results={run.step_results}
            steps={testCase?.steps}
            isRunning={isRunning}
            onImageClick={setSelectedImage}
          />
        )}

        {activeTab === "video" && (
          <div className="card p-4 space-y-4">
            {video ? (
              <>
                {/* Silent screen capture of the run: no audio track, so no captions. */}
                <video
                  src={`/${video.file_path}`}
                  controls
                  muted
                  aria-label="Silent screen recording of the test run"
                  className="w-full max-h-[62vh] rounded-xl border border-line bg-canvas"
                />
                <details>
                  <summary className="text-xs text-ink-muted cursor-pointer hover:text-ink">
                    Frames look blank? Step through the screenshots instead
                  </summary>
                  <div className="mt-3">
                    <Filmstrip
                      results={run.step_results}
                      onFrameClick={setSelectedImage}
                    />
                  </div>
                </details>
              </>
            ) : (
              <>
                <Filmstrip
                  results={run.step_results}
                  onFrameClick={setSelectedImage}
                />
                <p className="text-xs text-ink-muted leading-relaxed">
                  Played back from the screenshot the runner took after every
                  step. A film file was not kept for this run — headed Chrome
                  only paints while its window is in front. Set{" "}
                  <code className="mono-chip">HEADLESS=true</code> for a video
                  file every time.
                </p>
              </>
            )}
          </div>
        )}

        {activeTab === "console" && (
          <pre className="card p-4 font-mono text-xs text-ink-soft whitespace-pre-wrap max-h-[560px] overflow-auto">
            {consoleContent}
          </pre>
        )}

        {activeTab === "network" && (
          <pre className="card p-4 font-mono text-xs text-ink-soft whitespace-pre-wrap max-h-[560px] overflow-auto">
            {networkContent}
          </pre>
        )}
      </div>

      {selectedImage && (
        <EvidenceViewer
          evidence={null}
          screenshotPath={selectedImage}
          onClose={() => setSelectedImage(null)}
        />
      )}

      {confirming && (
        <ConfirmDialog
          title="Delete this run?"
          body={
            <>
              The result and all its evidence — screenshots, video, trace and
              logs — will be removed from disk. This cannot be undone.
            </>
          }
          confirmLabel="Delete run"
          isBusy={remove.isPending}
          error={deleteError}
          onConfirm={() => {
            setDeleteError("");
            remove.mutate([run.id], {
              onSuccess: () => navigate(`/test-cases/${run.test_case_id}`),
              onError: (e: any) =>
                setDeleteError(
                  e?.response?.data?.message || "Could not delete this run.",
                ),
            });
          }}
          onCancel={() => {
            setConfirming(false);
            setDeleteError("");
          }}
        />
      )}
    </div>
  );
};
