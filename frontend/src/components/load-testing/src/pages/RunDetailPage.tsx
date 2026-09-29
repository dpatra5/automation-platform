import {
  Activity,
  AlertOctagon,
  ArrowLeft,
  Ban,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  Gauge,
  OctagonX,
  Square,
  Timer,
  Trash2,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { AnalysisPanel } from '@/components/AnalysisPanel';
import { PageHeader } from '@/components/layout/AppLayout';
import { LatencyChart, ThroughputChart } from '@/components/RunCharts';
import { StatusBadge, VerdictBadge } from '@/components/StatusBadge';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/Spinner';
import { Stat } from '@/components/ui/Stat';
import { Tabs } from '@/components/ui/Tabs';
import {
  isActive,
  useDeleteRun,
  useLogs,
  useRun,
  useStopRun,
  useTimeseries,
} from '@/hooks/queries';
import { ApiError, api } from '@/lib/api';
import { cn } from '@/lib/cn';
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatInt,
  formatMs,
  formatPct,
  formatRps,
} from '@/lib/format';
import { mergeTimeseries, routeTotals, type ChartPoint } from '@/lib/timeseries';
import type { RunDetail, Timeseries } from '@/lib/types';

type TabId = 'overview' | 'analysis' | 'routes' | 'logs' | 'artifacts' | 'config';

