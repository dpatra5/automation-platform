import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { Link } from 'react-router';

import { keys } from '@/hooks/queries';
import { api } from '@/lib/api';
import { formatDate, formatMs } from '@/lib/format';
import type { RunSummary } from '@/lib/types';
import { IconButton, PassBadge } from './ui';

export function RunsTable({ runs }: { runs: RunSummary[] }) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteRun(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['runs'] }),
  });

  if (!runs.length) return <p className="p-4 text-sm text-slate-500">No runs yet.</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
          <th className="px-3 py-2">Run</th>
          <th className="px-3 py-2">Result</th>
          <th className="px-3 py-2">Collection</th>
          <th className="px-3 py-2">Environment</th>
          <th className="px-3 py-2">Requests</th>
          <th className="px-3 py-2">Assertions</th>
          <th className="px-3 py-2">Avg time</th>
          <th className="px-3 py-2">Started</th>
          <th className="w-8" />
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
            <td className="px-3 py-2">
              <Link to={`/runs/${r.id}`} className="font-medium text-indigo-700 hover:underline">
                #{r.id}
              </Link>
            </td>
            <td className="px-3 py-2">
              <PassBadge passed={r.status === 'passed'} />
            </td>
            <td className="px-3 py-2">{r.collection_name}</td>
            <td className="px-3 py-2 text-slate-600">{r.environment_name ?? '—'}</td>
            <td className="px-3 py-2">
              {r.totals.passed}/{r.totals.requests}
              {r.totals.iterations > 1 && <span className="text-slate-400"> · {r.totals.iterations} iter.</span>}
            </td>
            <td className="px-3 py-2">
              {r.totals.assertions_passed}/{r.totals.assertions_total}
            </td>
            <td className="px-3 py-2">{formatMs(r.totals.avg_response_ms)}</td>
            <td className="px-3 py-2 text-slate-600">{formatDate(r.started_at)}</td>
            <td className="px-2">
              <IconButton label="Delete run" onClick={() => remove.mutate(r.id)}>
                <Trash2 className="size-4" />
              </IconButton>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function invalidateRuns(client: ReturnType<typeof useQueryClient>, collectionId?: number) {
  void client.invalidateQueries({ queryKey: keys.runs() });
  if (collectionId) void client.invalidateQueries({ queryKey: keys.runs(collectionId) });
}
