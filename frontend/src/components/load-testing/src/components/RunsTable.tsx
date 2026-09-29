import { ChevronRight, Inbox } from 'lucide-react';
import { Link, useNavigate } from 'react-router';

import { StatusBadge, VerdictBadge } from '@/components/StatusBadge';
import { ButtonLink } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Spinner';
import { cn } from '@/lib/cn';
import {
  formatDuration,
  formatInt,
  formatMs,
  formatPct,
  formatRelative,
  formatRps,
} from '@/lib/format';
import type { RunListItem } from '@/lib/types';

interface RunsTableProps {
  runs: RunListItem[];
  loading?: boolean;
  compact?: boolean;
}

const th = 'px-4 py-2.5 text-left text-xs font-medium text-slate-500 dark:text-slate-400';
const td = 'px-4 py-3 whitespace-nowrap';

export function RunsTable({ runs, loading, compact }: RunsTableProps) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <EmptyState
        icon={<Inbox className="size-5" />}
        title="No runs yet"
        description="Start a load profile to see throughput, latency, and limiter analysis here."
        action={
          <ButtonLink to="/runs/new" variant="primary">
            Create a run
          </ButtonLink>
        }
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
        <thead className="bg-slate-50/60 dark:bg-slate-900/40">
          <tr>
            <th scope="col" className={th}>
              Run
            </th>
            <th scope="col" className={th}>
              Status
            </th>
            {!compact && (
              <th scope="col" className={th}>
                Duration
              </th>
            )}
            <th scope="col" className={cn(th, 'text-right')}>
              Accepted RPS
            </th>
            {!compact && (
              <th scope="col" className={cn(th, 'text-right')}>
                Attempted
              </th>
            )}
            <th scope="col" className={cn(th, 'text-right')}>
              429
            </th>
            <th scope="col" className={cn(th, 'text-right')}>
              p99
            </th>
            <th scope="col" className={th}>
              Verdict
            </th>
            <th scope="col" className="w-8">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 tabular-nums dark:divide-slate-800">
          {runs.map((r) => {
            const href = `/runs/${encodeURIComponent(r.run_id)}`;
            return (
              <tr
                key={r.run_id}
                onClick={() => void navigate(href)}
                className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
              >
                <td className={td}>
                  <Link
                    to={href}
                    onClick={(e) => e.stopPropagation()}
                    className="font-medium text-slate-900 hover:text-brand-600 dark:text-slate-100"
                  >
                    {r.name ?? 'untitled'}
                  </Link>
                  <div className="font-mono text-xs text-slate-500 dark:text-slate-400">
                    {r.run_id}
                    {r.started_at && (
                      <span className="ml-2 font-sans">· {formatRelative(r.started_at)}</span>
                    )}
                  </div>
                </td>
                <td className={td}>
                  <StatusBadge status={r.status} />
                </td>
                {!compact && <td className={td}>{formatDuration(r.duration_s)}</td>}
                <td className={cn(td, 'text-right')}>{formatRps(r.means?.accepted_rps)}</td>
                {!compact && (
                  <td className={cn(td, 'text-right')}>{formatInt(r.totals?.attempted)}</td>
                )}
                <td className={cn(td, 'text-right')}>{formatPct(r.ratios?.['429'])}</td>
                <td className={cn(td, 'text-right')}>{formatMs(r.latency_ms?.p99)}</td>
                <td className={td}>
                  <VerdictBadge pass={r.analysis_pass} na="—" />
                </td>
                <td className="pr-3 text-slate-400">
                  <ChevronRight className="size-4" aria-hidden />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