function ProgressBar({ run }: { run: RunDetail }) {
  const p = run.progress;
  if (!p) return null;
  const planned = p.planned_duration_s ?? 0;
  const pct = planned > 0 ? Math.min(100, (p.elapsed_s / planned) * 100) : 0;
  return (
    <Card className="mb-6">
      <CardBody>
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="font-medium">
            {run.status === 'stopping' ? 'Stopping — draining in-flight requests…' : 'Running'}
          </span>
          <span className="text-slate-500 tabular-nums dark:text-slate-400">
            {formatDuration(p.elapsed_s)} / {formatDuration(planned)}
          </span>
        </div>
        <div
          className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
          aria-label="Run progress"
        >
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-700',
              run.status === 'stopping' ? 'bg-amber-500' : 'bg-brand-600',
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function liveTotals(points: ChartPoint[]) {
  let attempted = 0;
  let accepted = 0;
  let limited = 0;
  let errors = 0;
  for (const p of points) {
    attempted += p.attempted ?? 0;
    accepted += p.accepted ?? 0;
    limited += p.rateLimited ?? 0;
    errors += p.errors ?? 0;
  }
  return { attempted, accepted, limited, errors };
}

function StatsGrid({ run, points }: { run: RunDetail; points: ChartPoint[] }) {
  const s = run.summary;
  if (s) {
    return (
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat
          label="Attempted"
          value={formatInt(s.totals.attempted)}
          sub={`${formatRps(s.means.attempted_rps)} rps`}
          icon={<Activity className="size-4" />}
        />
        <Stat
          label="Accepted"
          value={formatRps(s.means.accepted_rps)}
          sub={`${formatPct(s.ratios.accepted)} · ${formatInt(s.totals.accepted)} req`}
          icon={<CheckCircle2 className="size-4" />}
          tone="success"
        />
        <Stat
          label="Rate limited (429)"
          value={formatPct(s.ratios['429'])}
          sub={`${formatRps(s.means['429_rps'])} rps`}
          icon={<Ban className="size-4" />}
          tone={s.ratios['429'] > 0 ? 'warning' : 'default'}
        />
        <Stat
          label="Errors"
          value={formatInt(s.totals.errors)}
          sub={formatPct(s.ratios.errors, 2)}
          icon={<AlertOctagon className="size-4" />}
          tone={s.totals.errors > 0 ? 'danger' : 'default'}
        />
        <Stat
          label="Latency p50 / p99"
          value={formatMs(s.latency_ms.p99)}
          sub={`p50 ${formatMs(s.latency_ms.p50)} · max ${formatMs(s.latency_ms.max)}`}
          icon={<Timer className="size-4" />}
        />
        <Stat
          label="Scheduler accuracy"
          value={`${s.scheduler.rate_error_pct.toFixed(2)}%`}
          sub={`lag p99 ${formatMs(s.scheduler.lag_p99_ms)}`}
          icon={<Gauge className="size-4" />}
          tone={Math.abs(s.scheduler.rate_error_pct) > 2 ? 'warning' : 'default'}
        />
      </div>
    );
  }
  if (!isActive(run.status)) return null;
  const t = liveTotals(points);
  const ratio = (n: number) => (t.attempted ? n / t.attempted : null);
  return (
    <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
      <Stat
        label="Attempted (live)"
        value={formatInt(t.attempted)}
        icon={<Activity className="size-4" />}
      />
      <Stat
        label="Accepted"
        value={formatInt(t.accepted)}
        sub={formatPct(ratio(t.accepted))}
        tone="success"
        icon={<CheckCircle2 className="size-4" />}
      />
      <Stat
        label="Rate limited (429)"
        value={formatInt(t.limited)}
        sub={formatPct(ratio(t.limited))}
        tone={t.limited ? 'warning' : 'default'}
        icon={<Ban className="size-4" />}
      />
      <Stat
        label="Errors"
        value={formatInt(t.errors)}
        sub={formatPct(ratio(t.errors), 2)}
        tone={t.errors ? 'danger' : 'default'}
        icon={<AlertOctagon className="size-4" />}
      />
    </div>
  );
}

function OverviewTab({ run, points }: { run: RunDetail; points: ChartPoint[] }) {
  const families = run.metrics?.latency_by_family_ms ?? {};
  const statusCodes = run.summary?.status_codes ?? {};
  const errorTypes = run.metrics?.error_types ?? {};
  const totalCodes = Object.values(statusCodes).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Throughput" description="Requests per second, by outcome" />
          <CardBody>
            {points.length ? (
              <ThroughputChart data={points} />
            ) : (
              <EmptyState
                title="Waiting for data"
                description="Per-second samples appear once the run starts sending."
              />
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader
            title="Latency"
            description="Measured from scheduled send time (coordinated-omission safe)"
          />
          <CardBody>
            {points.some((p) => p.p99 !== null) ? (
              <LatencyChart data={points} />
            ) : (
              <EmptyState
                title="Latency not finalized yet"
                description="Per-second percentiles are published once each window's in-flight requests settle."
              />
            )}
          </CardBody>
        </Card>
      </div>
      {run.summary && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader title="Status codes" />
            <CardBody className="space-y-2.5">
              {Object.entries(statusCodes).map(([code, count]) => {
                const pct = totalCodes ? count / totalCodes : 0;
                const tone = code.startsWith('2')
                  ? 'bg-emerald-500'
                  : code === '429'
                    ? 'bg-amber-500'
                    : 'bg-rose-500';
                return (
                  <div key={code}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="font-mono">{code}</span>
                      <span className="text-slate-500 tabular-nums dark:text-slate-400">
                        {formatInt(count)} · {formatPct(pct)}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className={cn('h-full rounded-full', tone)}
                        style={{ width: `${pct * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              {Object.keys(errorTypes).length > 0 && (
                <div className="pt-2">
                  <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
                    Client errors
                  </p>
                  <ul className="space-y-1 text-sm">
                    {Object.entries(errorTypes).map(([k, v]) => (
                      <li key={k} className="flex justify-between">
                        <span className="font-mono text-xs">{k}</span>
                        <span className="tabular-nums">{formatInt(v)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Latency by status family" />
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm tabular-nums">
                <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
                  <tr>
                    {['Family', 'Count', 'p50', 'p90', 'p99', 'Max'].map((h, i) => (
                      <th key={h} className={cn('px-5 py-2 font-medium', i > 0 && 'text-right')}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {Object.entries(families).map(([family, l]) => (
                    <tr key={family}>
                      <td className="px-5 py-2 font-mono">{family}</td>
                      <td className="px-5 py-2 text-right">{formatInt(l.count)}</td>
                      <td className="px-5 py-2 text-right">{formatMs(l.p50)}</td>
                      <td className="px-5 py-2 text-right">{formatMs(l.p90)}</td>
                      <td className="px-5 py-2 text-right">{formatMs(l.p99)}</td>
                      <td className="px-5 py-2 text-right">{formatMs(l.max)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function RoutesTab({ ts }: { ts: Timeseries | undefined }) {
  const rows = routeTotals(ts);
  if (!rows.length) {
    return (
      <Card>
        <EmptyState
          title="No per-route data yet"
          description="routes.csv is written when the run finishes."
        />
      </Card>
    );
  }
  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm tabular-nums">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
            <tr>
              {['Route', 'Attempted', 'Accepted', '429', 'Errors', 'Acceptance'].map((h, i) => (
                <th key={h} className={cn('px-5 py-2.5 font-medium', i > 0 && 'text-right')}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => (
              <tr key={r.route}>
                <td className="px-5 py-2.5 font-medium">{r.route}</td>
                <td className="px-5 py-2.5 text-right">{formatInt(r.attempted)}</td>
                <td className="px-5 py-2.5 text-right">{formatInt(r.accepted)}</td>
                <td className="px-5 py-2.5 text-right">{formatInt(r.rateLimited)}</td>
                <td className="px-5 py-2.5 text-right">{formatInt(r.errors)}</td>
                <td className="px-5 py-2.5 text-right">
                  {formatPct(r.attempted ? r.accepted / r.attempted : null)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

const levelTone: Record<string, string> = {
  ERROR: 'text-rose-400',
  CRITICAL: 'text-rose-400',
  WARNING: 'text-amber-400',
  INFO: 'text-sky-400',
  DEBUG: 'text-slate-500',
};

function LogsTab({ runId, active }: { runId: string; active: boolean }) {
  const logs = useLogs(runId, active, true);
  if (logs.error) return <ErrorAlert error={logs.error} title="Could not load logs" />;
  return (
    <Card className="overflow-hidden">
      <div className="max-h-[560px] overflow-auto bg-slate-950 p-4 font-mono text-xs leading-5 text-slate-300">
        {logs.isPending ? (
          <p className="text-slate-500">Loading…</p>
        ) : logs.data.length ? (
          logs.data.map((rec, i) => {
            const { ts, level, msg, logger: _logger, ...rest } = rec;
            const extra = Object.keys(rest).length ? JSON.stringify(rest) : '';
            return (
              <div key={i} className="break-all whitespace-pre-wrap">
                <span className="text-slate-500">{ts?.slice(11, 23)}</span>{' '}
                <span className={levelTone[level ?? ''] ?? 'text-slate-400'}>
                  {level?.padEnd(7)}
                </span>{' '}
                <span className="text-slate-100">{msg}</span>{' '}
                <span className="text-slate-500">{extra}</span>
              </div>
            );
          })
        ) : (
          <p className="text-slate-500">No log output.</p>
        )}
      </div>
    </Card>
  );
}

function ArtifactsTab({ run }: { run: RunDetail }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const download = async (name: string) => {
    setError(null);
    setBusy(name);
    try {
      await api.downloadArtifact(run.run_id, name);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-4">
      <ErrorAlert error={error} title="Download failed" />
      <Card>
        {run.artifacts.length === 0 ? (
          <EmptyState icon={<FileText className="size-5" />} title="No artifacts yet" />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {run.artifacts.map((a) => (
              <li key={a.name} className="flex items-center justify-between gap-4 px-5 py-3">
                <div className="flex items-center gap-3">
                  <FileText className="size-4 text-slate-400" />
                  <span className="font-mono text-sm">{a.name}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {formatBytes(a.size)}
                  </span>
                </div>
                <Button
                  size="sm"
                  icon={<Download className="size-3.5" />}
                  loading={busy === a.name}
                  onClick={() => void download(a.name)}
                >
                  Download
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ConfigTab({ run }: { run: RunDetail }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Effective config"
        description="Sensitive headers are redacted by the engine."
      />
      <pre className="max-h-[560px] overflow-auto bg-slate-950 p-4 font-mono text-xs leading-5 text-slate-200">
        {run.config ? JSON.stringify(run.config, null, 2) : 'Config not written yet.'}
      </pre>
    </Card>
  );
}

export function RunDetailPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const run = useRun(runId);
  const active = isActive(run.data?.status);
  const ts = useTimeseries(runId, active);
  const stop = useStopRun(runId);
  const del = useDeleteRun();
  const [tab, setTab] = useState<TabId>('overview');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const points = useMemo(() => mergeTimeseries(ts.data), [ts.data]);

  if (run.isPending) return <PageLoader />;
  if (run.error) {
    const notFound = run.error instanceof ApiError && run.error.status === 404;
    return (
      <EmptyState
        icon={<OctagonX className="size-5" />}
        title={notFound ? 'Run not found' : 'Could not load run'}
        description={notFound ? `No run with id “${runId}”.` : run.error.message}
        action={
          <ButtonLink to="/runs" icon={<ArrowLeft className="size-4" />}>
            Back to runs
          </ButtonLink>
        }
      />
    );
  }

  const r = run.data;
  const title = r.summary?.name ?? (r.config?.name as string | undefined) ?? 'Untitled run';
  const baseUrl = r.summary?.base_url ?? (r.config?.base_url as string | undefined);

  return (
    <>
      <Link
        to="/runs"
        className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        <ArrowLeft className="size-3.5" /> All runs
      </Link>
      <PageHeader
        title={title}
        meta={
          <>
            <StatusBadge status={r.status} />
            {r.analysis && (
              <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                Analysis <VerdictBadge pass={r.analysis.pass} />
              </span>
            )}
            <Badge className="font-mono">{r.run_id}</Badge>
            {baseUrl && (
              <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                {baseUrl}
              </span>
            )}
            {r.summary?.started_at && (
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                <Clock className="size-3" /> {formatDateTime(r.summary.started_at)} ·{' '}
                {formatDuration(r.summary.duration_s)}
              </span>
            )}
          </>
        }
        actions={
          active ? (
            r.status === 'running' ? (
              <Button
                variant="secondary"
                icon={<Square className="size-4" />}
                loading={stop.isPending}
                onClick={() => stop.mutate(false)}
              >
                Stop gracefully
              </Button>
            ) : (
              <Button
                variant="danger"
                icon={<OctagonX className="size-4" />}
                loading={stop.isPending}
                onClick={() => stop.mutate(true)}
              >
                Force stop
              </Button>
            )
          ) : (
            <Button
              variant="ghost"
              icon={<Trash2 className="size-4" />}
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </Button>
          )
        }
      />

      <div className="space-y-4">
        <ErrorAlert error={stop.error} title="Could not stop run" />
        <ErrorAlert error={del.error} title="Could not delete run" />
        {r.status === 'failed' && r.error && (
          <Alert tone="danger" title="Run failed">
            <code className="text-xs">{r.error}</code>
          </Alert>
        )}
        {r.status === 'interrupted' && (
          <Alert tone="warning" title="Run was interrupted">
            Results cover only the portion of the profile that executed.
          </Alert>
        )}
      </div>
      <div className="mt-4">
        <ProgressBar run={r} />
        <StatsGrid run={r} points={points} />
      </div>

      <div className="mb-6">
        <Tabs<TabId>
          label="Run sections"
          value={tab}
          onChange={setTab}
          items={[
            { id: 'overview', label: 'Overview' },
            { id: 'analysis', label: 'Analysis' },
            { id: 'routes', label: 'Routes' },
            { id: 'logs', label: 'Logs' },
            { id: 'artifacts', label: 'Artifacts', count: r.artifacts.length },
            { id: 'config', label: 'Config' },
          ]}
        />
      </div>

      <div role="tabpanel" className="animate-fade-in">
        {tab === 'overview' && <OverviewTab run={r} points={points} />}
        {tab === 'analysis' &&
          (r.summary && !active ? (
            <AnalysisPanel runId={r.run_id} analysis={r.analysis} />
          ) : (
            <Card>
              <EmptyState
                title="Analysis unavailable"
                description={
                  active
                    ? 'Analysis becomes available once the run finishes.'
                    : 'This run has no summary to analyze.'
                }
              />
            </Card>
          ))}
        {tab === 'routes' && <RoutesTab ts={ts.data} />}
        {tab === 'logs' && <LogsTab runId={r.run_id} active={active} />}
        {tab === 'artifacts' && <ArtifactsTab run={r} />}
        {tab === 'config' && <ConfigTab run={r} />}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        danger
        title="Delete this run?"
        description="All artifacts for this run will be permanently removed from the server."
        confirmLabel="Delete run"
        loading={del.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() =>
          del.mutate(r.run_id, {
            onSuccess: () => void navigate('/runs', { replace: true }),
            onSettled: () => setConfirmDelete(false),
          })
        }
      />
    </>
  );
}
