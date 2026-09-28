import { apiClient } from "./client";
import { RunBatch } from "./types";

export const batchesApi = {
  list: async (projectId?: string): Promise<RunBatch[]> => {
    const { data } = await apiClient.get("/run-batches", {
      params: projectId ? { project_id: projectId } : undefined,
    });
    return data;
  },
  get: async (id: string): Promise<RunBatch> => {
    const { data } = await apiClient.get(`/run-batches/${id}`);
    return data;
  },
  create: async (payload: {
    test_case_ids: string[];
    name?: string;
  }): Promise<RunBatch> => {
    const { data } = await apiClient.post("/run-batches", payload);
    return data;
  },
};
