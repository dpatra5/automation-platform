import { AlertTriangle, CheckCircle2, Copy, XCircle } from 'lucide-react';
import { useState } from 'react';

import { formatBytes, formatMs, prettyBody } from '@/lib/format';
import type { Assertion, ExecutionResult } from '@/lib/types';
import { Alert, Empty, IconButton, StatusPill, Tabs } from './ui';

type Tab = 'body' | 'headers' | 'tests' | 'extracted' | 'request';

export function describeAssertion(a: Assertion): string {
  const subject = {
    status: 'Status',
    response_time: 'Response time',
    header: `Header ${a.property}`,
    json: a.property || '$',
    body: 'Body',
    json_schema: 'Body matches JSON Schema',
  }[a.source];
  if (a.source === 'json_schema') return subject;
  const symbols: Record<string, string> = { lt: '<', lte: '<=', gt: '>', gte: '>=' };
  const op = symbols[a.operator] ?? a.operator.replace('_', ' ');
  return ['exists', 'not_exists'].includes(a.operator) ? `${subject} ${op}` : `${subject} ${op} ${a.expected}`;
}

export function AssertionResults({ result }: { result: ExecutionResult }) {
  if (result.assertions.length === 0) return <p className="p-3 text-sm text-slate-500">No assertions on this request.</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {result.assertions.map((a, i) => (
        <li key={i} className="flex items-start gap-2 px-3 py-2 text-sm">
          {a.passed ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
          ) : (
            <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
          )}
          <div className="min-w-0">
            <div className="font-mono text-xs break-all">{describeAssertion(a.assertion)}</div>
            {!a.passed && a.message && <div className="text-rose-700">{a.message}</div>}
            {a.actual !== null && <div className="text-xs break-all text-slate-500">actual: {a.actual}</div>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <IconButton
      label={copied ? 'Copied' : 'Copy'}
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
    >
      <Copy className="size-4" />
    </IconButton>
  );
}

function HeaderTable({ headers }: { headers: [string, string][] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {headers.map(([k, v], i) => (
          <tr key={i} className="border-b border-slate-100">
            <td className="w-1/3 px-3 py-1.5 align-top font-mono text-xs font-medium break-all">{k}</td>
            <td className="px-3 py-1.5 font-mono text-xs break-all">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ResponseViewer({ result, loading }: { result: ExecutionResult | null; loading?: boolean }) {
  const [tab, setTab] = useState<Tab>('body');
  const [raw, setRaw] = useState(false);

  if (loading) return <Empty title="Sending request…" />;
  if (!result) return <Empty title="No response yet">Press Send (Ctrl+Enter) to execute the request.</Empty>;

  const r = result.response;
  const failed = result.assertions.filter((a) => !a.passed).length;
  const body = r ? (raw ? r.body : prettyBody(r.body, r.content_type)) : '';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
        <StatusPill status={r?.status} reason={r?.reason} />
        {r && (
          <>
            <span className="text-slate-500">
              Time <b className="text-slate-800">{formatMs(r.elapsed_ms)}</b>
            </span>
            <span className="text-slate-500">
              Size <b className="text-slate-800">{formatBytes(r.size_bytes)}</b>
            </span>
          </>
        )}
        {result.assertions.length > 0 && (
          <span className={failed ? 'font-medium text-rose-600' : 'font-medium text-emerald-600'}>
            {result.assertions.length - failed}/{result.assertions.length} assertions passed
          </span>
        )}
      </div>
      <div className="space-y-2 px-3">
        {result.error && <Alert>{result.error}</Alert>}
        {result.unresolved.length > 0 && !result.error && (
          <Alert tone="warning">
            <AlertTriangle className="mr-1 inline size-4" />
            Unresolved variables: {result.unresolved.join(', ')}
          </Alert>
        )}
      </div>
      <div className="px-3">
        <Tabs<Tab>
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'body', label: 'Body' },
            { id: 'headers', label: 'Headers', count: r?.headers.length },
            { id: 'tests', label: 'Test results', count: result.assertions.length },
            { id: 'extracted', label: 'Extracted', count: result.extractions.length },
            { id: 'request', label: 'Request sent' },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === 'body' &&
          (r ? (
            <div className="relative">
              <div className="sticky top-0 flex items-center justify-end gap-2 bg-white/90 px-3 py-1 text-xs">
                {r.body_truncated && <span className="text-amber-700">Body truncated</span>}
                <label className="flex items-center gap-1 text-slate-500">
                  <input type="checkbox" checked={raw} onChange={(e) => setRaw(e.target.checked)} /> Raw
                </label>
                <CopyButton text={r.body} />
              </div>
              {r.is_binary ? (
                <p className="px-3 text-sm text-slate-500">Binary response ({r.content_type || 'unknown type'}) not shown.</p>
              ) : (
                <pre className="px-3 pb-3 font-mono text-xs break-all whitespace-pre-wrap">{body || '(empty body)'}</pre>
              )}
            </div>
          ) : (
            <p className="p-3 text-sm text-slate-500">No response received.</p>
          ))}
        {tab === 'headers' && r && <HeaderTable headers={r.headers} />}
        {tab === 'tests' && <AssertionResults result={result} />}
        {tab === 'extracted' &&
          (result.extractions.length ? (
            <ul className="divide-y divide-slate-100 text-sm">
              {result.extractions.map((e, i) => (
                <li key={i} className="flex gap-3 px-3 py-2">
                  <span className="font-mono text-xs font-medium">{`{{${e.variable}}}`}</span>
                  {e.ok ? (
                    <span className="font-mono text-xs break-all">{e.value}</span>
                  ) : (
                    <span className="text-rose-700">{e.message}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="p-3 text-sm text-slate-500">No extractions on this request.</p>
          ))}
        {tab === 'request' && (
          <div className="space-y-2 p-3">
            <div className="font-mono text-xs break-all">
              <b>{result.request.method}</b> {result.request.url}
            </div>
            <HeaderTable headers={result.request.headers} />
            {result.request.body !== null && (
              <pre className="rounded bg-slate-50 p-2 font-mono text-xs break-all whitespace-pre-wrap">
                {result.request.body}
              </pre>
            )}
            <p className="text-xs text-slate-500">Secret variables and credentials are masked.</p>
          </div>
        )}
      </div>
    </div>
  );
}
