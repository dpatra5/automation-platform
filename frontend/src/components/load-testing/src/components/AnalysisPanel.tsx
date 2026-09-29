import { FlaskConical } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';

import { CapacityChart } from '@/components/RunCharts';
import { VerdictBadge } from '@/components/StatusBadge';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Input } from '@/components/ui/Field';
import { useAnalyze } from '@/hooks/queries';
import { formatPct, formatRps, humanize, isNum } from '@/lib/format';
import type { Analysis, AnalysisSection, AnalyzeRequest } from '@/lib/types';

const SECTIONS = [
  {
    key: 'sustained',
    title: 'Sustained capacity',
    hint: 'Steady-state accepted rate vs. the limit',
  },
  { key: 'burst', title: 'Burst', hint: 'Token-bucket burst size inferred after idle' },
  { key: 'step', title: 'Step / capacity curve', hint: 'Knee point across constant-rate steps' },
  { key: 'fairness', title: 'Fairness', hint: 'Max-min fair share across tenants' },
] as const;

const HIDDEN_KEYS = new Set([
  'applicable',
  'pass',
  'capacity_curve',
  'tenants',
  'headers',
  'knee_point',
  'segment',
  'basis',
  'method',
]);

function renderValue(v: unknown): ReactNode {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(3);
  if (typeof v === 'string') return v;
  return JSON.stringify(v);
}

