import { RunsTable } from '@/components/RunsTable';
import { Alert, Spinner } from '@/components/ui';
import { useRuns } from '@/hooks/queries';

export function RunsPage() {
  const { data: runs, error } = useRuns();
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl rounded-lg border border-slate-200 bg-white">
        <h1 className="border-b border-slate-200 px-4 py-3 text-lg font-semibold">Run history</h1>
        {error && (
          <div className="p-4">
            <Alert>{error.message}</Alert>
          </div>
        )}
        {runs ? <RunsTable runs={runs} /> : !error && <Spinner />}
      </div>
    </div>
  );
}
