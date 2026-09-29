import { apiClient } from "./client";
import { Project, AuthProfile } from "./types";

export const projectsApi = {
  list: async (): Promise<Project[]> => {
    const { data } = await apiClient.get("/projects");
    return data;
  },
  get: async (id: string): Promise<Project> => {
    const { data } = await apiClient.get(`/projects/${id}`);
    return data;
  },
  create: async (project: {
    name: string;
    base_url: string;
    description?: string | null;
    jira_key?: string | null;
  }): Promise<Project> => {
    const { data } = await apiClient.post("/projects", project);
    return data;
  },
  update: async (
    id: string,
    changes: Partial<
      Pick<Project, "name" | "base_url" | "description" | "jira_key">
    >,
  ): Promise<Project> => {
    const { data } = await apiClient.patch(`/projects/${id}`, changes);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/projects/${id}`);
  },
  uploadAuthProfile: async (
    projectId: string,
    profile: { name: string; storage_state_json: string },
  ): Promise<AuthProfile> => {
    const { data } = await apiClient.post(
      `/projects/${projectId}/auth-profile`,
      profile,
    );
    return data;
  },
  getAuthProfile: async (projectId: string): Promise<AuthProfile | null> => {
    const { data } = await apiClient.get(`/projects/${projectId}/auth-profile`);
    return data;
  },
  clearAuthProfile: async (projectId: string): Promise<void> => {
    await apiClient.delete(`/projects/${projectId}/auth-profile`);
  },
};