function KeyValues({ section }: { section: AnalysisSection }) {
  const entries = Object.entries(section).filter(
    ([k, v]) => !HIDDEN_KEYS.has(k) && (typeof v !== 'object' || v === null),
  );
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div
          key={k}
          className="flex justify-between gap-3 border-b border-dashed border-slate-100 py-1 dark:border-slate-800"
        >
          <dt className="text-slate-500 dark:text-slate-400">{humanize(k)}</dt>
          <dd className="text-right font-medium tabular-nums">{renderValue(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function SectionCard({
  title,
  hint,
  section,
}: {
  title: string;
  hint: string;
  section: AnalysisSection;
}) {
  const applicable = section.applicable !== false;
  const curve = (section as Analysis['step']).capacity_curve;
  const tenants = (section as Analysis['fairness']).tenants;
  return (
    <Card>
      <CardHeader
        title={title}
        description={hint}
        actions={
          applicable ? (
            <VerdictBadge pass={section.pass} na="info" />
          ) : (
            <Badge>Not applicable</Badge>
          )
        }
      />
      <CardBody className="space-y-4">
        {!applicable ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {typeof section.reason === 'string'
              ? section.reason
              : 'Not applicable to this profile.'}
          </p>
        ) : (
          <>
            <KeyValues section={section} />
            {curve && curve.length > 0 && <CapacityChart data={curve} />}
            {tenants && (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
                    <tr>
                      <th className="py-1.5 pr-4 font-medium">Tenant</th>
                      <th className="py-1.5 pr-4 text-right font-medium">Attempted</th>
                      <th className="py-1.5 pr-4 text-right font-medium">Accepted</th>
                      <th className="py-1.5 pr-4 text-right font-medium">Fair share</th>
                      <th className="py-1.5 text-right font-medium">Acceptance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 tabular-nums dark:divide-slate-800">
                    {Object.entries(tenants).map(([name, t]) => (
                      <tr key={name}>
                        <td className="py-1.5 pr-4 font-medium">{name}</td>
                        <td className="py-1.5 pr-4 text-right">{formatRps(t.attempted_rps)}</td>
                        <td className="py-1.5 pr-4 text-right">{formatRps(t.accepted_rps)}</td>
                        <td className="py-1.5 pr-4 text-right">{formatRps(t.fair_share_rps)}</td>
                        <td className="py-1.5 text-right">{formatPct(t.acceptance_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function numOrNull(v: string): number | null {
  if (v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function AnalyzeForm({ runId, analysis }: { runId: string; analysis: Analysis | null }) {
  const s = analysis?.settings;
  const [limit, setLimit] = useState(
    isNum(s?.expected_limit_rps) ? String(s.expected_limit_rps) : '',
  );
  const [burst, setBurst] = useState(isNum(s?.expected_burst) ? String(s.expected_burst) : '');
  const [tolerance, setTolerance] = useState(isNum(s?.tolerance) ? String(s.tolerance) : '');
  const [fairness, setFairness] = useState(
    isNum(s?.fairness_threshold) ? String(s.fairness_threshold) : '',
  );
  const analyze = useAnalyze(runId);

  const onSubmit = (e: SyntheticEvent) => {
    e.preventDefault();
    const req: AnalyzeRequest = {
      expected_limit_rps: numOrNull(limit),
      expected_burst: numOrNull(burst),
      tolerance: numOrNull(tolerance),
      fairness_threshold: numOrNull(fairness),
    };
    analyze.mutate(req);
  };

  return (
    <Card>
      <CardHeader
        title="Analysis parameters"
        description="Leave blank to use the values from the run's config."
      />
      <CardBody>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Field label="Expected limit (RPS)">
              <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} />
            </Field>
            <Field label="Expected burst">
              <Input inputMode="decimal" value={burst} onChange={(e) => setBurst(e.target.value)} />
            </Field>
            <Field label="Tolerance (0–1)">
              <Input
                inputMode="decimal"
                value={tolerance}
                placeholder="0.05"
                onChange={(e) => setTolerance(e.target.value)}
              />
            </Field>
            <Field label="Fairness threshold (≥ 1)">
              <Input
                inputMode="decimal"
                value={fairness}
                placeholder="1.2"
                onChange={(e) => setFairness(e.target.value)}
              />
            </Field>
          </div>
          <ErrorAlert error={analyze.error} title="Analysis failed" />
          <Button
            type="submit"
            variant="primary"
            loading={analyze.isPending}
            icon={<FlaskConical className="size-4" />}
          >
            {analysis ? 'Re-run analysis' : 'Run analysis'}
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

export function AnalysisPanel({ runId, analysis }: { runId: string; analysis: Analysis | null }) {
  return (
    <div className="space-y-5">
      <AnalyzeForm runId={runId} analysis={analysis} />
      {!analysis ? (
        <Card>
          <EmptyState
            icon={<FlaskConical className="size-5" />}
            title="Not analyzed yet"
            description="Run the analysis to verify sustained capacity, burst size, knee point, fairness, rate-limit headers, and window semantics."
          />
        </Card>
      ) : (
        <>
          <Alert
            tone={analysis.pass ? 'success' : 'danger'}
            title={analysis.pass ? 'All applicable checks passed' : 'One or more checks failed'}
          >
            {Object.entries(analysis.checks)
              .map(([k, v]) => `${humanize(k)}: ${v === null ? 'info' : v ? 'pass' : 'fail'}`)
              .join(' · ')}
          </Alert>
          {!analysis.validity.pass && (
            <Alert tone="warning" title="Run validity concerns">
              {analysis.validity.reasons.join('\n')}
            </Alert>
          )}
          <Card>
            <CardHeader
              title="Window semantics"
              description="Inferred limiter algorithm"
              actions={
                <Badge tone="brand">
                  {analysis.window_semantics.classification} ·{' '}
                  {formatPct(analysis.window_semantics.confidence, 0)} confidence
                </Badge>
              }
            />
            <CardBody>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {analysis.window_semantics.rationale}
              </p>
            </CardBody>
          </Card>
          <div className="grid gap-5 xl:grid-cols-2">
            {SECTIONS.map(({ key, title, hint }) => (
              <SectionCard key={key} title={title} hint={hint} section={analysis[key]} />
            ))}
          </div>
          <Card>
            <CardHeader title="Rate-limit headers" description="Observed response headers" />
            <CardBody>
              <KeyValues section={analysis.headers} />
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
