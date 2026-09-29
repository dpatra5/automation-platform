import type { JiraOutput } from "../models/sprintGuard.types";
import {
  CheckCircle,
  Eye,
  Layers,
  ListChecks,
  FileText,
  RefreshCw,
} from "lucide-react";

interface JiraSuccessProps {
  jiraOutput: JiraOutput;
  onStartNew: () => void;
  onViewDetails: () => void;
}

export function JiraSuccess({
  jiraOutput,
  onStartNew,
  onViewDetails,
}: JiraSuccessProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Success Header */}
      <div className="bg-emerald-600 px-6 py-8 text-center">
        <div className="w-14 h-14 bg-white rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-emerald-600" />
        </div>
        <h2 className="text-xl font-semibold text-white mb-1">
          Jira Tickets Created
        </h2>
        <p className="text-emerald-100 text-sm">
          All items have been created successfully
        </p>
      </div>

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Main Story */}
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <Layers className="w-5 h-5 text-slate-600" />
              <div>
                <span className="text-xs text-slate-500 font-medium">
                  Story
                </span>
                <h3 className="text-sm font-semibold text-slate-800">
                  {jiraOutput.story_title}
                </h3>
              </div>
            </div>
            <span className="text-sm font-mono font-medium text-slate-700 bg-slate-200 px-2 py-1 rounded">
              {jiraOutput.story_key}
            </span>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-100">
            <ListChecks className="w-5 h-5 text-slate-400 mx-auto mb-2" />
            <span className="text-2xl font-semibold text-slate-800">
              {jiraOutput.sub_task_keys.length}
            </span>
            <p className="text-xs text-slate-500 mt-1">Sub-tasks</p>
          </div>
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-100">
            <FileText className="w-5 h-5 text-slate-400 mx-auto mb-2" />
            <span className="text-2xl font-semibold text-slate-800">
              {jiraOutput.test_case_count}
            </span>
            <p className="text-xs text-slate-500 mt-1">Test Cases</p>
          </div>
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-100">
            <CheckCircle className="w-5 h-5 text-emerald-500 mx-auto mb-2" />
            <span className="text-2xl font-semibold text-slate-800">
              {jiraOutput.created_tickets.length}
            </span>
            <p className="text-xs text-slate-500 mt-1">Total</p>
          </div>
        </div>

        {/* Created Tickets List */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">
            Created Tickets
          </h4>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {jiraOutput.created_tickets.map((ticket, index) => (
              <div
                key={ticket.key || index}
                className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      ticket.type === "Story"
                        ? "bg-slate-200 text-slate-700"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {ticket.type}
                  </span>
                  <span className="text-sm text-slate-700">{ticket.title}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-slate-500">
                    {ticket.key}
                  </span>
                  <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs">
                    {ticket.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={onViewDetails}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors text-sm font-medium"
          >
            <Eye className="w-4 h-4" />
            View Jira Details
          </button>
          <button
            type="button"
            onClick={onStartNew}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors text-sm font-medium"
          >
            <RefreshCw className="w-4 h-4" />
            Create Another Story
          </button>
        </div>
      </div>
    </div>
  );
}
