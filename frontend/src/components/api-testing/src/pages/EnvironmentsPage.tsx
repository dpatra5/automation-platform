import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Save, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { VariablesEditor } from '@/components/KeyValueEditor';
import { Alert, Button, Empty, Spinner } from '@/components/ui';
import { keys, useEnvironments } from '@/hooks/queries';
import { useWorkspace } from '@/hooks/workspace';
import { api } from '@/lib/api';
import type { Environment } from '@/lib/types';

function EnvironmentEditor({ env, onDeleted }: { env: Environment; onDeleted: () => void }) {
  const client = useQueryClient();
  const { environmentId, setEnvironmentId } = useWorkspace();
  const [name, setName] = useState(env.name);
  const [variables, setVariables] = useState(env.variables);
  const dirty = name !== env.name || JSON.stringify(variables) !== JSON.stringify(env.variables);

  const save = useMutation({
    mutationFn: () => api.updateEnvironment(env.id, { name, variables }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.environments }),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteEnvironment(env.id),
    onSuccess: () => {
      if (environmentId === env.id) setEnvironmentId(null);
      void client.invalidateQueries({ queryKey: keys.environments });
      onDeleted();
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <input
          className="input text-base font-semibold"
          aria-label="Environment name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          variant={environmentId === env.id ? 'secondary' : 'ghost'}
          onClick={() => setEnvironmentId(environmentId === env.id ? null : env.id)}
        >
          {environmentId === env.id ? 'Active' : 'Use'}
        </Button>
        <Button variant="primary" disabled={!dirty || !name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
          <Save className="size-4" /> Save
        </Button>
        <Button
          variant="ghost"
          onClick={() => window.confirm(`Delete environment "${env.name}"?`) && remove.mutate()}
          title="Delete environment"
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
      {save.error && <Alert>{save.error.message}</Alert>}
      <VariablesEditor rows={variables} onChange={setVariables} />
      <p className="text-xs text-slate-500">
        Secret values are masked in the UI, replaced with •••••• in stored run reports, and blanked in collection
        exports. They are stored locally in this tool's database.
      </p>
    </div>
  );
}

export function EnvironmentsPage() {
  const client = useQueryClient();
  const { data: environments, isLoading, error } = useEnvironments();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = environments?.find((e) => e.id === selectedId) ?? environments?.[0];

  const create = useMutation({
    mutationFn: () => api.createEnvironment({ name: 'New environment', variables: [] }),
    onSuccess: (env) => {
      void client.invalidateQueries({ queryKey: keys.environments });
      setSelectedId(env.id);
    },
  });

  return (
    <div className="flex h-full">
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white">
        <div className="flex items-center border-b border-slate-200 px-3 py-2">
          <span className="text-sm font-semibold">Environments</span>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => create.mutate()} loading={create.isPending}>
            <Plus className="size-3.5" /> New
          </Button>
        </div>
        {isLoading && <Spinner />}
        {error && <Alert>{error.message}</Alert>}
        {environments?.map((e) => (
          <button
            key={e.id}
            type="button"
            className={`block w-full truncate px-4 py-2 text-left text-sm hover:bg-slate-50 ${
              selected?.id === e.id ? 'bg-indigo-50 font-medium text-indigo-700' : ''
            }`}
            onClick={() => setSelectedId(e.id)}
          >
            {e.name}
            <span className="ml-1 text-xs text-slate-400">{e.variables.length}</span>
          </button>
        ))}
      </aside>
      <div className="min-w-0 flex-1 overflow-y-auto bg-white p-6">
        <div className="mx-auto max-w-4xl">
          {selected ? (
            <EnvironmentEditor key={selected.id} env={selected} onDeleted={() => setSelectedId(null)} />
          ) : (
            !isLoading && (
              <Empty title="No environments">
                <p className="text-sm">Create one to hold values such as baseUrl and credentials per stage.</p>
              </Empty>
            )
          )}
        </div>
      </div>
    </div>
  );
}
