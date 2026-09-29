import React from "react";
import { ExternalLink, Ticket, AlertTriangle } from "lucide-react";
import { JiraSyncStatus } from "../api/types";
import { useJiraStatus } from "../hooks/useAssertions";

interface Props {
  issueKey: string | null;
  status: JiraSyncStatus | null;
  error: string | null;
  className?: string;
}

/**
 * What happened when this result was pushed to Jira.
 *
 * Reporting is deliberately a side effect: a run that passed still passed even
 * if Jira was unreachable. Saying so here is the only way anyone finds out.
 */
export const JiraSyncNote = ({
  issueKey,
  status,
  error,
  className = "",
}: Props) => {
  const { data: jira } = useJiraStatus();

  // "Skipped" is the normal state for a project with no Jira key: stay quiet.
  if (!status || status === "skipped") return null;

  const failed = status === "failed";
  const url =
    jira?.url && issueKey
      ? `${jira.url.replace(/\/$/, "")}/browse/${issueKey}`
      : null;

  return (
    <div
      className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-xs ${className} ${
        failed
          ? "bg-amber-50 border-amber-100 text-amber-600"
          : "bg-mint-50 border-mint-100 text-mint-600"
      }`}
    >
      {failed ? (
        <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
      ) : (
        <Ticket className="w-4 h-4 shrink-0 mt-px" />
      )}
      <div className="min-w-0">
        {failed ? (
          <span>Could not report this to Jira. {error}</span>
        ) : (
          <span>
            Reported to{" "}
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="font-semibold hover:underline inline-flex items-center gap-1"
              >
                {issueKey} <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span className="font-semibold">{issueKey}</span>
            )}{" "}
            with the evidence attached.
            {error && <span className="block mt-1 opacity-80">{error}</span>}
          </span>
        )}
      </div>
    </div>
  );
};
