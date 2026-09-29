import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { Project } from "../api/types";

export const useProjects = () => {
  return useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });
};

export const useProject = (id: string) => {
  return useQuery({
    queryKey: ["projects", id],
    queryFn: () => projectsApi.get(id),
    enabled: !!id,
  });
};

export const useCreateProject = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (project: {
      name: string;
      base_url: string;
      description?: string | null;
      jira_key?: string | null;
    }) => projectsApi.create(project),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
};

export const useUpdateProject = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      changes,
    }: {
      id: string;
      changes: Partial<
        Pick<Project, "name" | "base_url" | "description" | "jira_key">
      >;
    }) => projectsApi.update(id, changes),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects", project.id] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
};

export const useDeleteProject = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    // A project takes its test cases and runs with it, so every list that
    // could still be showing them has to be refetched.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["testCases"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });
};

export const useAuthProfile = (projectId: string) => {
  return useQuery({
    queryKey: ["authProfile", projectId],
    queryFn: () => projectsApi.getAuthProfile(projectId),
    enabled: !!projectId,
  });
};

export const useUploadAuthProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      profile,
    }: {
      projectId: string;
      profile: { name: string; storage_state_json: string };
    }) => projectsApi.uploadAuthProfile(projectId, profile),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["authProfile", variables.projectId],
      });
    },
  });
};

export const useClearAuthProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => projectsApi.clearAuthProfile(projectId),
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ["authProfile", projectId] });
    },
  });
};
