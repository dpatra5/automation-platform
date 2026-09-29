import { useEffect, useMemo } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { useSession } from "./hooks/useSession";
import {
  ProgressSteps,
  ProblemInput,
  SummaryReview,
  StoryDescriptionReview,
  SDLCReview,
  StoryTasksReview,
  TestCasesReview,
  JiraSuccess,
  JiraDetailsPage,
  ErrorToast,
} from "./components";
import type { Step } from "./models/sprintGuard.types";

// Route-level SprintGuard workflow. Same six-step UI the standalone SprintGuard
// app exposes — dropped into the platform's page slot.
export function SprintGuardWorkflow() {
  const { state, actions } = useSession();

  useEffect(() => {
    actions.createSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const completedSteps = useMemo(
    () => ({
      1: !!state.summary,
      2: !!state.storyDescription,
      3: !!state.sdlcTestplan,
      4: !!state.storyTasks,
      5: !!state.testCases,
      6: !!state.jiraOutput,
    }),
    [
      state.summary,
      state.storyDescription,
      state.sdlcTestplan,
      state.storyTasks,
      state.testCases,
      state.jiraOutput,
    ],
  );

  const displayStep = state.viewingStep || state.currentStep;
  const isViewingPastStep =
    state.viewingStep !== null && state.viewingStep < state.currentStep;

  const isProcessing = [
    "analyzing",
    "creating_story_description",
    "creating_sdlc_testplan",
    "creating_story_subtasks",
    "creating_test_cases",
    "creating_jira",
  ].includes(state.sessionState);

  const handleStepClick = (step: Step) => {
    if (completedSteps[step]) actions.viewStep(step);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="h-1 bg-gradient-to-r from-slate-900 via-slate-600 to-slate-900" />
      <div className="max-w-5xl mx-auto px-6 py-8">
        <header className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-slate-900 rounded-lg flex items-center justify-center">
              <svg
                className="w-5 h-5 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900">
                SprintGuard
              </h1>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
            <span>Ready</span>
          </div>
        </header>

        <ProgressSteps
          currentStep={state.currentStep}
          viewingStep={state.viewingStep}
          sessionState={state.sessionState}
          completedSteps={completedSteps}
          skipSdlc={state.skipSdlc}
          onStepClick={handleStepClick}
          onReturnToCurrentStep={actions.returnToCurrentStep}
        />

        {!isViewingPastStep && state.message && (
          <div className="mb-6">
            <p className="text-xs text-slate-500 text-center">
              {state.message}
            </p>
          </div>
        )}

        <main className="relative space-y-6">
          {isProcessing && !isViewingPastStep && (
            <div className="absolute inset-0 bg-white/90 backdrop-blur-sm z-10 flex items-center justify-center rounded-xl">
              <div className="text-center">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin mx-auto mb-3" />
                <p className="text-sm text-slate-600 font-medium">Processing</p>
                <p className="text-xs text-slate-400 mt-1">{state.message}</p>
              </div>
            </div>
          )}

          {!isViewingPastStep &&
            (state.sessionState === "awaiting_problem" ||
              (state.currentStep === 1 && !state.summary)) && (
              <ProblemInput
                value={state.problemStatement}
                onChange={actions.setProblemStatement}
                skipSdlc={state.skipSdlc}
                onSkipSdlcChange={actions.setSkipSdlc}
                onSubmit={actions.analyzeProblem}
                isLoading={state.isLoading}
              />
            )}

          {((isViewingPastStep && displayStep === 1) ||
            (!isViewingPastStep && state.sessionState === "review_summary")) &&
            state.summary && (
              <SummaryReview
                summary={state.summary}
                problemStatement={state.problemStatement}
                isLoading={state.isLoading}
                onApprove={() => actions.reviewSummary(true)}
                onModify={actions.modifySummary}
                isReadOnly={isViewingPastStep}
              />
            )}

          {((isViewingPastStep && displayStep === 2) ||
            (!isViewingPastStep &&
              state.sessionState === "review_story_description")) &&
            state.storyDescription && (
              <StoryDescriptionReview
                storyDescription={state.storyDescription}
                isLoading={state.isLoading}
                onApprove={() => actions.reviewStoryDescription(true)}
                onModify={actions.modifyStoryDescription}
                isReadOnly={isViewingPastStep}
              />
            )}

          {((isViewingPastStep && displayStep === 3) ||
            (!isViewingPastStep &&
              state.sessionState === "review_sdlc_testplan")) &&
            state.sdlcTestplan && (
              <SDLCReview
                sdlcTestplan={state.sdlcTestplan}
                isLoading={state.isLoading}
                onApprove={() => actions.reviewSDLC(true)}
                onModify={actions.modifySDLC}
                isReadOnly={isViewingPastStep}
              />
            )}

          {((isViewingPastStep && displayStep === 4) ||
            (!isViewingPastStep &&
              state.sessionState === "review_story_subtasks")) &&
            state.storyTasks && (
              <StoryTasksReview
                storyTasks={state.storyTasks}
                isLoading={state.isLoading}
                onApprove={() => actions.reviewStoryTasks(true)}
                onModify={actions.modifyStoryTasks}
                isReadOnly={isViewingPastStep}
              />
            )}

          {((isViewingPastStep && displayStep === 5) ||
            (!isViewingPastStep &&
              state.sessionState === "review_test_cases")) &&
            state.testCases && (
              <>
                <TestCasesReview
                  testCases={state.testCases}
                  isLoading={state.isLoading}
                  onApprove={() => actions.reviewTestCases(true)}
                  onModify={actions.modifyTestCases}
                  isReadOnly={isViewingPastStep}
                />

                {/* Automation Pipeline hidden per product decision. */}
              </>
            )}

          {((isViewingPastStep && displayStep === 6) ||
            (!isViewingPastStep && state.sessionState === "completed")) &&
            state.jiraOutput &&
            !state.showJiraDetails && (
              <JiraSuccess
                jiraOutput={state.jiraOutput}
                onStartNew={actions.startNewStory}
                onViewDetails={actions.viewJiraDetails}
              />
            )}

          {state.showJiraDetails && state.jiraOutput && (
            <JiraDetailsPage
              jiraOutput={state.jiraOutput}
              onBack={actions.closeJiraDetails}
              onStartNew={actions.startNewStory}
            />
          )}

          {!isViewingPastStep && state.sessionState === "error" && (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
              <div className="w-12 h-12 mx-auto mb-4 bg-red-100 rounded-full flex items-center justify-center">
                <AlertCircle className="w-6 h-6 text-red-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                Something went wrong
              </h3>
              <p className="text-sm text-slate-500 mb-6 max-w-md mx-auto">
                {state.error || "An unexpected error occurred"}
              </p>
              <button
                type="button"
                onClick={actions.startNewStory}
                className="px-5 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium"
              >
                Start Over
              </button>
            </div>
          )}
        </main>

        {state.error && state.sessionState !== "error" && (
          <ErrorToast
            message={state.error}
            onClose={() => actions.setError(null)}
          />
        )}

        <footer className="mt-16 pb-8">
          <div className="flex items-center justify-center gap-6 text-xs text-slate-400">
            <span className="w-px h-3 bg-slate-200" />
            <span>v1.0.0</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
