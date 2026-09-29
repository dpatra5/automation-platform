import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Copy, Download, FilePlus2, Play, Plus, Settings2, Trash2, Upload } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { keys, useCollection, useCollections } from '@/hooks/queries';
import { api } from '@/lib/api';
import { newRequestSpec } from '@/lib/request';
import type { CollectionSummary } from '@/lib/types';
import { ImportDialog } from './ImportDialog';
import { Alert, Button, IconButton, MethodBadge, Spinner } from './ui';

interface Selection {
  collectionId: number | null;
  requestId: number | null;
}

export function CollectionSidebar({
  selection,
  onSelectRequest,
  onOpenSettings,
  onDeselect,
}: {
  selection: Selection;
  onSelectRequest: (collectionId: number, requestId: number) => void;
  onOpenSettings: (collectionId: number) => void;
  onDeselect: () => void;
}) {
  const client = useQueryClient();
  const { data: collections, isLoading, error } = useCollections();
  const [importing, setImporting] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(
    () => new Set(selection.collectionId ? [selection.collectionId] : []),
  );

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const create = useMutation({
    mutationFn: () => api.createCollection({ name: 'New collection', description: '', variables: [] }),
    onSuccess: (c) => {
      void client.invalidateQueries({ queryKey: keys.collections });
      setExpanded((prev) => new Set(prev).add(c.id));
      onOpenSettings(c.id);
    },
  });

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-1 border-b border-slate-200 px-3 py-2">
        <span className="text-sm font-semibold">Collections</span>
        <div className="ml-auto flex gap-1">
          <IconButton label="Import (cURL, OpenAPI, Postman)" onClick={() => setImporting(true)}>
            <Upload className="size-4" />
          </IconButton>
          <IconButton label="New collection" onClick={() => create.mutate()} disabled={create.isPending}>
            <Plus className="size-4" />
          </IconButton>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {isLoading && <Spinner />}
        {error && (
          <div className="p-3">
            <Alert>{error.message}</Alert>
          </div>
        )}
        {collections?.length === 0 && (
          <div className="space-y-2 p-4 text-sm text-slate-500">
            <p>No collections yet.</p>
            <Button size="sm" onClick={() => setImporting(true)}>
              <Upload className="size-3.5" /> Import an API
            </Button>
          </div>
        )}
        {collections?.map((c) => (
          <CollectionNode
            key={c.id}
            collection={c}
            open={expanded.has(c.id)}
            selection={selection}
            onToggle={() => toggle(c.id)}
            onSelectRequest={onSelectRequest}
            onOpenSettings={onOpenSettings}
            onDeleted={onDeselect}
          />
        ))}
      </div>
      {importing && (
        <ImportDialog
          onClose={() => setImporting(false)}
          onImported={(id) => {
            setExpanded((prev) => new Set(prev).add(id));
            onOpenSettings(id);
          }}
        />
      )}
    </aside>
  );
}

function CollectionNode({
  collection,
  open,
  selection,
  onToggle,
  onSelectRequest,
  onOpenSettings,
  onDeleted,
}: {
  collection: CollectionSummary;
  open: boolean;
  selection: Selection;
  onToggle: () => void;
  onSelectRequest: (collectionId: number, requestId: number) => void;
  onOpenSettings: (collectionId: number) => void;
  onDeleted: () => void;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: detail } = useCollection(open ? collection.id : null);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.collections });
    void client.invalidateQueries({ queryKey: keys.collection(collection.id) });
  };

  const addRequest = useMutation({
    mutationFn: () => api.createRequest(collection.id, { name: 'New request', ...newRequestSpec() }),
    onSuccess: (r) => {
      refresh();
      onSelectRequest(collection.id, r.id);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteCollection(collection.id),
    onSuccess: () => {
      if (selection.collectionId === collection.id) onDeleted();
      void client.invalidateQueries({ queryKey: keys.collections });
    },
  });
  const duplicate = useMutation({
    mutationFn: (id: number) => api.duplicateRequest(id),
    onSuccess: (r) => {
      refresh();
      onSelectRequest(collection.id, r.id);
    },
  });
  const removeRequest = useMutation({
    mutationFn: (id: number) => api.deleteRequest(id),
    onSuccess: (_, id) => {
      refresh();
      if (selection.requestId === id) onDeleted();
    },
  });

  const confirmDelete = () => {
    if (window.confirm(`Delete collection "${collection.name}" and its ${collection.request_count} request(s)?`))
      remove.mutate();
  };

  return (
    <div>
      <div
        className={`group flex items-center gap-1 px-2 py-1 text-sm hover:bg-slate-50 ${
          selection.collectionId === collection.id && selection.requestId === null ? 'bg-indigo-50' : ''
        }`}
      >
        <button type="button" className="flex min-w-0 flex-1 items-center gap-1 text-left" onClick={onToggle}>
          {open ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
          <span className="truncate font-medium">{collection.name}</span>
          <span className="text-xs text-slate-400">{collection.request_count}</span>
        </button>
        <div className="hidden gap-0.5 group-hover:flex">
          <IconButton label="Add request" onClick={() => addRequest.mutate()}>
            <FilePlus2 className="size-3.5" />
          </IconButton>
          <IconButton label="Run collection" onClick={() => navigate(`/runner?collection=${collection.id}`)}>
            <Play className="size-3.5" />
          </IconButton>
          <IconButton label="Collection settings & variables" onClick={() => onOpenSettings(collection.id)}>
            <Settings2 className="size-3.5" />
          </IconButton>
          <IconButton label="Export" onClick={() => void api.exportCollection(collection.id)}>
            <Download className="size-3.5" />
          </IconButton>
          <IconButton label="Delete collection" onClick={confirmDelete}>
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </div>
      {open && (
        <div className="pb-1">
          {detail?.requests.length === 0 && (
            <button
              type="button"
              className="ml-7 py-1 text-xs text-indigo-700 hover:underline"
              onClick={() => addRequest.mutate()}
            >
              + Add first request
            </button>
          )}
          {detail?.requests.map((r) => (
            <div
              key={r.id}
              className={`group flex items-center gap-2 py-1 pr-2 pl-7 text-sm hover:bg-slate-50 ${
                selection.requestId === r.id ? 'bg-indigo-50' : ''
              }`}
            >
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => onSelectRequest(collection.id, r.id)}
              >
                <MethodBadge method={r.method} className="w-9 shrink-0" />
                <span className="truncate">{r.name}</span>
              </button>
              <div className="hidden gap-0.5 group-hover:flex">
                <IconButton label="Duplicate" onClick={() => duplicate.mutate(r.id)}>
                  <Copy className="size-3.5" />
                </IconButton>
                <IconButton
                  label="Delete request"
                  onClick={() => window.confirm(`Delete "${r.name}"?`) && removeRequest.mutate(r.id)}
                >
                  <Trash2 className="size-3.5" />
                </IconButton>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
