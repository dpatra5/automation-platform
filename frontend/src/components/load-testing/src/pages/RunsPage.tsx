import { PlayCircle, RefreshCw, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/layout/AppLayout';
import { RunsTable } from '@/components/RunsTable';
import { ErrorAlert } from '@/components/ui/Alert';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input, Select } from '@/components/ui/Field';
import { useRuns } from '@/hooks/queries';
import type { RunStatus } from '@/lib/types';

type Filter = RunStatus | 'all';

export function RunsPage() {
  const runs = useRuns();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<Filter>('all');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (runs.data ?? []).filter(
      (r) =>
        (status === 'all' || r.status === status) &&
        (!q ||
          r.run_id.toLowerCase().includes(q) ||
          (r.name ?? '').toLowerCase().includes(q) ||
          (r.base_url ?? '').toLowerCase().includes(q)),
    );
  }, [runs.data, query, status]);

  return (
    <>
      <PageHeader
        title="Runs"
        description="Every run's artifacts live under the API's runs directory."
        actions={
          <>
            <Button
              onClick={() => void runs.refetch()}
              loading={runs.isFetching && !runs.isPending}
              icon={<RefreshCw className="size-4" />}
            >
              Refresh
            </Button>
            <ButtonLink to="/runs/new" variant="primary" icon={<PlayCircle className="size-4" />}>
              New run
            </ButtonLink>
          </>
        }
      />
      <ErrorAlert error={runs.error} title="Could not load runs" />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
            <Input
              type="search"
              aria-label="Search runs"
              placeholder="Search by name, run id, or target"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => setStatus(e.target.value as Filter)}
            className="w-40"
          >
            <option value="all">All statuses</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="interrupted">Interrupted</option>
            <option value="failed">Failed</option>
          </Select>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {filtered.length} of {runs.data?.length ?? 0}
          </span>
        </div>
        <RunsTable runs={filtered} loading={runs.isPending} />
      </Card>
    </>
  );
}
