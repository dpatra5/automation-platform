import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import type {
  AnalyzeRequest,
  ConfigRequest,
  DemoServerRequest,
  LoadPlan,
  RunDetail,
  RunStatus,
  ScanDetail,
  ScanRequest,
  ScanStatus,
} from '@/lib/types';

export const ACTIVE_STATUSES: readonly RunStatus[] = ['running', 'stopping'];
export const isActive = (status: RunStatus | undefined): boolean =>
  status !== undefined && ACTIVE_STATUSES.includes(status);

export const queryKeys = {
  health: ['health'] as const,
  examples: ['examples'] as const,
  runs: ['runs'] as const,
  run: (id: string) => ['runs', id] as const,
  timeseries: (id: string) => ['runs', id, 'timeseries'] as const,
  logs: (id: string) => ['runs', id, 'logs'] as const,
  demo: ['demo-server'] as const,
  demoStats: ['demo-server', 'stats'] as const,
  scans: ['scans'] as const,
  scan: (id: string) => ['scans', id] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 15_000,
    retry: false,
  });
}

export function useExamples() {
  return useQuery({ queryKey: queryKeys.examples, queryFn: api.examples, staleTime: Infinity });
}

export function useRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
    refetchInterval: (q) => (q.state.data?.some((r) => isActive(r.status)) ? 2000 : 10_000),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: queryKeys.run(id),
    queryFn: () => api.getRun(id),
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 1000 : false),
  });
}

export function useTimeseries(id: string, active: boolean) {
  return useQuery({
    queryKey: queryKeys.timeseries(id),
    queryFn: () => api.timeseries(id),
    refetchInterval: active ? 1000 : false,
  });
}

export function useLogs(id: string, active: boolean, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.logs(id),
    queryFn: () => api.logs(id, 500),
    enabled,
    refetchInterval: active ? 2000 : false,
  });
}

export function useValidation(req: ConfigRequest) {
  return useQuery({
    queryKey: ['validate', req] as const,
    queryFn: ({ signal }) => api.validate(req, signal),
    enabled: req.yaml.trim() !== '',
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ConfigRequest) => api.startRun(req),
    onSuccess: (run: RunDetail) => {
      qc.setQueryData(queryKeys.run(run.run_id), run);
      void qc.invalidateQueries({ queryKey: queryKeys.runs, exact: true });
    },
  });
}

export function useStopRun(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => api.stopRun(id, force),
    onSuccess: (run) => qc.setQueryData(queryKeys.run(id), run),
  });
}

export function useAnalyze(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: AnalyzeRequest) => api.analyze(id, req),
    onSuccess: (analysis) => {
      qc.setQueryData<RunDetail>(queryKeys.run(id), (old) => (old ? { ...old, analysis } : old));
      void qc.invalidateQueries({ queryKey: queryKeys.runs, exact: true });
    },
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteRun(id),
    onSuccess: (_, id) => {
      qc.removeQueries({ queryKey: queryKeys.run(id) });
      void qc.invalidateQueries({ queryKey: queryKeys.runs, exact: true });
    },
  });
}

export function useDemoState() {
  return useQuery({ queryKey: queryKeys.demo, queryFn: api.demoState, refetchInterval: 5000 });
}

export function useDemoStats(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.demoStats,
    queryFn: api.demoStats,
    enabled,
    refetchInterval: 1000,
  });
}

export function useDemoControl() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.demo });
  const start = useMutation({
    mutationFn: (req: DemoServerRequest) => api.demoStart(req),
    onSuccess: (state) => qc.setQueryData(queryKeys.demo, state),
  });
  const stop = useMutation({ mutationFn: api.demoStop, onSettled: invalidate });
  return { start, stop };
}

const ACTIVE_SCAN: readonly ScanStatus[] = ['discovering', 'running'];
export const isScanActive = (status: ScanStatus | undefined): boolean =>
  status !== undefined && ACTIVE_SCAN.includes(status);

export function useScans() {
  return useQuery({
    queryKey: queryKeys.scans,
    queryFn: api.listScans,
    refetchInterval: (q) => (q.state.data?.some((s) => isScanActive(s.status)) ? 2000 : 15_000),
  });
}

export function useScan(id: string) {
  return useQuery({
    queryKey: queryKeys.scan(id),
    queryFn: () => api.getScan(id),
    refetchInterval: (q) => (isScanActive(q.state.data?.status) ? 1500 : false),
  });
}

export function useStartScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ScanRequest) => api.startScan(req),
    onSuccess: (scan: ScanDetail) => {
      qc.setQueryData(queryKeys.scan(scan.id), scan);
      void qc.invalidateQueries({ queryKey: queryKeys.scans, exact: true });
    },
  });
}

export function useScanControl(id: string) {
  const qc = useQueryClient();
  const onSuccess = (scan: ScanDetail) => {
    qc.setQueryData(queryKeys.scan(id), scan);
    void qc.invalidateQueries({ queryKey: queryKeys.scans, exact: true });
  };
  const run = useMutation({
    mutationFn: ({ endpointIds, plan }: { endpointIds: string[]; plan: LoadPlan }) =>
      api.runScan(id, endpointIds, plan),
    onSuccess,
  });
  const cancel = useMutation({ mutationFn: () => api.cancelScan(id), onSuccess });
  const remove = useMutation({
    mutationFn: () => api.deleteScan(id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: queryKeys.scan(id) });
      void qc.invalidateQueries({ queryKey: queryKeys.scans, exact: true });
    },
  });
  return { run, cancel, remove };
}
