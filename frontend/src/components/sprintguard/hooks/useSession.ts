import { useState, useCallback } from 'react';
import { api } from '../api/sprintGuardApi';
import type { AppState, Step, SessionResponse } from '../models/sprintGuard.types';

const initialState: AppState = {
  currentStep: 1,
  viewingStep: null,
  sessionId: null,
  sessionState: 'awaiting_problem',
  problemStatement: '',
  skipSdlc: false,
  summary: null,
  storyDescription: null,
  sdlcTestplan: null,
  storyTasks: null,
  testCases: null,
  jiraOutput: null,
  isLoading: false,
  error: null,
  message: 'Enter your problem statement to begin',
  showJiraDetails: false,
};

function mapResponseToState(response: SessionResponse): Partial<AppState> {
  return {
    sessionId: response.session_id,
    sessionState: response.state,
    currentStep: response.current_step as Step,
    problemStatement: response.problem_statement || '',
    skipSdlc: response.skip_sdlc || false,
    summary: response.summary,
    storyDescription: response.story_description,
    sdlcTestplan: response.sdlc_testplan,
    storyTasks: response.story_tasks,
    testCases: response.test_cases,
    jiraOutput: response.jira_output,
    message: response.message,
    error: response.error_message,
  };
}

export function useSession() {
  const [state, setState] = useState<AppState>(initialState);

  const setError = useCallback((error: string | null) => {
    setState((prev) => ({ ...prev, error }));
    if (error) {
      setTimeout(() => setState((prev) => ({ ...prev, error: null })), 5000);
    }
  }, []);

  const setLoading = useCallback((isLoading: boolean) => {
    setState((prev) => ({ ...prev, isLoading }));
  }, []);

  const setProblemStatement = useCallback((problemStatement: string) => {
    setState((prev) => ({ ...prev, problemStatement }));
  }, []);

  const setSkipSdlc = useCallback((skipSdlc: boolean) => {
    setState((prev) => ({ ...prev, skipSdlc }));
  }, []);

  // Navigate to view a specific step (only for completed steps)
  const viewStep = useCallback((step: Step) => {
    setState((prev) => {
      // Can only view steps that have data
      const stepData: Record<number, boolean> = {
        1: !!prev.summary,
        2: !!prev.storyDescription,
        3: !!prev.sdlcTestplan,
        4: !!prev.storyTasks,
        5: !!prev.testCases,
        6: !!prev.jiraOutput,
      };
      
      if (stepData[step]) {
        return { ...prev, viewingStep: step };
      }
      return prev;
    });
  }, []);

  // Return to current step view
  const returnToCurrentStep = useCallback(() => {
    setState((prev) => ({ ...prev, viewingStep: null }));
  }, []);

  // ===================================================================
  // Session Management
  // ===================================================================

  const createSession = useCallback(async () => {
    try {
      const response = await api.createSession();
      setState((prev) => ({ 
        ...prev, 
        sessionId: response.session_id,
        sessionState: response.state,
        message: response.message,
      }));
      return response.session_id;
    } catch (err) {
      console.error('Failed to create session:', err);
      return null;
    }
  }, []);

  const refreshSession = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const response = await api.getSession(state.sessionId);
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh session');
    }
  }, [state.sessionId, setError]);

  // ===================================================================
  // Step 1: Problem Analysis
  // ===================================================================

  const analyzeProblem = useCallback(async () => {
    if (!state.problemStatement.trim()) {
      setError('Please enter a problem statement.');
      return;
    }

    if (state.problemStatement.length < 10) {
      setError('Problem statement is too short. Please provide more details.');
      return;
    }

    setLoading(true);

    try {
      let sessionId = state.sessionId;
      if (!sessionId) {
        sessionId = await createSession();
        if (!sessionId) throw new Error('Failed to create session');
      }

      const response = await api.analyzeProblem(sessionId, {
        problem_statement: state.problemStatement,
        skip_sdlc: state.skipSdlc,
      });

      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze problem statement.');
      setLoading(false);
    }
  }, [state.problemStatement, state.skipSdlc, state.sessionId, createSession, setError, setLoading]);

  const reviewSummary = useCallback(async (approved: boolean) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.reviewSummary(state.sessionId, { approved });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review summary.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  const modifySummary = useCallback(async (feedback: string) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.modifySummary(state.sessionId, { user_feedback: feedback });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to modify summary.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Step 2: Story Description
  // ===================================================================

  const reviewStoryDescription = useCallback(async (approved: boolean) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.reviewStoryDescription(state.sessionId, { approved });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review story description.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  const modifyStoryDescription = useCallback(async (feedback: string) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.modifyStoryDescription(state.sessionId, { user_feedback: feedback });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to modify story description.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Step 3: SDLC & Test Plan
  // ===================================================================

  const reviewSDLC = useCallback(async (approved: boolean) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.reviewSDLC(state.sessionId, { approved });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review SDLC.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  const modifySDLC = useCallback(async (feedback: string) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.modifySDLC(state.sessionId, { user_feedback: feedback });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to modify SDLC.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Step 4: Story & Sub-tasks
  // ===================================================================

  const reviewStoryTasks = useCallback(async (approved: boolean) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.reviewStoryTasks(state.sessionId, { approved });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review story tasks.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  const modifyStoryTasks = useCallback(async (feedback: string) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.modifyStoryTasks(state.sessionId, { user_feedback: feedback });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to modify story tasks.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Step 5: Test Cases
  // ===================================================================

  const reviewTestCases = useCallback(async (approved: boolean) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.reviewTestCases(state.sessionId, { approved });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review test cases.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  const modifyTestCases = useCallback(async (feedback: string) => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.modifyTestCases(state.sessionId, { user_feedback: feedback });
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to modify test cases.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Step 6: Jira Creation
  // ===================================================================

  const createJira = useCallback(async () => {
    if (!state.sessionId) return setError('No active session.');
    setLoading(true);
    try {
      const response = await api.createJira(state.sessionId);
      setState((prev) => ({ ...prev, ...mapResponseToState(response), isLoading: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create Jira tickets.');
      setLoading(false);
    }
  }, [state.sessionId, setError, setLoading]);

  // ===================================================================
  // Reset / Start New
  // ===================================================================

  const startNewStory = useCallback(async () => {
    setState({ ...initialState });
    await createSession();
  }, [createSession]);

  // ===================================================================
  // Jira Details View
  // ===================================================================

  const viewJiraDetails = useCallback(() => {
    setState((prev) => ({ ...prev, showJiraDetails: true }));
  }, []);

  const closeJiraDetails = useCallback(() => {
    setState((prev) => ({ ...prev, showJiraDetails: false }));
  }, []);

  return {
    state,
    actions: {
      setError,
      setProblemStatement,
      setSkipSdlc,
      createSession,
      refreshSession,
      viewStep,
      returnToCurrentStep,
      // Step 1
      analyzeProblem,
      reviewSummary,
      modifySummary,
      // Step 2
      reviewStoryDescription,
      modifyStoryDescription,
      // Step 3
      reviewSDLC,
      modifySDLC,
      // Step 4
      reviewStoryTasks,
      modifyStoryTasks,
      // Step 5
      reviewTestCases,
      modifyTestCases,
      // Step 6
      createJira,
      viewJiraDetails,
      closeJiraDetails,
      // Reset
      startNewStory,
    },
  };
}
