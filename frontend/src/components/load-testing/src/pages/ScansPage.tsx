import { ChevronDown, Globe, Radar } from 'lucide-react';
import { useState, type SyntheticEvent } from 'react';
import { useNavigate } from 'react-router';

import { PageHeader } from '@/components/layout/AppLayout';
import { PlanFields } from '@/components/scan/PlanFields';
import { ScanStatusBadge } from '@/components/StatusBadge';
import { Alert, ErrorAlert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Input, Toggle } from '@/components/ui/Field';
import { Skeleton } from '@/components/ui/Spinner';
import { useScans, useStartScan } from '@/hooks/queries';
import { cn } from '@/lib/cn';
import { formatRelative } from '@/lib/format';
import { DEFAULT_PLAN, parseHeaders, splitList } from '@/lib/scan';
import type { LoadPlan } from '@/lib/types';

function ScanForm() {
  const navigate = useNavigate();
  const start = useStartScan();
  const [url, setUrl] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [maxPages, setMaxPages] = useState(10);
  const [maxDepth, setMaxDepth] = useState(2);
  const [waitMs, setWaitMs] = useState(1500);
  const [scope, setScope] = useState('');
  const [headersText, setHeadersText] = useState('');
  const [ignoreTls, setIgnoreTls] = useState(false);
  const [includeUnsafe, setIncludeUnsafe] = useState(false);
  const [autoRun, setAutoRun] = useState(true);
  const [plan, setPlan] = useState<LoadPlan>(DEFAULT_PLAN);

  const parsed = parseHeaders(headersText);

  const onSubmit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (parsed.error) return;
    start.mutate(
      {
        discovery: {
          url: url.trim(),
          max_pages: maxPages,
          max_depth: maxDepth,
          wait_ms: waitMs,
          scope: splitList(scope),
          headers: parsed.headers,
          ignore_https_errors: ignoreTls,
        },
        plan,
        auto_run: autoRun,
        include_unsafe_methods: includeUnsafe,
      },
      { onSuccess: (scan) => void navigate(`/scans/${encodeURIComponent(scan.id)}`) },
    );
  };

  return (
    <Card className="mb-6">
      <CardHeader
        title="Scan a web app"
        description="A headless browser opens the URL, follows same-site links, records every API call the pages make, and load-tests each one."
      />
      <CardBody>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Globe className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
              <Input
                type="url"
                required
                aria-label="Web app URL"
                placeholder="https://app.example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="h-11 pl-9 text-base"
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              className="h-11 px-5"
              loading={start.isPending}
              icon={<Radar className="size-4" />}
            >
              {autoRun ? 'Scan & load test' : 'Discover APIs'}
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Toggle label="Run load tests automatically" checked={autoRun} onChange={setAutoRun} />
            <Toggle
              label="Include POST/PUT/PATCH/DELETE"
              checked={includeUnsafe}
              onChange={setIncludeUnsafe}
            />
          </div>
          {includeUnsafe && (
            <Alert tone="warning">
              Data-modifying requests will be replayed at the configured rate. Only enable this
              against disposable test environments.
            </Alert>
          )}

          <PlanFields value={plan} onChange={setPlan} />

          <button
            type="button"
            onClick={() => setAdvanced((v) => !v)}
            aria-expanded={advanced}
            className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          >
            <ChevronDown
              className={cn('size-3.5 transition-transform', advanced && 'rotate-180')}
            />
            Crawl & authentication options
          </button>
          {advanced && (
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="Max pages">
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={maxPages}
                  onChange={(e) => setMaxPages(Number(e.target.value))}
                />
              </Field>
              <Field label="Link depth" hint="0 = only the given URL">
                <Input
                  type="number"
                  min={0}
                  max={10}
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(Number(e.target.value))}
                />
              </Field>
              <Field label="Settle time per page (ms)">
                <Input
                  type="number"
                  min={0}
                  max={30000}
                  value={waitMs}
                  onChange={(e) => setWaitMs(Number(e.target.value))}
                />
              </Field>
              <Field
                label="Extra API hosts"
                hint="Comma-separated, e.g. api.example.net, *.cdn.example.com"
                className="md:col-span-3"
              >
                <Input value={scope} onChange={(e) => setScope(e.target.value)} />
              </Field>
              <Field
                label="Request headers"
                hint="One 'Name: value' per line, e.g. Authorization: Bearer … — sent while crawling and during load tests; never stored on disk."
                error={parsed.error}
                className="md:col-span-3"
              >
                <textarea
                  rows={3}
                  spellCheck={false}
                  value={headersText}
                  onChange={(e) => setHeadersText(e.target.value)}
                  className="block w-full rounded-md border-0 bg-white px-3 py-2 font-mono text-xs text-slate-900 shadow-xs ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-brand-500 focus:outline-none dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-700"
                />
              </Field>
              <div className="md:col-span-3">
                <Toggle
                  label="Ignore TLS certificate errors"
                  checked={ignoreTls}
                  onChange={setIgnoreTls}
                />
              </div>
            </div>
          )}
          <ErrorAlert error={start.error} title="Could not start scan" />
        </form>
      </CardBody>
    </Card>
  );
}

export function ScansPage() {
  const scans = useScans();
  const navigate = useNavigate();
  const items = scans.data ?? [];
  return (
    <>
      <PageHeader
        title="Auto scan"
        description="Give a URL — lt discovers the APIs behind it with Playwright and tests every one."
      />
      <ScanForm />
      <Card>
        <CardHeader title="Recent scans" />
        <ErrorAlert error={scans.error} title="Could not load scans" />
        {scans.isPending ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Radar className="size-5" />}
            title="No scans yet"
            description="Enter a URL above to discover and load-test its APIs."
          />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {items.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => void navigate(`/scans/${encodeURIComponent(s.id)}`)}
                  className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{s.url}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatRelative(s.created_at)} · {s.endpoints_found} API(s) found
                      {s.items_total > 0 && ` · ${s.items_done}/${s.items_total} tests done`}
                    </p>
                  </div>
                  <ScanStatusBadge status={s.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
