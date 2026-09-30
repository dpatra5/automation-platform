import { ChevronDown, FileUp, Play, RotateCcw, ShieldCheck } from 'lucide-react';
import { useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router';

import { ConfigEditor } from '@/components/ConfigEditor';
import { PageHeader } from '@/components/layout/AppLayout';
import { ProfileChart } from '@/components/RunCharts';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field, Input, Select, Toggle } from '@/components/ui/Field';
import { Spinner } from '@/components/ui/Spinner';
import { useExamples, useStartRun, useValidation } from '@/hooks/queries';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { cn } from '@/lib/cn';
import { formatDuration, formatInt, formatRps } from '@/lib/format';
import type { ConfigSummary, Overrides, RouteSummary } from '@/lib/types';

const MAX_UPLOAD_BYTES = 256 * 1024;

const STARTER = `version: 1
name: my-first-run
base_url: http://127.0.0.1:8080
safety:
  allowlist: [127.0.0.1, localhost]
  max_rps_cap: 1000
model:
  workers: 4
  profile:
    - { duration: 10s, rate: 100 }
routes:
  - name: items
    method: GET
    path: /api/items
    expect_status: [200, 429]
`;

interface OverrideForm {
  rps: string;
  duration: string;
  processes: string;
  connections: string;
  concurrency: string;
  http2: 'config' | 'on' | 'off';
}

const EMPTY_OVERRIDES: OverrideForm = {
  rps: '',
  duration: '',
  processes: '',
  connections: '',
  concurrency: '',
  http2: 'config',
};

function toOverrides(f: OverrideForm): Overrides {
  const num = (v: string) => (v.trim() === '' || !Number.isFinite(Number(v)) ? null : Number(v));
  return {
    rps: num(f.rps),
    duration: f.duration.trim() || null,
    processes: num(f.processes),
    connections: num(f.connections),
    concurrency: num(f.concurrency),
    http2: f.http2 === 'config' ? null : f.http2 === 'on',
  };
}

function routeDetail(r: RouteSummary, closed: boolean): string {
  if (!closed) {
    const tenant = r.tenant ? `${r.tenant} · ` : '';
    return `${tenant}w=${r.weight}`;
  }
  const parts: string[] = [];
  if (r.checks) parts.push(`${r.checks} check${r.checks > 1 ? 's' : ''}`);
  if (r.extracts?.length) parts.push(`→ ${r.extracts.join(', ')}`);
  return parts.join(' · ');
}

