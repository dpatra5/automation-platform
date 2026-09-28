import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';

export const keys = {
  collections: ['collections'] as const,
  collection: (id: number) => ['collections', id] as const,
  environments: ['environments'] as const,
  runs: (collectionId?: number) => ['runs', collectionId ?? 'all'] as const,
  run: (id: number) => ['run', id] as const,
};

export const useCollections = () => useQuery({ queryKey: keys.collections, queryFn: api.listCollections });

export const useCollection = (id: number | null) =>
  useQuery({
    queryKey: keys.collection(id ?? 0),
    queryFn: () => api.getCollection(id as number),
    enabled: id !== null,
  });

export const useEnvironments = () => useQuery({ queryKey: keys.environments, queryFn: api.listEnvironments });

export const useRuns = (collectionId?: number) =>
  useQuery({ queryKey: keys.runs(collectionId), queryFn: () => api.listRuns(collectionId) });

export const useRun = (id: number) => useQuery({ queryKey: keys.run(id), queryFn: () => api.getRun(id) });
