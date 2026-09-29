import type {
  SessionResponse,
  ProblemStatementRequest,
  ReviewRequest,
  ModifyRequest,
  ProgressResponse,
  HealthResponse,
} from '../models/sprintGuard.types';

const API_BASE_URL = '/api';

class ApiError extends Error {
  statusCode?: number;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
  }
}

async function apiCall<T>(
  endpoint: string,
  method: 'GET' | 'POST' | 'DELETE' = 'GET',
  data?: unknown
): Promise<T> {
  const options: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
  };

  if (data) {
    options.body = JSON.stringify(data);
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(error.detail || 'Request failed', response.status);
  }

  return response.json();
}

export const api = {
  // ===================================================================
  // Health & Session Management
  // ===================================================================
  
  health: () => apiCall<HealthResponse>('/health'),
  
  createSession: () => apiCall<SessionResponse>('/session/create', 'POST'),
  
  getSession: (sessionId: string) => 
    apiCall<SessionResponse>(`/session/${sessionId}`),
  
  getProgress: (sessionId: string) =>
    apiCall<ProgressResponse>(`/session/${sessionId}/progress`),
  
  deleteSession: (sessionId: string) =>
    apiCall<{ message: string }>(`/session/${sessionId}`, 'DELETE'),

  // ===================================================================
  // Step 1: Problem Analysis
  // ===================================================================
  
  analyzeProblem: (sessionId: string, request: ProblemStatementRequest) =>
    apiCall<SessionResponse>(`/step1/analyze/${sessionId}`, 'POST', request),
  
  reviewSummary: (sessionId: string, request: ReviewRequest) =>
    apiCall<SessionResponse>(`/step1/review/${sessionId}`, 'POST', request),
  
  modifySummary: (sessionId: string, request: ModifyRequest) =>
    apiCall<SessionResponse>(`/step1/modify/${sessionId}`, 'POST', request),

  // ===================================================================
  // Step 2: Story Description
  // ===================================================================
  
  reviewStoryDescription: (sessionId: string, request: ReviewRequest) =>
    apiCall<SessionResponse>(`/step2/review/${sessionId}`, 'POST', request),
  
  modifyStoryDescription: (sessionId: string, request: ModifyRequest) =>
    apiCall<SessionResponse>(`/step2/modify/${sessionId}`, 'POST', request),

  // ===================================================================
  // Step 3: SDLC & Test Plan
  // ===================================================================
  
  reviewSDLC: (sessionId: string, request: ReviewRequest) =>
    apiCall<SessionResponse>(`/step3/review/${sessionId}`, 'POST', request),
  
  modifySDLC: (sessionId: string, request: ModifyRequest) =>
    apiCall<SessionResponse>(`/step3/modify/${sessionId}`, 'POST', request),

  // ===================================================================
  // Step 4: Story & Sub-tasks
  // ===================================================================
  
  reviewStoryTasks: (sessionId: string, request: ReviewRequest) =>
    apiCall<SessionResponse>(`/step4/review/${sessionId}`, 'POST', request),
  
  modifyStoryTasks: (sessionId: string, request: ModifyRequest) =>
    apiCall<SessionResponse>(`/step4/modify/${sessionId}`, 'POST', request),

  // ===================================================================
  // Step 5: Test Cases
  // ===================================================================
  
  reviewTestCases: (sessionId: string, request: ReviewRequest) =>
    apiCall<SessionResponse>(`/step5/review/${sessionId}`, 'POST', request),
  
  modifyTestCases: (sessionId: string, request: ModifyRequest) =>
    apiCall<SessionResponse>(`/step5/modify/${sessionId}`, 'POST', request),

  // ===================================================================
  // Step 6: Jira Creation
  // ===================================================================
  
  createJira: (sessionId: string) =>
    apiCall<SessionResponse>(`/step6/create/${sessionId}`, 'POST'),

  // ===================================================================
  // Legacy endpoint (backwards compatibility)
  // ===================================================================
  
  analyze: (request: ProblemStatementRequest) =>
    apiCall<SessionResponse>('/analyze', 'POST', request),
};

export { ApiError };