function SummaryPanel({
  summary,
  warnings,
}: Readonly<{ summary: ConfigSummary; warnings: string[] }>) {
  const closed = summary.model_type === 'closed';
  const rows: [string, string][] = closed
    ? [
        ['Target', summary.base_url],
        ['Virtual users', `${formatInt(summary.peak_users)} peak`],
        ['Duration', formatDuration(summary.duration_s)],
        ...(summary.iterations
          ? [['Iterations', `${summary.iterations} per user`] as [string, string]]
          : []),
        [
          'Throughput cap',
          summary.max_rps
            ? `${formatRps(summary.max_rps)} rps`
            : `safety cap ${formatInt(summary.effective_cap)} rps`,
        ],
        ['Test data', summary.data_rows ? `${formatInt(summary.data_rows)} rows` : 'none'],
        ['Pass/fail checks', summary.thresholds ? `${summary.thresholds} threshold(s)` : 'none'],
      ]
    : [
        ['Target', summary.base_url],
        [
          'Peak rate',
          `${formatRps(summary.peak_rps)} rps (cap ${formatInt(summary.effective_cap)})`,
        ],
        ['Duration', formatDuration(summary.duration_s)],
        ['Expected requests', `~${formatInt(summary.expected_requests)}`],
        [
          'Execution',
          `${summary.processes} proc · ${summary.workers} shards · ${summary.concurrency_per_process} workers/proc`,
        ],
        ['HTTP/2', summary.http2 ? 'enabled' : 'disabled'],
      ];
  // Users ramp linearly between stages, the same shape as a rate profile.
  let previous = 0;
  const userSteps = (summary.stages ?? []).map((s) => {
    const step = { duration_s: s.duration_s, rate: previous, end_rate: s.users, name: null };
    previous = s.users;
    return step;
  });
  return (
    <div className="space-y-4">
      {warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      <dl className="space-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4">
            <dt className="text-slate-500 dark:text-slate-400">{k}</dt>
            <dd className="truncate text-right font-medium" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          {closed ? 'Virtual users over time' : 'Target rate'}
        </p>
        <ProfileChart
          steps={closed ? userSteps : summary.profile}
          unit={closed ? 'users' : 'rps'}
        />
      </div>
      <div>
        <p className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          {closed ? 'Scenario (each user runs these in order)' : 'Routes'}
        </p>
        <ol className="space-y-1.5">
          {summary.routes.map((r) => (
            <li key={r.name} className="flex items-center gap-2 text-sm">
              <Badge tone="brand" className="font-mono">
                {r.method}
              </Badge>
              <span className="truncate font-mono text-xs" title={r.name}>
                {r.path}
              </span>
              <span className="ml-auto shrink-0 text-xs text-slate-500 dark:text-slate-400">
                {routeDetail(r, closed)}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export function NewRunPage() {
  const navigate = useNavigate();
  const examples = useExamples();
  const [yaml, setYaml] = useState(STARTER);
  const [form, setForm] = useState<OverrideForm>(EMPTY_OVERRIDES);
  const [showOverrides, setShowOverrides] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const overrides = useMemo(() => toOverrides(form), [form]);
  const req = useMemo(() => ({ yaml, overrides }), [yaml, overrides]);
  const debouncedReq = useDebouncedValue(req, 500);
  const validation = useValidation(debouncedReq);
  const start = useStartRun();

  const pending = debouncedReq !== req || validation.isFetching;
  const result = validation.data;
  const canStart = !pending && result?.valid === true && !start.isPending;

  let validationBadge: ReactNode = null;
  if (pending) {
    validationBadge = <Spinner className="size-4 text-slate-400" label="Validating" />;
  } else if (result?.valid) {
    validationBadge = (
      <Badge tone="success">
        <ShieldCheck className="size-3" /> Valid
      </Badge>
    );
  } else if (result) {
    validationBadge = <Badge tone="danger">Invalid</Badge>;
  }

  const set = <K extends keyof OverrideForm>(key: K, value: OverrideForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const onUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError('File is larger than 256 KiB.');
      return;
    }
    setUploadError(null);
    void file.text().then(setYaml);
  };

  const onStart = () => {
    start.mutate(
      { yaml, overrides },
      {
        onSuccess: (run) => void navigate(`/runs/${encodeURIComponent(run.run_id)}`),
        onSettled: () => setConfirming(false),
      },
    );
  };

  return (
    <>
      <PageHeader
        title="New run"
        description="Define an open-model load profile. The config is validated against schema and safety guardrails as you type."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Load profile (YAML)"
              description="Environment variable references are not permitted through the API."
              actions={
                <>
                  <Select
                    aria-label="Load example"
                    value=""
                    onChange={(e) => {
                      const ex = examples.data?.find((x) => x.filename === e.target.value);
                      if (ex) setYaml(ex.yaml);
                    }}
                    className="h-8 w-44 text-xs"
                    disabled={!examples.data?.length}
                  >
                    <option value="">Load example…</option>
                    {examples.data?.map((ex) => (
                      <option key={ex.filename} value={ex.filename}>
                        {ex.name}
                      </option>
                    ))}
                  </Select>
                  <Button
                    size="sm"
                    icon={<FileUp className="size-3.5" />}
                    onClick={() => fileInput.current?.click()}
                  >
                    Upload
                  </Button>
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".yaml,.yml,text/yaml,application/x-yaml"
                    className="hidden"
                    onChange={onUpload}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<RotateCcw className="size-3.5" />}
                    onClick={() => setYaml(STARTER)}
                  >
                    Reset
                  </Button>
                </>
              }
            />
            <CardBody className="space-y-3">
              {uploadError && <Alert tone="danger">{uploadError}</Alert>}
              <ConfigEditor
                value={yaml}
                onChange={setYaml}
                invalid={result?.valid === false && !pending}
                className="h-120"
              />
            </CardBody>
          </Card>

          <Card>
            <button
              type="button"
              onClick={() => setShowOverrides((v) => !v)}
              aria-expanded={showOverrides}
              className="flex w-full items-center justify-between px-5 py-4 text-left"
            >
              <div>
                <h2 className="text-sm font-semibold">Overrides</h2>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Equivalent to <code>lt run</code> CLI flags. RPS/duration replace the profile with
                  one constant step.
                </p>
              </div>
              <ChevronDown
                className={cn(
                  'size-4 text-slate-400 transition-transform',
                  showOverrides && 'rotate-180',
                )}
              />
            </button>
            {showOverrides && (
              <CardBody className="grid grid-cols-2 gap-4 border-t border-slate-200 md:grid-cols-3 dark:border-slate-800">
                <Field label="Constant RPS">
                  <Input
                    inputMode="decimal"
                    value={form.rps}
                    onChange={(e) => set('rps', e.target.value)}
                  />
                </Field>
                <Field label="Duration" hint="e.g. 30s, 5m">
                  <Input value={form.duration} onChange={(e) => set('duration', e.target.value)} />
                </Field>
                <Field label="Processes">
                  <Input
                    inputMode="numeric"
                    value={form.processes}
                    onChange={(e) => set('processes', e.target.value)}
                  />
                </Field>
                <Field label="Max connections">
                  <Input
                    inputMode="numeric"
                    value={form.connections}
                    onChange={(e) => set('connections', e.target.value)}
                  />
                </Field>
                <Field label="Concurrency / process">
                  <Input
                    inputMode="numeric"
                    value={form.concurrency}
                    onChange={(e) => set('concurrency', e.target.value)}
                  />
                </Field>
                <div className="flex items-end pb-1.5">
                  <Toggle
                    label={form.http2 === 'config' ? 'HTTP/2 (from config)' : 'HTTP/2'}
                    checked={form.http2 === 'on'}
                    onChange={(on) => set('http2', on ? 'on' : 'off')}
                  />
                </div>
                <div className="col-span-full">
                  <Button size="sm" variant="ghost" onClick={() => setForm(EMPTY_OVERRIDES)}>
                    Clear overrides
                  </Button>
                </div>
              </CardBody>
            )}
          </Card>
        </div>

        <div className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <Card>
            <CardHeader title="Pre-flight check" actions={validationBadge} />
            <CardBody className="space-y-4">
              <ErrorAlert error={validation.error} title="Validation unavailable" />
              {result && !result.valid && (
                <Alert tone="danger" title="Fix these issues to continue">
                  <ul className="list-disc space-y-0.5 pl-4">
                    {result.errors.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                </Alert>
              )}
              {result?.summary && (
                <SummaryPanel summary={result.summary} warnings={result.warnings} />
              )}
              {!result && !validation.error && (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Enter a config to validate it.
                </p>
              )}
              <ErrorAlert error={start.error} title="Could not start run" />
              <Button
                variant="primary"
                className="w-full"
                disabled={!canStart}
                onClick={() => setConfirming(true)}
                icon={<Play className="size-4" />}
              >
                Start run
              </Button>
            </CardBody>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirming}
        title="Start load test?"
        confirmLabel="Start run"
        loading={start.isPending}
        onConfirm={onStart}
        onCancel={() => setConfirming(false)}
        description={
          result?.summary && (
            <p>
              This will send up to <strong>{formatRps(result.summary.peak_rps)} rps</strong> for{' '}
              <strong>{formatDuration(result.summary.duration_s)}</strong> to{' '}
              <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">
                {result.summary.host}
              </code>
              . Only test systems you are authorized to load.
            </p>
          )
        }
      />
    </>
  );
}
