import { apiClient } from "./client";
import { TestCase, Step, TestRun } from "./types";

export const testCasesApi = {
  listByProject: async (projectId: string): Promise<TestCase[]> => {
    const { data } = await apiClient.get(`/projects/${projectId}/test-cases`);
    return data;
  },
  get: async (id: string): Promise<TestCase> => {
    const { data } = await apiClient.get(`/test-cases/${id}`);
    return data;
  },
  create: async (testCase: {
    project_id: string;
    name: string;
    description?: string;
    start_url?: string;
    steps?: Partial<Step>[];
  }): Promise<TestCase> => {
    const { data } = await apiClient.post(
      `/projects/${testCase.project_id}/test-cases`,
      testCase,
    );
    return data;
  },
  update: async (
    id: string,
    testCase: Partial<TestCase>,
  ): Promise<TestCase> => {
    const { data } = await apiClient.patch(`/test-cases/${id}`, testCase);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/test-cases/${id}`);
  },
  triggerRun: async (id: string, silentMode: boolean = false): Promise<TestRun> => {
    const { data } = await apiClient.post(`/test-cases/${id}/run`, { silent_mode: silentMode });
    return data;
  },
  updateSteps: async (
    id: string,
    steps: Partial<Step>[],
  ): Promise<TestCase> => {
    const { data } = await apiClient.put(`/test-cases/${id}/steps`, { steps });
    return data;
  },
  getScript: async (id: string): Promise<string> => {
    const { data } = await apiClient.get(`/test-cases/${id}/script`);
    return data.script as string;
  },
  updateScript: async (id: string, script: string): Promise<TestCase> => {
    const { data } = await apiClient.put(`/test-cases/${id}/script`, {
      script,
    });
    return data;
  },
};
