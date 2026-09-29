import { useQuery } from "@tanstack/react-query";
import { integrationsApi } from "../api/integrations";
import { FALLBACK_ASSERTIONS } from "../utils/constants";

/**
 * The check catalogue, straight from the runner that evaluates it.
 *
 * Fetched rather than hard-coded so the editor can never offer a check the
 * backend has never heard of. A built-in shortlist keeps the editor usable if
 * the request fails.
 */
export const useAssertions = () => {
  const query = useQuery({
    queryKey: ["assertions"],
    queryFn: integrationsApi.assertions,
    staleTime: Infinity,
    retry: 1,
  });

  return {
    ...query,
    options: query.data?.assertions?.length
      ? query.data.assertions
      : FALLBACK_ASSERTIONS,
    defaultKey: query.data?.default ?? "text_contains",
  };
};

export const useJiraStatus = () =>
  useQuery({
    queryKey: ["jiraStatus"],
    queryFn: integrationsApi.jiraStatus,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
