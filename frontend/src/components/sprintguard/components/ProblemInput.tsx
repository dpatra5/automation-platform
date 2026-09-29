import { Loader2, ArrowRight } from "lucide-react";

interface ProblemInputProps {
  value: string;
  onChange: (value: string) => void;
  skipSdlc: boolean;
  onSkipSdlcChange: (skip: boolean) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export function ProblemInput({
  value,
  onChange,
  skipSdlc,
  onSkipSdlcChange,
  onSubmit,
  isLoading,
}: ProblemInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey && e.key === "Enter") {
      onSubmit();
    }
  };

  const charPercentage = Math.min((value.length / 7000) * 100, 100);

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden fade-in">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100">
        <h2 className="text-lg font-semibold text-slate-900">
          Problem Statement
        </h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Describe the problem or feature you want to create a Jira story for
        </p>
      </div>

      {/* Content */}
      <div className="p-6">
        <textarea
          className="w-full min-h-[200px] p-4 border border-slate-200 rounded-lg resize-y text-slate-700 text-sm placeholder-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 transition-all outline-none"
          placeholder="Example: We need to implement a user authentication system that supports OAuth2.0, social login providers (Google, GitHub), and traditional email/password authentication. The system should include rate limiting, session management, and support for multi-factor authentication..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={7000}
        />

        {/* Character count */}
        <div className="mt-3 flex items-center justify-between">
          <span className="text-xs text-slate-400 flex items-center gap-2">
            <kbd className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono">
              Ctrl + Enter
            </kbd>
            <span>to submit</span>
          </span>
          <div className="flex items-center gap-3">
            <div className="w-24 h-1 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  value.length > 6000 ? "bg-amber-500" : "bg-slate-400"
                }`}
                style={{ width: `${charPercentage}%` }}
              />
            </div>
            <span
              className={`text-xs font-medium ${value.length > 6000 ? "text-amber-600" : "text-slate-400"}`}
            >
              {value.length.toLocaleString()}
            </span>
          </div>
        </div>

        {/* Tips */}
        <div className="mt-5 p-4 bg-slate-50 rounded-lg">
          <p className="text-xs font-medium text-slate-600 mb-2">
            Tips for better results
          </p>
          <ul className="text-xs text-slate-500 space-y-1">
            <li className="flex items-start gap-2">
              <span className="text-slate-300 mt-0.5">•</span>
              Include the business context and goals
            </li>
            <li className="flex items-start gap-2">
              <span className="text-slate-300 mt-0.5">•</span>
              Mention technical requirements or constraints
            </li>
            <li className="flex items-start gap-2">
              <span className="text-slate-300 mt-0.5">•</span>
              Describe who will use this feature
            </li>
          </ul>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 space-y-4">
        {/* Skip SDLC Option */}
        <label className="flex items-center gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={skipSdlc}
            onChange={(e) => onSkipSdlcChange(e.target.checked)}
            className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500 focus:ring-offset-0"
          />
          <div className="flex-1">
            <span className="text-sm font-medium text-slate-700 group-hover:text-slate-900">
              Skip SDLC Plan
            </span>
            <p className="text-xs text-slate-500 mt-0.5">
              Go directly to Tasks & Test Cases (faster workflow)
            </p>
          </div>
        </label>

        <button
          type="button"
          className="w-full flex items-center justify-center gap-2 px-5 py-3 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={onSubmit}
          disabled={isLoading || value.length < 10}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Analyzing...</span>
            </>
          ) : (
            <>
              <span>Analyze Problem Statement</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
