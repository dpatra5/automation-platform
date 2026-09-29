import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { runsApi } from "../api/runs";

export const useRuns = (filters?: {
  test_case_id?: string;
  project_id?: string;
  status?: string;
}) => {
  return useQuery({
    queryKey: ["runs", filters],
    queryFn: () => runsApi.list(filters),
    // Keep lists moving while a run is in flight.
    refetchInterval: (query) =>
      query.state?.data?.some(
        (r) => r.status === "running" || r.status === "pending",
      )
        ? 3000
        : false,
  });
};

export const useRun = (id: string) => {
  return useQuery({
    queryKey: ["runs", id],
    queryFn: () => runsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
  });
};

/** Delete one run or a selection of them; both refresh every run list. */
export const useDeleteRuns = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      ids.length === 1
        ? runsApi.delete(ids[0]).then(() => 1)
        : runsApi.deleteMany(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      // A deleted run changes the project's last-run status.
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
};
