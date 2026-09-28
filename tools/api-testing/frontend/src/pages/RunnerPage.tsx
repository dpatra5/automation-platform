import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { invalidateRuns, RunsTable } from '@/components/RunsTable';
import { Alert, Button, MethodBadge, Spinner } from '@/components/ui';
import { useCollection, useCollections, useEnvironments, useRuns } from '@/hooks/queries';
import { useWorkspace } from '@/hooks/workspace';
import { api } from '@/lib/api';

export function RunnerPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { environmentId, setEnvironmentId } = useWorkspace();
  const { data: collections } = useCollections();
  const { data: environments } = useEnvironments();

  const selectedId = Number(params.get('collection')) || collections?.[0]?.id || null;
  const { data: collection, isLoading } = useCollection(selectedId);
  const { data: runs } = useRuns(selectedId ?? undefined);

  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [iterations, setIterations] = useState(1);
  const [data, setData] = useState('');
  const [stopOnFailure, setStopOnFailure] = useState(false);
  const [delayMs, setDelayMs] = useState(0);

  useEffect(() => setExcluded(new Set()), [selectedId]);

  const selected = collection?.requests.filter((r) => !excluded.has(r.id)) ?? [];
  const run = useMutation({
    mutationFn: () =>
      api.createRun({
        collection_id: selectedId as number,
        environment_id: environmentId,
        request_ids: selected.map((r) => r.id),
        iterations,
        data,
        stop_on_failure: stopOnFailure,
        delay_ms: delayMs,
      }),
    onSuccess: (detail) => {
      invalidateRuns(client, selectedId ?? undefined);
      navigate(`/runs/${detail.id}`);
    },
  });

  const toggle = (id: number) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const rows = data.trim() ? data.trim().split(/\r?\n/).length - (data.trim().startsWith('[') ? 0 : 1) : 0;

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
          <h1 className="text-lg font-semibold">Collection runner</h1>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="run-collection">
                Collection
              </label>
              <select
                id="run-collection"
                className="input"
                value={selectedId ?? ''}
                onChange={(e) => setParams({ collection: e.target.value })}
              >
                {collections?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.request_count})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="run-env">
                Environment
              </label>
              <select
                id="run-env"
                className="input"
                value={environmentId ?? ''}
                onChange={(e) => setEnvironmentId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">No environment</option>
                {environments?.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center">
              <span className="label mb-0!">
                Requests ({selected.length}/{collection?.requests.length ?? 0}) — run in this order
              </span>
              <div className="ml-auto flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => setExcluded(new Set())}>
                  All
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setExcluded(new Set(collection?.requests.map((r) => r.id)))}
                >
                  None
                </Button>
              </div>
            </div>
            {isLoading ? (
              <Spinner />
            ) : (
              <ul className="max-h-72 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
                {collection?.requests.map((r, i) => (
                  <li key={r.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-1.5 text-sm hover:bg-slate-50">
                      <input type="checkbox" checked={!excluded.has(r.id)} onChange={() => toggle(r.id)} />
                      <span className="w-5 text-right text-xs text-slate-400">{i + 1}</span>
                      <MethodBadge method={r.method} className="w-9" />
                      <span className="truncate">{r.name}</span>
                      <span className="ml-auto text-xs text-slate-400">
                        {r.assertions.filter((a) => a.enabled).length} checks
                      </span>
                    </label>
                  </li>
                ))}
                {collection?.requests.length === 0 && <li className="p-3 text-sm text-slate-500">No requests.</li>}
              </ul>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="iterations">
                Iterations
              </label>
              <input
                id="iterations"
                type="number"
                min={1}
                max={100}
                className="input"
                disabled={!!data.trim()}
                value={iterations}
                onChange={(e) => setIterations(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
              />
            </div>
            <div>
              <label className="label" htmlFor="delay">
                Delay between requests (ms)
              </label>
              <input
                id="delay"
                type="number"
                min={0}
                max={60000}
                className="input"
                value={delayMs}
                onChange={(e) => setDelayMs(Math.min(60000, Math.max(0, Number(e.target.value) || 0)))}
              />
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center">
              <label className="label mb-0!" htmlFor="data">
                Test data (optional) — CSV with header row, or JSON array
              </label>
              <label className="ml-auto inline-flex cursor-pointer items-center gap-1 text-xs text-indigo-700 hover:underline">
                <Upload className="size-3.5" /> Load file
                <input
                  type="file"
                  accept=".csv,.json,.txt"
                  className="hidden"
                  onChange={(e) => void e.target.files?.[0]?.text().then(setData)}
                />
              </label>
            </div>
            <textarea
              id="data"
              className="input min-h-28 font-mono text-xs"
              spellCheck={false}
              placeholder={'username,password,expectedStatus\ndemo,demo123,200\ndemo,wrong,401'}
              value={data}
              onChange={(e) => setData(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              Each row is one iteration; columns become <code>{'{{variables}}'}</code>.
              {rows > 0 && ` About ${rows} row(s).`}
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={stopOnFailure} onChange={(e) => setStopOnFailure(e.target.checked)} />
            Stop at the first failing request
          </label>

          {run.error && <Alert>{run.error.message}</Alert>}
          <Button
            variant="primary"
            disabled={!selectedId || selected.length === 0}
            loading={run.isPending}
            onClick={() => run.mutate()}
          >
            <Play className="size-4" /> {run.isPending ? 'Running…' : `Run ${selected.length} request(s)`}
          </Button>
        </section>

        <aside className="space-y-3 text-sm text-slate-600">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-medium text-slate-900">How runs work</h2>
            <ul className="list-disc space-y-1 pl-4">
              <li>Requests run sequentially, in collection order.</li>
              <li>Values from <b>Extract</b> flow into later requests (e.g. login → token).</li>
              <li>Variables: collection &lt; environment &lt; data row &lt; extracted.</li>
              <li>Each iteration starts with fresh extracted values.</li>
              <li>Download JSON, JUnit XML (for CI) or HTML reports from the run page.</li>
            </ul>
          </div>
        </aside>

        <section className="rounded-lg border border-slate-200 bg-white lg:col-span-2">
          <h2 className="border-b border-slate-200 px-4 py-3 font-medium">Recent runs of this collection</h2>
          {runs ? <RunsTable runs={runs} /> : <Spinner />}
        </section>
      </div>
    </div>
  );
}
