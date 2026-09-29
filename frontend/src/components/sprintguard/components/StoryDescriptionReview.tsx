import { ReviewCard } from "./ReviewCard";
import type { StoryDescriptionData } from "../models/sprintGuard.types";
import { Check } from "lucide-react";

interface StoryDescriptionReviewProps {
  storyDescription: StoryDescriptionData;
  isLoading: boolean;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isReadOnly?: boolean;
}

export function StoryDescriptionReview({
  storyDescription,
  isLoading,
  onApprove,
  onModify,
  isReadOnly = false,
}: StoryDescriptionReviewProps) {
  return (
    <ReviewCard
      title="Story Description"
      onApprove={onApprove}
      onModify={onModify}
      isLoading={isLoading}
      approveLabel="Approve & Continue"
      isReadOnly={isReadOnly}
    >
      <div className="space-y-6">
        {/* Title */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Story Title
          </h4>
          <p className="text-base font-medium text-slate-900 bg-slate-50 p-4 rounded-lg border border-slate-100">
            {storyDescription.title || "Untitled Story"}
          </p>
        </div>

        {/* Description */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Description
          </h4>
          <p className="text-sm text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-lg border border-slate-100 whitespace-pre-wrap">
            {storyDescription.description || "No description available"}
          </p>
        </div>

        {/* Business Value & Persona */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Business Value
            </h4>
            <p className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100">
              {storyDescription.business_value || "Not specified"}
            </p>
          </div>
          <div>
            <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              User Persona
            </h4>
            <p className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100">
              {storyDescription.user_persona || "Not specified"}
            </p>
          </div>
        </div>

        {/* Success Metrics */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Success Metrics
          </h4>
          {storyDescription.success_metrics.length > 0 ? (
            <ul className="space-y-2">
              {storyDescription.success_metrics.map((metric, index) => (
                <li
                  key={`metric-${metric.slice(0, 20)}-${index}`}
                  className="flex items-start gap-3 text-sm"
                >
                  <Check className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                  <span className="text-slate-700">{metric}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400 italic">
              No success metrics defined
            </p>
          )}
        </div>
      </div>
    </ReviewCard>
  );
}
