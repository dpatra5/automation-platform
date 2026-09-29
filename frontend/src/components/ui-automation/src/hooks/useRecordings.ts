import { useMutation } from '@tanstack/react-query';
import { recordingsApi } from '../api/recordings';

export const useRequestSessionToken = () => {
  return useMutation({
    mutationFn: (projectId: string) => recordingsApi.requestSessionToken(projectId)
  });
};
