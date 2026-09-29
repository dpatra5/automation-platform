import { ChevronDown, ChevronRight, Download, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { ResponseViewer } from '@/components/ResponseViewer';
import { Alert, Button, MethodBadge, PassBadge, Spinner, Stat, StatusPill } from '@/components/ui';
import { useRun } from '@/hooks/queries';
import { api } from '@/lib/api';
import { formatDate, formatMs } from '@/lib/format';
import type { RunStep } from '@/lib/types';

function StepRow({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(!step.result.passed);
  const r = step.result;
  const failed = r.assertions.filter((a) => !a.passed).length;
  return (
    <div className="border-b border-slate-100">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-slate-50"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <PassBadge passed={r.passed} />
        <MethodBadge method={r.request.method} className="w-9" />
        <span className="min-w-0 flex-1 truncate font-medium">{step.request_name}</span>
        {r.assertions.length > 0 && (
          <span className={failed ? 'text-rose-600' : 'text-slate-500'}>
            {r.assertions.length - failed}/{r.assertions.length} checks
          </span>
        )}
        <StatusPill status={r.response?.status} />
        <span className="w-16 text-right text-slate-500">{formatMs(r.response?.elapsed_ms)}</span>
      </button>
      {open && (
        <div className="h-[28rem] border-t border-slate-100 bg-white">
          <ResponseViewer result={r} />
        </div>
      )}
    </div>
  );
}

export function RunDetailPage() {
  const runId = Number(useParams().runId);
  const navigate = useNavigate();
  const { data: run, isLoading, error } = useRun(runId);
  const [failedOnly, setFailedOnly] = useState(false);

  if (isLoading) return <Spinner />;
  if (error || !run)
    return (
      <div className="p-6">
        <Alert>{error?.message ?? 'Run not found'}</Alert>
      </div>
    );

  const t = run.totals;
  const iterations = [...new Set(run.steps.map((s) => s.iteration))];
  const visible = (steps: RunStep[]) => (failedOnly ? steps.filter((s) => !s.result.passed) : steps);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold">
            Run #{run.id} · {run.collection_name}
          </h1>
          <PassBadge passed={run.status === 'passed'} />
          <span className="text-sm text-slate-500">
            {run.environment_name ?? 'No environment'} · {formatDate(run.started_at)}
          </span>
          <div className="ml-auto flex gap-2">
            {run.collection_id && (
              <Button size="sm" onClick={() => navigate(`/runner?collection=${run.collection_id}`)}>
                <RotateCcw className="size-3.5" /> Run again
              </Button>
            )}
            {(['html', 'junit', 'json'] as const).map((f) => (
              <Button key={f} size="sm" onClick={() => void api.downloadReport(run.id, f)}>
                <Download className="size-3.5" /> {f === 'junit' ? 'JUnit XML' : f.toUpperCase()}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Requests passed" value={`${t.passed}/${t.requests}`} tone={t.failed ? 'bad' : 'good'} />
          <Stat
            label="Assertions passed"
            value={`${t.assertions_passed}/${t.assertions_total}`}
            tone={t.assertions_failed ? 'bad' : 'good'}
          />
          <Stat label="Errors" value={t.errors} tone={t.errors ? 'bad' : undefined} />
          <Stat label="Avg response" value={formatMs(t.avg_response_ms)} />
          <Stat label="Duration" value={formatMs(t.duration_ms)} />
        </div>

        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center border-b border-slate-200 px-4 py-3">
            <h2 className="font-medium">Results</h2>
            <label className="ml-auto flex items-center gap-2 text-sm">
              <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} /> Failed
              only
            </label>
          </div>
          {iterations.map((it) => {
            const steps = visible(run.steps.filter((s) => s.iteration === it));
            if (!steps.length) return null;
            return (
              <div key={it}>
                {iterations.length > 1 && (
                  <div className="bg-slate-50 px-4 py-1.5 text-xs font-semibold text-slate-500 uppercase">
                    Iteration {it}
                  </div>
                )}
                {steps.map((s, i) => (
                  <StepRow key={`${it}-${i}`} step={s} />
                ))}
              </div>
            );
          })}
          {failedOnly && t.failed === 0 && <p className="p-4 text-sm text-emerald-700">Everything passed.</p>}
        </div>
      </div>
    </div>
  );
}
