import { Check, Loader2, ArrowRight, Eye, SkipForward } from "lucide-react";
import type { Step, SessionState } from "../models/sprintGuard.types";

interface ProgressStepsProps {
  currentStep: Step;
  viewingStep: Step | null;
  sessionState: SessionState;
  completedSteps: { [key: number]: boolean };
  skipSdlc: boolean;
  onStepClick: (step: Step) => void;
  onReturnToCurrentStep: () => void;
}

const steps = [
  { number: 1, label: "Analysis" },
  { number: 2, label: "Description" },
  { number: 3, label: "SDLC Plan" },
  { number: 4, label: "Tasks" },
  { number: 5, label: "Test Cases" },
  { number: 6, label: "Jira" },
];

const processingStates = new Set<SessionState>([
  "analyzing",
  "creating_story_description",
  "creating_sdlc_testplan",
  "creating_story_subtasks",
  "creating_test_cases",
  "creating_jira",
]);

export function ProgressSteps({
  currentStep,
  viewingStep,
  sessionState,
  completedSteps,
  skipSdlc,
  onStepClick,
  onReturnToCurrentStep,
}: ProgressStepsProps) {
  const isProcessing = processingStates.has(sessionState);
  const activeStep = viewingStep || currentStep;

  const getStepState = (stepNum: number) => {
    const isPast = stepNum < currentStep;
    const isCurrent = stepNum === currentStep;
    const isViewing = stepNum === viewingStep;
    const isClickable = completedSteps[stepNum];
    const isSkipped = skipSdlc && stepNum === 3 && currentStep > 3;
    return { isPast, isCurrent, isViewing, isClickable, isSkipped };
  };

  return (
    <div className="mb-8">
      {/* Viewing Previous Step Banner */}
      {viewingStep && viewingStep < currentStep && (
        <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Eye className="w-4 h-4 text-amber-600" />
            <span className="text-sm text-amber-800">
              Viewing <strong>Step {viewingStep}</strong> —{" "}
              {steps[viewingStep - 1]?.label}
            </span>
          </div>
          <button
            type="button"
            onClick={onReturnToCurrentStep}
            className="text-sm font-medium text-amber-700 hover:text-amber-900 flex items-center gap-1"
          >
            Return to current
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Mobile: Simple indicator */}
      <div className="flex md:hidden items-center justify-center gap-2 text-sm mb-4">
        <span className="font-medium text-slate-900">Step {activeStep}</span>
        <span className="text-slate-400">of 6</span>
        <span className="text-slate-300">—</span>
        <span className="text-slate-600">{steps[activeStep - 1]?.label}</span>
        {isProcessing && !viewingStep && (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400 ml-1" />
        )}
      </div>

      {/* Desktop: Progress bar */}
      <div className="hidden md:block">
        <div className="flex items-center justify-between">
          {steps.map((step, index) => {
            const { isPast, isCurrent, isViewing, isClickable, isSkipped } =
              getStepState(step.number);
            const isLast = index === steps.length - 1;

            return (
              <div key={step.number} className="flex items-center flex-1">
                <button
                  type="button"
                  onClick={() =>
                    isClickable && onStepClick(step.number as Step)
                  }
                  disabled={!isClickable}
                  className={`
                    relative flex flex-col items-center group
                    ${isClickable ? "cursor-pointer" : "cursor-default"}
                  `}
                >
                  {/* Step circle */}
                  <div
                    className={`
                      w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium
                      transition-all duration-200 border-2
                      ${
                        isSkipped
                          ? "border-slate-300 bg-slate-100 text-slate-400"
                          : isViewing
                            ? "border-amber-500 bg-amber-50 text-amber-700"
                            : isPast
                              ? "border-emerald-500 bg-emerald-500 text-white"
                              : isCurrent
                                ? isProcessing
                                  ? "border-slate-400 bg-slate-100 text-slate-600"
                                  : "border-slate-900 bg-slate-900 text-white"
                                : "border-slate-200 bg-white text-slate-400"
                      }
                      ${isClickable && !isCurrent ? "group-hover:border-slate-400" : ""}
                    `}
                  >
                    {isSkipped ? (
                      <SkipForward className="w-4 h-4" />
                    ) : isPast ? (
                      <Check className="w-4 h-4" />
                    ) : isCurrent && isProcessing ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      step.number
                    )}
                  </div>

                  {/* Step label */}
                  <span
                    className={`
                      mt-2 text-xs font-medium whitespace-nowrap
                      ${
                        isSkipped
                          ? "text-slate-400"
                          : isViewing
                            ? "text-amber-700"
                            : isCurrent
                              ? "text-slate-900"
                              : isPast
                                ? "text-slate-600"
                                : "text-slate-400"
                      }
                    `}
                  >
                    {isSkipped ? "Skipped" : step.label}
                  </span>
                </button>

                {/* Connector line */}
                {!isLast && (
                  <div className="flex-1 mx-3 h-px relative top-[-12px]">
                    <div
                      className={`
                        h-full transition-colors duration-300
                        ${isPast ? "bg-emerald-400" : "bg-slate-200"}
                      `}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
