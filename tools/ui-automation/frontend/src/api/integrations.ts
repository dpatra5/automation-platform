import { apiClient } from "./client";
import { AssertionOption, JiraIssueRef, JiraStatus, JiraWhoami } from "./types";

export const integrationsApi = {
  /** Every check the runner understands, so the pickers cannot drift from it. */
  assertions: async (): Promise<{
    assertions: AssertionOption[];
    default: string;
  }> => {
    const { data } = await apiClient.get("/integrations/assertions");
    return data;
  },
  jiraStatus: async (): Promise<JiraStatus> => {
    const { data } = await apiClient.get("/integrations/jira/status");
    return data;
  },
  /** Proves the token reaches Jira, and says which auth scheme worked. */
  jiraWhoami: async (): Promise<JiraWhoami> => {
    const { data } = await apiClient.get("/integrations/jira/whoami");
    return data;
  },
  validateJiraKey: async (
    key: string,
  ): Promise<{ valid: boolean; issue: JiraIssueRef }> => {
    const { data } = await apiClient.get("/integrations/jira/validate", {
      params: { key },
    });
    return data;
  },
};
