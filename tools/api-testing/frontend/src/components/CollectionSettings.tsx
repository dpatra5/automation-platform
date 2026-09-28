import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Save } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { keys } from '@/hooks/queries';
import { api } from '@/lib/api';
import type { Collection } from '@/lib/types';
import { VariablesEditor } from './KeyValueEditor';
import { Alert, Button } from './ui';

export function CollectionSettings({ collection }: { collection: Collection }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(collection.name);
  const [description, setDescription] = useState(collection.description);
  const [variables, setVariables] = useState(collection.variables);

  const save = useMutation({
    mutationFn: () => api.updateCollection(collection.id, { name, description, variables }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.collections });
      void client.invalidateQueries({ queryKey: keys.collection(collection.id) });
    },
  });

  return (
    <div className="h-full overflow-y-auto bg-white p-6">
      <div className="mx-auto max-w-3xl space-y-5">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold">Collection settings</h1>
          <Button className="ml-auto" onClick={() => navigate(`/runner?collection=${collection.id}`)}>
            <Play className="size-4" /> Run collection
          </Button>
          <Button variant="primary" onClick={() => save.mutate()} disabled={!name.trim()} loading={save.isPending}>
            <Save className="size-4" /> Save
          </Button>
        </div>
        {save.error && <Alert>{save.error.message}</Alert>}
        {save.isSuccess && <Alert tone="info">Saved.</Alert>}
        <div>
          <label className="label" htmlFor="col-name">
            Name
          </label>
          <input id="col-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="col-desc">
            Description
          </label>
          <textarea
            id="col-desc"
            className="input min-h-20"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div>
          <h2 className="mb-1 font-medium">Collection variables</h2>
          <p className="mb-2 text-sm text-slate-500">
            Defaults for every request in this collection. Environment values override them, and values extracted
            during a run override both.
          </p>
          <VariablesEditor rows={variables} onChange={setVariables} />
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          <b>Dynamic variables:</b> <code>{'{{$uuid}}'}</code>, <code>{'{{$timestamp}}'}</code>,{' '}
          <code>{'{{$isoTimestamp}}'}</code>, <code>{'{{$randomInt}}'}</code>, <code>{'{{$randomEmail}}'}</code>
        </div>
      </div>
    </div>
  );
}
