import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { testCasesApi } from "../api/testCases";
import { TestCase, Step } from "../api/types";

export const useTestCases = (projectId: string) => {
  return useQuery({
    queryKey: ["testCases", "project", projectId],
    queryFn: () => testCasesApi.listByProject(projectId),
    enabled: !!projectId,
  });
};

export const useTestCase = (id: string) => {
  return useQuery({
    queryKey: ["testCases", id],
    queryFn: () => testCasesApi.get(id),
    enabled: !!id,
  });
};

export const useCreateTestCase = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: testCasesApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: ["testCases", "project", data.project_id],
      });
    },
  });
};

export const useUpdateTestCase = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TestCase> }) =>
      testCasesApi.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["testCases", data.id] });
      queryClient.invalidateQueries({
        queryKey: ["testCases", "project", data.project_id],
      });
    },
  });
};

export const useUpdateSteps = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, steps }: { id: string; steps: Partial<Step>[] }) =>
      testCasesApi.updateSteps(id, steps),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["testCases", variables.id] });
    },
  });
};

export const useTriggerRun = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, silentMode }: { id: string; silentMode: boolean }) =>
      testCasesApi.triggerRun(id, silentMode),
    // The new run must show up in the test case and history lists.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });
};

/** The steps written out as a script, refetched whenever they change. */
export const useScript = (id: string) => {
  return useQuery({
    queryKey: ["testCases", id, "script"],
    queryFn: () => testCasesApi.getScript(id),
    enabled: !!id,
  });
};

export const useUpdateScript = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, script }: { id: string; script: string }) =>
      testCasesApi.updateScript(id, script),
    // The steps and the script are two views of the same thing; a change to
    // either has to leave the other showing what was actually saved.
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["testCases", variables.id] });
    },
  });
};
