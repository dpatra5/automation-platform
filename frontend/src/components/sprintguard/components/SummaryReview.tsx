import { ReviewCard } from "./ReviewCard";
import type { SummaryData } from "../models/sprintGuard.types";
import { AlertTriangle, FileText } from "lucide-react";

interface SummaryReviewProps {
  summary: SummaryData;
  problemStatement?: string;
  isLoading: boolean;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isReadOnly?: boolean;
}

const complexityColors = {
  Low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Medium: "bg-amber-50 text-amber-700 border-amber-200",
  High: "bg-red-50 text-red-700 border-red-200",
};

export function SummaryReview({
  summary,
  problemStatement,
  isLoading,
  onApprove,
  onModify,
  isReadOnly = false,
}: SummaryReviewProps) {
  return (
    <ReviewCard
      title="Problem Analysis"
      onApprove={onApprove}
      onModify={onModify}
      isLoading={isLoading}
      approveLabel="Approve & Continue"
      isReadOnly={isReadOnly}
    >
      <div className="space-y-6">
        {/* Problem Statement */}
        {problemStatement && (
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-200">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h4 className="text-xs font-medium text-blue-700 uppercase tracking-wider mb-2">
                  Your Problem Statement
                </h4>
                <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
                  {problemStatement}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Summary */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <p className="text-sm text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-lg border border-slate-100">
            {summary.summary || "No summary available"}
          </p>
        </div>

        {/* Key Points */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Key Points
          </h4>
          {summary.key_points.length > 0 ? (
            <ul className="space-y-2">
              {summary.key_points.map((point, index) => (
                <li
                  key={`point-${point.slice(0, 20)}-${index}`}
                  className="flex items-start gap-3 text-sm"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 mt-2 flex-shrink-0" />
                  <span className="text-slate-700">{point}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400 italic">
              No key points identified
            </p>
          )}
        </div>

        {/* Scope & Complexity */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Suggested Scope
            </h4>
            <p className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100">
              {Array.isArray(summary.suggested_scope)
                ? summary.suggested_scope.join(", ")
                : summary.suggested_scope || "Not specified"}
            </p>
          </div>
          <div>
            <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Complexity
            </h4>
            <span
              className={`inline-block px-3 py-1.5 rounded-md text-xs font-medium border ${
                complexityColors[summary.estimated_complexity] ||
                complexityColors.Medium
              }`}
            >
              {summary.estimated_complexity || "Medium"}
            </span>
          </div>
        </div>

        {/* Challenges */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Potential Challenges
          </h4>
          {summary.potential_challenges.length > 0 ? (
            <ul className="space-y-2">
              {summary.potential_challenges.map((challenge, index) => (
                <li
                  key={`challenge-${challenge.slice(0, 20)}-${index}`}
                  className="flex items-start gap-3 text-sm"
                >
                  <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <span className="text-slate-700">{challenge}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400 italic">
              No challenges identified
            </p>
          )}
        </div>
      </div>
    </ReviewCard>
  );
}
