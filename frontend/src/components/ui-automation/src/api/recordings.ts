import { apiClient } from './client';

export const recordingsApi = {
  requestSessionToken: async (projectId: string): Promise<{ token: string }> => {
    // We ignore projectId here since the endpoint doesn't need it,
    // but keep it in signature so useMutation still works as is.
    const { data } = await apiClient.get(`/recordings/session-token`);
    return data;
  }
};
