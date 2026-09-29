import {
  ArrowRight,
  Radar,
  CheckCircle2,
  Gauge,
  ListChecks,
  PlayCircle,
  Server,
  Timer,
} from 'lucide-react';
import { Link } from 'react-router';

import { PageHeader } from '@/components/layout/AppLayout';
import { RunsTable } from '@/components/RunsTable';
import { ErrorAlert } from '@/components/ui/Alert';
import { ButtonLink } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Spinner';
import { Stat } from '@/components/ui/Stat';
import { isActive, useDemoState, useRuns } from '@/hooks/queries';
import { formatMs, formatPct, formatRps } from '@/lib/format';

export function DashboardPage() {
  const runs = useRuns();
  const demo = useDemoState();
  const items = runs.data ?? [];
  const active = items.find((r) => isActive(r.status));
  const analyzed = items.filter((r) => r.analysis_pass !== null);
  const passed = analyzed.filter((r) => r.analysis_pass).length;
  const latest = items.find((r) => r.status === 'completed' || r.status === 'interrupted');

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Open-model HTTP load generation and API rate-limit verification."
        actions={
          <>
            <ButtonLink to="/runs/new" icon={<PlayCircle className="size-4" />}>
              New run
            </ButtonLink>
            <ButtonLink to="/scans" variant="primary" icon={<Radar className="size-4" />}>
              Scan a URL
            </ButtonLink>
          </>
        }
      />

      <ErrorAlert error={runs.error} title="Could not load runs" />

      {active && (
        <Link
          to={`/runs/${encodeURIComponent(active.run_id)}`}
          className="mb-6 flex items-center justify-between gap-4 rounded-xl border border-brand-500/30 bg-brand-50 px-5 py-4 text-brand-700 transition-colors hover:bg-brand-100 dark:bg-brand-500/10 dark:text-brand-100 dark:hover:bg-brand-500/20"
        >
          <div className="flex items-center gap-3">
            <span className="relative flex size-2.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-500 opacity-60" />
              <span className="relative inline-flex size-2.5 rounded-full bg-brand-600" />
            </span>
            <div>
              <p className="text-sm font-semibold">
                Run in progress · {active.name ?? active.run_id}
              </p>
              <p className="text-xs opacity-80">{active.base_url}</p>
            </div>
          </div>
          <ArrowRight className="size-4" />
        </Link>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {runs.isPending ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <Stat
              label="Total runs"
              value={items.length}
              icon={<ListChecks className="size-4" />}
              sub={`${items.filter((r) => r.status === 'failed').length} failed`}
            />
            <Stat
              label="Analysis pass rate"
              value={analyzed.length ? formatPct(passed / analyzed.length, 0) : '—'}
              icon={<CheckCircle2 className="size-4" />}
              sub={`${passed} of ${analyzed.length} analyzed runs`}
              tone={analyzed.length && passed < analyzed.length ? 'warning' : 'default'}
            />
            <Stat
              label="Latest accepted RPS"
              value={formatRps(latest?.means?.accepted_rps)}
              icon={<Gauge className="size-4" />}
              sub={
                latest ? `${formatPct(latest.ratios?.['429'])} rate limited` : 'No completed runs'
              }
            />
            <Stat
              label="Latest p99 latency"
              value={formatMs(latest?.latency_ms?.p99)}
              icon={<Timer className="size-4" />}
              sub="From scheduled send time (CO-safe)"
            />
          </>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Recent runs"
            actions={
              <Link
                to="/runs"
                className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-100"
              >
                View all
              </Link>
            }
          />
          <RunsTable runs={items.slice(0, 6)} loading={runs.isPending} compact />
        </Card>

        <Card>
          <CardHeader title="Demo server" description="Local rate-limited target for experiments" />
          <div className="space-y-4 px-5 py-4 text-sm">
            {demo.data?.running ? (
              <>
                <p className="text-slate-600 dark:text-slate-300">
                  Running at{' '}
                  <code className="rounded bg-slate-100 px-1 py-0.5 text-xs dark:bg-slate-800">
                    {demo.data.base_url}
                  </code>
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {demo.data.settings?.algo} · {demo.data.settings?.rate}/
                  {demo.data.settings?.window} · {demo.data.settings?.scope}
                </p>
              </>
            ) : (
              <p className="text-slate-500 dark:text-slate-400">
                Not running. Start one to try the bundled examples without an external API.
              </p>
            )}
            <ButtonLink to="/demo-server" icon={<Server className="size-4" />}>
              Manage demo server
            </ButtonLink>
          </div>
        </Card>
      </div>
    </>
  );
}
