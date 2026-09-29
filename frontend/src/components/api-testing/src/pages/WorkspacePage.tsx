import { Eraser, Variable as VariableIcon } from 'lucide-react';
import { useSearchParams } from 'react-router';

import { CollectionSettings } from '@/components/CollectionSettings';
import { CollectionSidebar } from '@/components/CollectionSidebar';
import { RequestEditor } from '@/components/RequestEditor';
import { Alert, Button, Empty, Spinner } from '@/components/ui';
import { useCollection } from '@/hooks/queries';
import { useWorkspace } from '@/hooks/workspace';

function toId(value: string | null): number | null {
  const n = Number(value);
  return value && Number.isInteger(n) && n > 0 ? n : null;
}

function SessionVariablesBar() {
  const { sessionVariables, clearSessionVariables } = useWorkspace();
  const entries = Object.entries(sessionVariables);
  if (!entries.length) return null;
  return (
    <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-200 bg-amber-50 px-3 py-1.5 text-xs">
      <VariableIcon className="size-4 shrink-0 text-amber-700" />
      <span className="shrink-0 font-medium text-amber-800">Session variables:</span>
      {entries.map(([k, v]) => (
        <span key={k} className="shrink-0 rounded bg-white px-1.5 py-0.5 font-mono" title={v}>
          {k}={v.length > 24 ? `${v.slice(0, 24)}…` : v}
        </span>
      ))}
      <Button size="sm" variant="ghost" className="ml-auto shrink-0" onClick={clearSessionVariables}>
        <Eraser className="size-3.5" /> Clear
      </Button>
    </div>
  );
}

export function WorkspacePage() {
  const [params, setParams] = useSearchParams();
  const collectionId = toId(params.get('collection'));
  const requestId = toId(params.get('request'));
  const { data: collection, isLoading, error } = useCollection(collectionId);
  const item = collection?.requests.find((r) => r.id === requestId);

  const select = (next: { collection?: number; request?: number }) => {
    const p = new URLSearchParams();
    if (next.collection) p.set('collection', String(next.collection));
    if (next.request) p.set('request', String(next.request));
    setParams(p);
  };

  let content;
  if (collectionId === null) {
    content = (
      <Empty title="Select a request or create a collection">
        <p className="max-w-md text-sm">
          Build requests, add assertions, chain values between requests with extractions, then run the whole
          collection from the Runner. Try the <b>Demo Store API (sample)</b> collection with the <b>Local demo</b>{' '}
          environment selected at the top right.
        </p>
      </Empty>
    );
  } else if (isLoading) {
    content = <Spinner />;
  } else if (error) {
    content = (
      <div className="p-4">
        <Alert>{error.message}</Alert>
      </div>
    );
  } else if (collection && requestId === null) {
    content = <CollectionSettings key={collection.id} collection={collection} />;
  } else if (item) {
    content = <RequestEditor key={item.id} item={item} />;
  } else {
    content = <Empty title="Request not found" />;
  }

  return (
    <div className="flex h-full">
      <CollectionSidebar
        selection={{ collectionId, requestId }}
        onSelectRequest={(c, r) => select({ collection: c, request: r })}
        onOpenSettings={(c) => select({ collection: c })}
        onDeselect={() => select({})}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <SessionVariablesBar />
        <div className="min-h-0 flex-1">{content}</div>
      </div>
    </div>
  );
}
