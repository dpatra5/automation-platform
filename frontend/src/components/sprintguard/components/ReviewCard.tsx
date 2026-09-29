import { useState } from "react";
import { Check, Edit3, Loader2, Send, Eye } from "lucide-react";

interface ReviewCardProps {
  title: string;
  children: React.ReactNode;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isLoading: boolean;
  approveLabel?: string;
  modifyLabel?: string;
  isReadOnly?: boolean;
}

export function ReviewCard({
  title,
  children,
  onApprove,
  onModify,
  isLoading,
  approveLabel = "Approve & Continue",
  modifyLabel = "Request Changes",
  isReadOnly = false,
}: ReviewCardProps) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");

  const handleModifyClick = () => {
    setShowFeedback(true);
  };

  const handleSubmitFeedback = () => {
    if (feedback.trim().length >= 5) {
      onModify(feedback);
      setShowFeedback(false);
      setFeedback("");
    }
  };

  const handleCancel = () => {
    setShowFeedback(false);
    setFeedback("");
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div
        className={`px-6 py-4 border-b ${
          isReadOnly
            ? "bg-amber-50 border-amber-100"
            : "bg-slate-50 border-slate-100"
        }`}
      >
        <div className="flex items-center justify-between">
          <h3
            className={`font-semibold ${isReadOnly ? "text-amber-900" : "text-slate-900"}`}
          >
            {title}
          </h3>
          {isReadOnly && (
            <div className="flex items-center gap-1.5 text-amber-700 text-xs font-medium">
              <Eye className="w-3.5 h-3.5" />
              <span>View Only</span>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">{children}</div>

      {/* Actions */}
      {!isReadOnly && (
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-100">
          {showFeedback ? (
            <div className="space-y-3">
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Describe what changes you'd like..."
                className="w-full p-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-slate-100 focus:border-slate-400 resize-none outline-none"
                rows={3}
                disabled={isLoading}
              />
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={isLoading}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 font-medium disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmitFeedback}
                  disabled={isLoading || feedback.trim().length < 5}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {isLoading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  Submit
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={handleModifyClick}
                disabled={isLoading}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm font-medium disabled:opacity-50"
              >
                <Edit3 className="w-4 h-4" />
                {modifyLabel}
              </button>
              <button
                type="button"
                onClick={onApprove}
                disabled={isLoading}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                {approveLabel}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
