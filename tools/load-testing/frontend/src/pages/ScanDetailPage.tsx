import {
  ArrowLeft,
  ExternalLink,
  FileSearch,
  Gauge,
  Globe,
  ListChecks,
  OctagonX,
  Play,
  Radar,
  Trash2,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { PageHeader } from '@/components/layout/AppLayout';
import { PlanFields } from '@/components/scan/PlanFields';
import { ScanStatusBadge, VerdictBadge } from '@/components/StatusBadge';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader, Spinner } from '@/components/ui/Spinner';
import { Stat } from '@/components/ui/Stat';
import { isScanActive, useScan, useScanControl } from '@/hooks/queries';
import { ApiError } from '@/lib/api';
import { cn } from '@/lib/cn';
import { formatDateTime, formatMs, formatPct, formatRps } from '@/lib/format';
import { DEFAULT_PLAN, endpointFlags, isDefaultSelected } from '@/lib/scan';
import type { DiscoveredEndpoint, LoadPlan, ScanDetail } from '@/lib/types';

const methodTone = (m: string) =>
  m === 'GET' || m === 'HEAD' || m === 'OPTIONS' ? 'brand' : m === 'DELETE' ? 'danger' : 'warning';

function ResultsCard({ scan }: { scan: ScanDetail }) {
  const done = scan.items_done;
  const total = scan.items_total;
  const pct = total ? (done / total) * 100 : 0;
  return (
    <Card>
      <CardHeader
        title="Load test results"
        description={
          scan.plan &&
          `${scan.plan.mode === 'per-endpoint' ? 'One run per API' : 'One run per host'} · ${formatRps(scan.plan.rate)} rps for ${scan.plan.duration}`
        }
        actions={
          <span className="text-xs text-slate-500 tabular-nums">
            {done} / {total}
          </span>
        }
      />
      {scan.status === 'running' && (
        <div className="h-1 bg-slate-100 dark:bg-slate-800">
          <div
            className="h-full bg-brand-600 transition-[width] duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm tabular-nums">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-5 py-2.5 font-medium">Test</th>
              <th className="px-5 py-2.5 font-medium">Status</th>
              <th className="px-5 py-2.5 text-right font-medium">Accepted RPS</th>
              <th className="px-5 py-2.5 text-right font-medium">429</th>
              <th className="px-5 py-2.5 text-right font-medium">p99</th>
              <th className="px-5 py-2.5 font-medium">Verdict</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {scan.items.map((item, i) => (
              <tr key={`${item.name}-${i}`} className="align-top">
                <td className="px-5 py-2.5">
                  <div className="font-medium">{item.name}</div>
                  {item.error && (
                    <div className="mt-0.5 max-w-xl text-xs whitespace-pre-wrap text-rose-600 dark:text-rose-400">
                      {item.error}
                    </div>
                  )}
                </td>
                <td className="px-5 py-2.5">
                  <ScanStatusBadge status={item.status} />
                </td>
                <td className="px-5 py-2.5 text-right">{formatRps(item.accepted_rps)}</td>
                <td className="px-5 py-2.5 text-right">{formatPct(item.ratio_429)}</td>
                <td className="px-5 py-2.5 text-right">{formatMs(item.p99_ms)}</td>
                <td className="px-5 py-2.5">
                  <VerdictBadge pass={item.analysis_pass} na="—" />
                </td>
                <td className="py-2.5 pr-4">
                  {item.run_id && (
                    <Link
                      to={`/runs/${encodeURIComponent(item.run_id)}`}
                      aria-label={`Open run ${item.run_id}`}
                      className="text-slate-400 hover:text-brand-600"
                    >
                      <ExternalLink className="size-4" />
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

interface EndpointsCardProps {
  scan: ScanDetail;
  selected: Set<string>;
  onToggle: (id: string) => void;
  onSetAll: (ids: string[]) => void;
  disabled: boolean;
}

function EndpointsCard({ scan, selected, onToggle, onSetAll, disabled }: EndpointsCardProps) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? scan.endpoints : scan.endpoints.filter((e) => e.in_scope);
  const hidden = scan.endpoints.length - visible.length;
  const allVisibleSelected = visible.length > 0 && visible.every((e) => selected.has(e.id));

  return (
    <Card>
      <CardHeader
        title="Discovered APIs"
        description="Selected endpoints are replayed exactly as the browser called them (method, path, query, body)."
        actions={
          hidden > 0 || showAll ? (
            <Button size="sm" variant="ghost" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Hide out-of-scope' : `Show ${hidden} out-of-scope`}
            </Button>
          ) : undefined
        }
      />
      {visible.length === 0 ? (
        <EmptyState
          icon={<FileSearch className="size-5" />}
          title="No API calls observed"
          description="Try a higher link depth or settle time, add the API host to scope, or pass auth headers if the app requires login."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
              <tr>
                <th className="w-10 px-4 py-2.5">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    disabled={disabled}
                    checked={allVisibleSelected}
                    onChange={() =>
                      onSetAll(
                        allVisibleSelected
                          ? [...selected].filter((id) => !visible.some((e) => e.id === id))
                          : [...new Set([...selected, ...visible.map((e) => e.id)])],
                      )
                    }
                    className="size-4 rounded accent-brand-600"
                  />
                </th>
                <th className="px-2 py-2.5 font-medium">Endpoint</th>
                <th className="px-4 py-2.5 font-medium">Host</th>
                <th className="px-4 py-2.5 text-right font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">Calls</th>
                <th className="px-4 py-2.5 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {visible.map((ep: DiscoveredEndpoint) => (
                <tr
                  key={ep.id}
                  className={cn(!selected.has(ep.id) && 'text-slate-500 dark:text-slate-400')}
                >
                  <td className="px-4 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ${ep.method} ${ep.template}`}
                      disabled={disabled}
                      checked={selected.has(ep.id)}
                      onChange={() => onToggle(ep.id)}
                      className="size-4 rounded accent-brand-600"
                    />
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2">
                      <Badge tone={methodTone(ep.method)} className="font-mono">
                        {ep.method}
                      </Badge>
                      <span className="font-mono text-xs" title={ep.path}>
                        {ep.template}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs whitespace-nowrap">
                    {new URL(ep.base_url).host}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{ep.status ?? '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{ep.count}</td>
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-1">
                      {endpointFlags(ep).map((f) => (
                        <Badge key={f} tone={f === 'out of scope' ? 'neutral' : 'warning'}>
                          {f}
                        </Badge>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function CrawlDetails({ scan }: { scan: ScanDetail }) {
  const hosts = Object.entries(scan.out_of_scope_hosts);
  return (
    <Card>
      <CardHeader title="Crawl details" />
      <CardBody className="space-y-4 text-sm">
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
            Pages visited ({scan.pages.length})
          </p>
          <ul className="space-y-0.5 font-mono text-xs">
            {scan.pages.map((p) => (
              <li key={p} className="truncate" title={p}>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          In scope: {scan.options.scope.join(', ')}
          {scan.options.header_names.length > 0 &&
            ` · headers: ${scan.options.header_names.join(', ')}`}
        </p>
        {hosts.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
              Ignored hosts (third-party / out of scope)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {hosts.map(([h, n]) => (
                <Badge key={h}>
                  {h} ×{n}
                </Badge>
              ))}
            </div>
          </div>
        )}
        {scan.discovery_errors.length > 0 && (
          <Alert tone="warning" title="Some pages could not be loaded">
            {scan.discovery_errors.join('\n')}
          </Alert>
        )}
      </CardBody>
    </Card>
  );
}

function ScanBody({ scan }: { scan: ScanDetail }) {
  const navigate = useNavigate();
  const { run, cancel, remove } = useScanControl(scan.id);
  const active = isScanActive(scan.status);
  const [plan, setPlan] = useState<LoadPlan>(scan.plan ?? DEFAULT_PLAN);
  const [selection, setSelection] = useState<Set<string> | null>(null);
  const [confirm, setConfirm] = useState<'run' | 'delete' | null>(null);

  const defaults = useMemo(() => {
    const planned = new Set(scan.items.flatMap((i) => i.endpoint_ids));
    return planned.size
      ? planned
      : new Set(scan.endpoints.filter((e) => isDefaultSelected(e)).map((e) => e.id));
  }, [scan.items, scan.endpoints]);
  const selected = selection ?? defaults;
  const unsafeSelected = scan.endpoints.filter((e) => selected.has(e.id) && !e.safe).length;
  const runsCount =
    plan.mode === 'per-endpoint'
      ? selected.size
      : new Set(scan.endpoints.filter((e) => selected.has(e.id)).map((e) => e.base_url)).size;

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelection(next);
  };

  const inScope = scan.endpoints.filter((e) => e.in_scope).length;
  const passed = scan.items.filter((i) => i.analysis_pass === true).length;
  const judged = scan.items.filter((i) => i.analysis_pass !== null).length;

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Globe className="size-5 text-slate-400" /> {scan.url}
          </span>
        }
        meta={
          <>
            <ScanStatusBadge status={scan.status} />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {formatDateTime(scan.created_at)}
            </span>
          </>
        }
        actions={
          active ? (
            <Button
              variant="danger"
              icon={<OctagonX className="size-4" />}
              loading={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Cancel scan
            </Button>
          ) : (
            <Button
              variant="ghost"
              icon={<Trash2 className="size-4" />}
              onClick={() => setConfirm('delete')}
            >
              Delete
            </Button>
          )
        }
      />

      <div className="space-y-6">
        <ErrorAlert error={cancel.error} title="Could not cancel" />
        <ErrorAlert error={remove.error} title="Could not delete" />
        {scan.status === 'failed' && scan.error && (
          <Alert tone="danger" title="Scan failed">
            {scan.error}
          </Alert>
        )}

        {scan.status === 'discovering' ? (
          <Card>
            <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
              <Spinner className="size-6 text-brand-600" />
              <p className="text-sm font-medium">Crawling with headless Chromium…</p>
              <p className="max-w-md text-xs text-slate-500 dark:text-slate-400">
                Visiting up to {scan.options.max_pages} page(s) and recording XHR/fetch calls. Load
                tests start automatically when discovery finishes.
              </p>
            </div>
          </Card>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat
                label="Pages crawled"
                value={scan.pages.length}
                icon={<FileSearch className="size-4" />}
              />
              <Stat
                label="APIs discovered"
                value={scan.endpoints.length}
                sub={`${inScope} in scope`}
                icon={<Radar className="size-4" />}
              />
              <Stat
                label="Load tests"
                value={`${scan.items_done} / ${scan.items_total}`}
                icon={<ListChecks className="size-4" />}
              />
              <Stat
                label="Analysis passed"
                value={judged ? `${passed} / ${judged}` : '—'}
                tone={judged && passed < judged ? 'warning' : 'default'}
                icon={<Gauge className="size-4" />}
              />
            </div>

            {scan.items.length > 0 && <ResultsCard scan={scan} />}

            <Card>
              <CardHeader
                title={scan.items.length ? 'Run again' : 'Configure load tests'}
                description="Choose endpoints below, then set the load applied to each."
              />
              <CardBody className="space-y-4">
                <PlanFields value={plan} onChange={setPlan} disabled={active} />
                <ErrorAlert error={run.error} title="Could not start load tests" />
                <Button
                  variant="primary"
                  icon={<Play className="size-4" />}
                  disabled={active || selected.size === 0}
                  loading={run.isPending}
                  onClick={() => setConfirm('run')}
                >
                  Run {runsCount} load test{runsCount === 1 ? '' : 's'}
                </Button>
              </CardBody>
            </Card>

            <EndpointsCard
              scan={scan}
              selected={selected}
              onToggle={toggle}
              onSetAll={(ids) => setSelection(new Set(ids))}
              disabled={active}
            />
            <CrawlDetails scan={scan} />
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirm === 'run'}
        title="Start load tests?"
        confirmLabel={`Run ${runsCount} test${runsCount === 1 ? '' : 's'}`}
        loading={run.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() =>
          run.mutate({ endpointIds: [...selected], plan }, { onSettled: () => setConfirm(null) })
        }
        description={
          <div className="space-y-2">
            <p>
              {runsCount} run(s) at <strong>{formatRps(plan.rate)} rps</strong> for{' '}
              <strong>{plan.duration}</strong> each, executed one after another. Only test systems
              you are authorized to load.
            </p>
            {unsafeSelected > 0 && (
              <p className="text-rose-600 dark:text-rose-400">
                {unsafeSelected} selected endpoint(s) modify data and will be replayed repeatedly.
              </p>
            )}
          </div>
        }
      />
      <ConfirmDialog
        open={confirm === 'delete'}
        danger
        title="Delete this scan?"
        description="The scan record is removed. Runs it created stay under Runs."
        confirmLabel="Delete scan"
        loading={remove.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => void navigate('/scans', { replace: true }),
            onSettled: () => setConfirm(null),
          })
        }
      />
    </>
  );
}

export function ScanDetailPage() {
  const { scanId = '' } = useParams();
  const scan = useScan(scanId);
  if (scan.isPending) return <PageLoader />;
  if (scan.error) {
    const notFound = scan.error instanceof ApiError && scan.error.status === 404;
    return (
      <EmptyState
        icon={<OctagonX className="size-5" />}
        title={notFound ? 'Scan not found' : 'Could not load scan'}
        description={scan.error.message}
        action={
          <ButtonLink to="/scans" icon={<ArrowLeft className="size-4" />}>
            Back to scans
          </ButtonLink>
        }
      />
    );
  }
  return (
    <>
      <Link
        to="/scans"
        className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        <ArrowLeft className="size-3.5" /> All scans
      </Link>
      <ScanBody key={scan.data.id} scan={scan.data} />
    </>
  );
}
