import { apiClient } from "./client";
import { TestRun } from "./types";

export const runsApi = {
  list: async (filters?: {
    test_case_id?: string;
    project_id?: string;
    status?: string;
  }): Promise<TestRun[]> => {
    const { data } = await apiClient.get("/runs", { params: filters });
    return data;
  },
  get: async (id: string): Promise<TestRun> => {
    const { data } = await apiClient.get(`/runs/${id}`);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/runs/${id}`);
  },
  // Sent as a body rather than a query string: a selection of a few hundred
  // runs would otherwise be cut off by a URL length limit.
  deleteMany: async (ids: string[]): Promise<number> => {
    const { data } = await apiClient.post("/runs/delete", { ids });
    return data.deleted as number;
  },
};
