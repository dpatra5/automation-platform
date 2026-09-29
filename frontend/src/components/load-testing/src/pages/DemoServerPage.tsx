import { Copy, Play, Server, Square } from 'lucide-react';
import { useState, type SyntheticEvent } from 'react';

import { PageHeader } from '@/components/layout/AppLayout';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Input, Select } from '@/components/ui/Field';
import { PageLoader } from '@/components/ui/Spinner';
import { useDemoControl, useDemoState, useDemoStats } from '@/hooks/queries';
import { formatInt, formatPct } from '@/lib/format';
import type { DemoAlgo, DemoScope, DemoServerRequest } from '@/lib/types';

const DEFAULTS: DemoServerRequest = {
  port: 8080,
  rate: 1000,
  burst: null,
  window: '1s',
  algo: 'token-bucket',
  scope: 'global',
  key_header: 'X-API-Key',
  latency_ms: 0,
};

const ALGOS: { id: DemoAlgo; label: string; hint: string }[] = [
  {
    id: 'token-bucket',
    label: 'Token bucket',
    hint: 'Allows bursts up to capacity, refills continuously',
  },
  {
    id: 'fixed-window',
    label: 'Fixed window',
    hint: 'Counter resets at clock-aligned window boundaries',
  },
  { id: 'sliding-window', label: 'Sliding window', hint: 'Exact rolling log of the last window' },
];

function StatsTable({ enabled }: { enabled: boolean }) {
  const stats = useDemoStats(enabled);
  const entries = Object.entries(stats.data ?? {});
  if (stats.error) return <ErrorAlert error={stats.error} title="Could not load stats" />;
  if (!entries.length) {
    return (
      <EmptyState
        title="No traffic yet"
        description="Counters appear per limiter key as soon as requests arrive."
      />
    );
  }
  return (
    <table className="min-w-full text-sm tabular-nums">
      <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
        <tr>
          <th className="px-5 py-2 font-medium">Key</th>
          <th className="px-5 py-2 text-right font-medium">Allowed</th>
          <th className="px-5 py-2 text-right font-medium">Denied (429)</th>
          <th className="px-5 py-2 text-right font-medium">Acceptance</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
        {entries.map(([key, v]) => (
          <tr key={key}>
            <td className="px-5 py-2 font-mono">{key}</td>
            <td className="px-5 py-2 text-right">{formatInt(v.allowed)}</td>
            <td className="px-5 py-2 text-right">{formatInt(v.denied)}</td>
            <td className="px-5 py-2 text-right">
              {formatPct(v.allowed + v.denied ? v.allowed / (v.allowed + v.denied) : null)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DemoServerPage() {
  const state = useDemoState();
  const { start, stop } = useDemoControl();
  const [form, setForm] = useState<DemoServerRequest>(DEFAULTS);
  const [copied, setCopied] = useState(false);

  const set = <K extends keyof DemoServerRequest>(key: K, value: DemoServerRequest[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const onSubmit = (e: SyntheticEvent) => {
    e.preventDefault();
    start.mutate(form);
  };

  if (state.isPending) return <PageLoader />;
  const running = state.data?.running ?? false;
  const s = state.data?.settings;

  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <>
      <PageHeader
        title="Demo server"
        description="A local, rate-limited API (bound to 127.0.0.1) for trying profiles and validating limiter analysis."
        meta={
          running ? (
            <Badge tone="success" dot pulse>
              Running
            </Badge>
          ) : (
            <Badge>Stopped</Badge>
          )
        }
      />
      <ErrorAlert error={state.error} title="Could not reach the API" />

      <div className="grid gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Limiter settings" />
          <CardBody>
            <form onSubmit={onSubmit} className="space-y-4">
              <fieldset disabled={running || start.isPending} className="space-y-4">
                <Field label="Algorithm" hint={ALGOS.find((a) => a.id === form.algo)?.hint}>
                  <Select
                    value={form.algo}
                    onChange={(e) => set('algo', e.target.value as DemoAlgo)}
                  >
                    {ALGOS.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Rate (requests / window)">
                    <Input
                      type="number"
                      min={1}
                      step="any"
                      required
                      value={form.rate}
                      onChange={(e) => set('rate', Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Window" hint="e.g. 1s, 500ms">
                    <Input
                      required
                      value={form.window}
                      onChange={(e) => set('window', e.target.value)}
                    />
                  </Field>
                  <Field label="Burst" hint="Token bucket only; default = rate">
                    <Input
                      type="number"
                      min={1}
                      value={form.burst ?? ''}
                      onChange={(e) => set('burst', e.target.value ? Number(e.target.value) : null)}
                    />
                  </Field>
                  <Field label="Artificial latency (ms)">
                    <Input
                      type="number"
                      min={0}
                      step="any"
                      value={form.latency_ms}
                      onChange={(e) => set('latency_ms', Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Scope">
                    <Select
                      value={form.scope}
                      onChange={(e) => set('scope', e.target.value as DemoScope)}
                    >
                      <option value="global">Global</option>
                      <option value="per-key">Per key</option>
                    </Select>
                  </Field>
                  <Field label="Port" hint="0 = random free port">
                    <Input
                      type="number"
                      min={0}
                      max={65535}
                      required
                      value={form.port}
                      onChange={(e) => set('port', Number(e.target.value))}
                    />
                  </Field>
                </div>
                {form.scope === 'per-key' && (
                  <Field label="Key header">
                    <Input
                      value={form.key_header}
                      onChange={(e) => set('key_header', e.target.value)}
                    />
                  </Field>
                )}
              </fieldset>
              <ErrorAlert error={start.error} title="Could not start demo server" />
              <ErrorAlert error={stop.error} title="Could not stop demo server" />
              {running ? (
                <Button
                  variant="danger"
                  className="w-full"
                  icon={<Square className="size-4" />}
                  loading={stop.isPending}
                  onClick={() => stop.mutate()}
                >
                  Stop server
                </Button>
              ) : (
                <Button
                  type="submit"
                  variant="primary"
                  className="w-full"
                  icon={<Play className="size-4" />}
                  loading={start.isPending}
                >
                  Start server
                </Button>
              )}
            </form>
          </CardBody>
        </Card>

        <div className="space-y-6">
          {running && state.data?.base_url ? (
            <>
              <Alert
                tone="success"
                title="Demo server is live"
                action={
                  <Button
                    size="sm"
                    icon={<Copy className="size-3.5" />}
                    onClick={() => void copy(state.data.base_url ?? '')}
                  >
                    {copied ? 'Copied' : 'Copy URL'}
                  </Button>
                }
              >
                <code>{state.data.base_url}</code> · {s?.algo} · {s?.rate}/{s?.window}
                {s?.burst ? ` · burst ${s.burst}` : ''} · {s?.scope}
                {'\n'}Use this as <code>base_url</code> and add its host to{' '}
                <code>safety.allowlist</code>. Rate-limited paths: anything except /healthz and
                /__stats.
              </Alert>
              <Card>
                <CardHeader title="Limiter counters" description="Refreshed every second" />
                <StatsTable enabled={running} />
              </Card>
            </>
          ) : (
            <Card>
              <EmptyState
                icon={<Server className="size-5" />}
                title="Demo server is stopped"
                description="Configure a limiter and start the server to get a local target for load tests."
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
