import type { JiraOutput, JiraTicketItem } from "../models/sprintGuard.types";
import {
  ArrowLeft,
  Bookmark,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Code,
  FileText,
  Layers,
  RefreshCw,
  Tag,
  User,
  Users,
} from "lucide-react";
import { useState } from "react";

interface JiraDetailsPageProps {
  jiraOutput: JiraOutput;
  onBack: () => void;
  onStartNew: () => void;
}

function TicketCard({
  ticket,
  isStory,
}: {
  ticket: JiraTicketItem;
  isStory: boolean;
}) {
  const [expanded, setExpanded] = useState(isStory);

  const statusColor: Record<string, string> = {
    "To Do": "bg-slate-100 text-slate-700",
    "In Progress": "bg-blue-100 text-blue-700",
    Completed: "bg-emerald-100 text-emerald-700",
    Done: "bg-emerald-100 text-emerald-700",
  };

  const taskTypeColor: Record<string, string> = {
    Story: "bg-emerald-600",
    "Sub-task": "bg-blue-500",
    Frontend: "bg-purple-500",
    Backend: "bg-orange-500",
    Database: "bg-cyan-500",
    API: "bg-pink-500",
    Testing: "bg-yellow-500",
    Documentation: "bg-gray-500",
  };

  return (
    <div
      className={`border rounded-xl overflow-hidden ${isStory ? "border-emerald-200 bg-emerald-50/30" : "border-slate-200 bg-white"}`}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-white/50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Task Type Badge */}
          <span
            className={`w-2 h-8 rounded-full shrink-0 ${taskTypeColor[ticket.type || ticket.task] || taskTypeColor.Story}`}
          />

          {/* Ticket ID */}
          <span className="font-mono text-sm font-semibold text-blue-600 shrink-0">
            {ticket.id}
          </span>

          {/* Summary */}
          <span className="font-medium text-slate-800 truncate">
            {ticket.summary}
          </span>
        </div>

        <div className="flex items-center gap-2 ml-4 shrink-0">
          {/* Type Badge */}
          <span
            className={`px-2 py-0.5 rounded text-xs font-medium text-white ${taskTypeColor[ticket.type || ticket.task] || "bg-slate-500"}`}
          >
            {ticket.type || ticket.task}
          </span>

          {/* Status Badge */}
          <span
            className={`px-2 py-0.5 rounded text-xs font-medium ${statusColor[ticket.status] || statusColor["To Do"]}`}
          >
            {ticket.status}
          </span>

          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100 pt-4">
          {/* Details Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white/60 rounded-lg p-3 border border-slate-100">
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Users className="w-3 h-3" /> Squad
              </span>
              <p className="text-sm font-medium text-slate-800 mt-1">
                {ticket.squad}
              </p>
            </div>
            <div className="bg-white/60 rounded-lg p-3 border border-slate-100">
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <User className="w-3 h-3" /> Owner
              </span>
              <p className="text-sm font-medium text-slate-800 mt-1">
                {ticket.owner}
              </p>
            </div>
            <div className="bg-white/60 rounded-lg p-3 border border-slate-100">
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Bookmark className="w-3 h-3" /> Sprint
              </span>
              <p className="text-sm font-medium text-slate-800 mt-1">
                {ticket.sprint}
              </p>
            </div>
            {ticket.estimate && (
              <div className="bg-white/60 rounded-lg p-3 border border-slate-100">
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Estimate
                </span>
                <p className="text-sm font-medium text-slate-800 mt-1">
                  {ticket.estimate}
                </p>
              </div>
            )}
            {ticket.priority && (
              <div className="bg-white/60 rounded-lg p-3 border border-slate-100">
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Tag className="w-3 h-3" /> Priority
                </span>
                <p className="text-sm font-medium text-slate-800 mt-1">
                  {ticket.priority}
                </p>
              </div>
            )}
          </div>

          {/* Description */}
          {ticket.description && (
            <div className="bg-white/60 rounded-lg p-4 border border-slate-100">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <FileText className="w-3 h-3" /> Description
              </span>
              <p className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
                {ticket.description}
              </p>
            </div>
          )}

          {/* Acceptance Criteria */}
          {ticket.acceptanceCriteria &&
            ticket.acceptanceCriteria.length > 0 && (
              <div>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide flex items-center gap-1 mb-2">
                  <CheckCircle className="w-3 h-3 text-emerald-500" />{" "}
                  Acceptance Criteria
                </span>
                <div className="space-y-2">
                  {ticket.acceptanceCriteria.map((ac, i) => (
                    <div
                      key={`ac-${ticket.id}-${i}`}
                      className="bg-emerald-50 border-l-4 border-emerald-500 p-3 rounded-r-lg"
                    >
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">
                        {ac}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
        </div>
      )}
    </div>
  );
}

export function JiraDetailsPage({
  jiraOutput,
  onBack,
  onStartNew,
}: JiraDetailsPageProps) {
  const [showRawData, setShowRawData] = useState(false);

  const tickets = jiraOutput.tickets || [];
  const storyTicket = tickets.find((t) => t.task === "Story");
  const subTasks = tickets.filter((t) => t.task === "Sub-task");

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-800 to-slate-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Summary
          </button>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onStartNew}
              className="flex items-center gap-2 px-3 py-1.5 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              Create Another
            </button>
          </div>
        </div>

        {storyTicket && (
          <div className="mt-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-blue-400 font-mono text-sm font-semibold">
                {storyTicket.id}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-300">
                {storyTicket.task}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-500/20 text-slate-300">
                {storyTicket.status}
              </span>
            </div>
            <h1 className="text-xl font-semibold text-white">
              {storyTicket.summary}
            </h1>
            <div className="flex items-center gap-4 mt-2 text-sm text-slate-400">
              <span className="flex items-center gap-1">
                <Users className="w-3.5 h-3.5" />
                {storyTicket.squad}
              </span>
              <span className="flex items-center gap-1">
                <Bookmark className="w-3.5 h-3.5" />
                {storyTicket.sprint}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100 text-center">
            <Layers className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
            <span className="text-2xl font-bold text-emerald-700">1</span>
            <p className="text-xs text-emerald-600 mt-1">Story</p>
          </div>
          <div className="bg-blue-50 rounded-xl p-4 border border-blue-100 text-center">
            <FileText className="w-6 h-6 text-blue-600 mx-auto mb-2" />
            <span className="text-2xl font-bold text-blue-700">
              {subTasks.length}
            </span>
            <p className="text-xs text-blue-600 mt-1">Sub-tasks</p>
          </div>
          <div className="bg-purple-50 rounded-xl p-4 border border-purple-100 text-center">
            <CheckCircle className="w-6 h-6 text-purple-600 mx-auto mb-2" />
            <span className="text-2xl font-bold text-purple-700">
              {jiraOutput.test_case_count}
            </span>
            <p className="text-xs text-purple-600 mt-1">Test Cases</p>
          </div>
        </div>

        {/* Tickets Section */}
        <div>
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4 flex items-center gap-2">
            <Layers className="w-4 h-4 text-slate-400" />
            Tickets ({tickets.length})
          </h3>

          <div className="space-y-3">
            {/* Story Ticket */}
            {storyTicket && <TicketCard ticket={storyTicket} isStory={true} />}

            {/* Sub-task Tickets */}
            {subTasks.length > 0 && (
              <div className="ml-6 space-y-2 border-l-2 border-slate-200 pl-4">
                <span className="text-xs font-medium text-slate-500 uppercase">
                  Sub-tasks
                </span>
                {subTasks.map((task) => (
                  <TicketCard key={task.id} ticket={task} isStory={false} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Not Found Section */}
        {jiraOutput.notFound && jiraOutput.notFound.length > 0 && (
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <h3 className="text-sm font-semibold text-amber-800 mb-2">
              Not Found
            </h3>
            <ul className="text-sm text-amber-700">
              {jiraOutput.notFound.map((item, i) => (
                <li key={`notfound-${i}`}>• {item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Raw Data Section */}
        <div>
          <button
            type="button"
            onClick={() => setShowRawData(!showRawData)}
            className="flex items-center gap-2 text-sm font-semibold text-slate-700 uppercase tracking-wide hover:text-blue-600 transition-colors"
          >
            <Code className="w-4 h-4" />
            View Raw JSON Response
            {showRawData ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
          {showRawData && (
            <div className="mt-3 bg-slate-900 rounded-lg p-4 overflow-auto max-h-96">
              <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">
                {JSON.stringify(
                  {
                    tickets: jiraOutput.tickets,
                    notFound: jiraOutput.notFound,
                  },
                  null,
                  2,
                )}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
