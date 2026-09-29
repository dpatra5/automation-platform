import { useEffect, useState } from "react";
import {
  ExternalLink,
  Loader2,
  Save,
  Ticket,
  AlertTriangle,
  X,
} from "lucide-react";
import { Project } from "../api/types";
import { integrationsApi } from "../api/integrations";
import { useJiraStatus } from "../hooks/useAssertions";
import { useUpdateProject } from "../hooks/useProjects";

interface Props {
  project: Project;
}

const KEY_PATTERN = /^[A-Z][A-Z0-9_]{1,20}-\d{1,10}$/;

type Feedback = { tone: "ok" | "warn"; text: string } | null;

const messageOf = (error: any, fallback: string) =>
  error?.response?.data?.message ||
  error?.response?.data?.detail ||
  error?.message ||
  fallback;

/**
 * The Jira Test Execution issue a project reports into.
 *
 * The key is verified against Jira before it is stored — a typo that silently
 * swallows every run report is worse than no integration at all.
 */
export const JiraCard = ({ project }: Props) => {
  const { data: jira, isLoading } = useJiraStatus();
  const updateProject = useUpdateProject();

  const [key, setKey] = useState(project.jira_key ?? "");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setKey(project.jira_key ?? "");
  }, [project.jira_key]);

  const trimmed = key.trim().toUpperCase();
  const dirty = trimmed !== (project.jira_key ?? "");
  const malformed = trimmed.length > 0 && !KEY_PATTERN.test(trimmed);

  const verify = async () => {
    setChecking(true);
    setFeedback(null);
    try {
      const { issue } = await integrationsApi.validateJiraKey(trimmed);
      setFeedback({
        tone: "ok",
        text: `${issue.key} — ${issue.summary || issue.issue_type}`,
      });
    } catch (e) {
      setFeedback({
        tone: "warn",
        text: messageOf(e, "Could not reach Jira."),
      });
    } finally {
      setChecking(false);
    }
  };

  const save = () => {
    setFeedback(null);
    updateProject.mutate(
      { id: project.id, changes: { jira_key: trimmed || null } },
      {
        onSuccess: () =>
          setFeedback({
            tone: "ok",
            text: trimmed ? `Linked to ${trimmed}.` : "Jira link removed.",
          }),
        onError: (e) =>
          setFeedback({
            tone: "warn",
            text: messageOf(e, "Could not save the key."),
          }),
      },
    );
  };

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Ticket className="w-4 h-4 text-primary-500" />
        <h3 className="text-sm font-semibold text-ink">Jira</h3>
      </div>

      {!isLoading && !jira?.configured ? (
        <p className="text-xs text-ink-muted leading-relaxed">
          Jira is not configured on the backend. Add{" "}
          <code className="mono-chip">JIRA_URL</code> and{" "}
          <code className="mono-chip">JIRA_TOKEN</code> to{" "}
          <code className="mono-chip">backend/.env</code> and restart it to link
          this project to a Test Execution issue.
        </p>
      ) : (
        <>
          <p className="text-xs text-ink-muted leading-relaxed">
            Finished runs comment on this issue with their evidence attached. It
            has to be a{" "}
            <span className="font-medium text-ink-soft">
              {jira?.required_issue_type ?? "Test Execution"}
            </span>{" "}
            issue.
          </p>

          <div>
            <label className="label" htmlFor="jira-key">
              Issue key
            </label>
            <div className="flex gap-2">
              <input
                id="jira-key"
                type="text"
                className="field font-mono text-xs"
                placeholder="JGQE-23122"
                value={key}
                onChange={(e) => {
                  setKey(e.target.value.toUpperCase());
                  setFeedback(null);
                }}
              />
              {project.jira_key && !dirty && (
                <button
                  onClick={() => {
                    setKey("");
                    setFeedback(null);
                  }}
                  aria-label="Remove the Jira link"
                  className="btn-secondary !px-2.5"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            {malformed && (
              <p className="text-[11px] text-amber-600 mt-1">
                Keys look like JGQE-23122 — a project prefix, a hyphen, then the
                number.
              </p>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={verify}
              disabled={!trimmed || malformed || checking}
              className="btn-secondary !py-1.5 text-xs"
            >
              {checking ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Ticket className="w-3.5 h-3.5" />
              )}
              Verify
            </button>
            <button
              onClick={save}
              disabled={!dirty || malformed || updateProject.isPending}
              className="btn-primary !py-1.5 text-xs"
            >
              <Save className="w-3.5 h-3.5" />{" "}
              {updateProject.isPending ? "Saving…" : "Save"}
            </button>
          </div>

          {feedback && (
            <div
              className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-xs ${
                feedback.tone === "ok"
                  ? "bg-mint-50 border-mint-100 text-mint-600"
                  : "bg-amber-50 border-amber-100 text-amber-600"
              }`}
            >
              {feedback.tone === "warn" && (
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
              )}
              <span>{feedback.text}</span>
            </div>
          )}

          {project.jira_browse_url && !dirty && (
            <a
              href={project.jira_browse_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary-600 hover:underline"
            >
              Open {project.jira_key} <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </>
      )}
    </div>
  );
};
