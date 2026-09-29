import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload } from 'lucide-react';
import { useState } from 'react';

import { keys } from '@/hooks/queries';
import { api } from '@/lib/api';
import type { ImportFormat, ImportOut } from '@/lib/types';
import { Alert, Button, Modal } from './ui';

const FORMATS: { id: ImportFormat; label: string }[] = [
  { id: 'auto', label: 'Auto-detect' },
  { id: 'curl', label: 'cURL command(s)' },
  { id: 'openapi', label: 'OpenAPI 3 / Swagger 2 (JSON or YAML)' },
  { id: 'postman', label: 'Postman collection v2.x' },
  { id: 'native', label: 'API Testing export' },
];

export function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: (id: number) => void }) {
  const client = useQueryClient();
  const [content, setContent] = useState('');
  const [format, setFormat] = useState<ImportFormat>('auto');
  const [name, setName] = useState('');
  const [done, setDone] = useState<ImportOut | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.importCollection({ content, format, ...(name.trim() ? { name: name.trim() } : {}) }),
    onSuccess: (out) => {
      void client.invalidateQueries({ queryKey: keys.collections });
      if (out.warnings.length) setDone(out);
      else {
        onImported(out.collection.id);
        onClose();
      }
    },
  });

  const loadFile = async (file: File | undefined) => {
    if (file) setContent(await file.text());
  };

  if (done) {
    return (
      <Modal
        title="Imported with warnings"
        onClose={onClose}
        footer={
          <Button
            variant="primary"
            onClick={() => {
              onImported(done.collection.id);
              onClose();
            }}
          >
            Open collection
          </Button>
        }
      >
        <p className="mb-2 text-sm">
          Created <b>{done.collection.name}</b> with {done.request_count} request(s) from {done.format}.
        </p>
        <Alert tone="warning">
          <ul className="list-disc pl-4">
            {done.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      </Modal>
    );
  }

  return (
    <Modal
      title="Import collection"
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!content.trim()} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Import
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Paste a cURL command, an OpenAPI/Swagger spec, a Postman collection, or a file exported from this tool.
          OpenAPI imports generate status and JSON Schema contract assertions from the spec.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="import-format">
              Format
            </label>
            <select
              id="import-format"
              className="input"
              value={format}
              onChange={(e) => setFormat(e.target.value as ImportFormat)}
            >
              {FORMATS.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="import-name">
              Collection name (optional)
            </label>
            <input id="import-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        </div>
        <textarea
          className="input min-h-64 font-mono text-xs"
          spellCheck={false}
          aria-label="Content to import"
          placeholder={"curl -X GET 'https://api.example.com/users' -H 'Accept: application/json'"}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-indigo-700 hover:underline">
          <Upload className="size-4" /> Load from file
          <input
            type="file"
            className="hidden"
            accept=".json,.yaml,.yml,.txt,.sh"
            onChange={(e) => void loadFile(e.target.files?.[0])}
          />
        </label>
        {mutation.error && <Alert>{mutation.error.message}</Alert>}
      </div>
    </Modal>
  );
}
