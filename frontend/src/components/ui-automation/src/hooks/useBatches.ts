import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { batchesApi } from "../api/batches";

const isMoving = (status?: string) =>
  status === "running" || status === "pending";

export const useBatches = (projectId?: string) =>
  useQuery({
    queryKey: ["batches", projectId ?? "all"],
    queryFn: () => batchesApi.list(projectId),
    // A sequence can take minutes; keep the list honest while it walks.
    refetchInterval: (query) =>
      query.state?.data?.some((b) => isMoving(b.status)) ? 4000 : false,
  });

export const useBatch = (id: string) =>
  useQuery({
    queryKey: ["batches", "detail", id],
    queryFn: () => batchesApi.get(id),
    enabled: !!id,
    refetchInterval: (query) =>
      isMoving(query.state?.data?.status) ? 2000 : false,
  });

export const useCreateBatch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: batchesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
};
