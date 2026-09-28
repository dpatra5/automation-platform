import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Braces, Save, Send, Terminal } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { keys } from '@/hooks/queries';
import { useWorkspace } from '@/hooks/workspace';
import { api } from '@/lib/api';
import { specOf, toCurl } from '@/lib/request';
import { METHODS, type AuthType, type BodyMode, type ExecutionResult, type Method, type RequestItem } from '@/lib/types';
import { KeyValueEditor } from './KeyValueEditor';
import { ResponseViewer } from './ResponseViewer';
import { AssertionsEditor, ExtractionsEditor } from './TestsEditors';
import { Alert, Button, Tabs } from './ui';

type Tab = 'params' | 'headers' | 'body' | 'auth' | 'tests' | 'extract' | 'settings';

const BODY_MODES: { id: BodyMode; label: string }[] = [
  { id: 'none', label: 'None' },
  { id: 'json', label: 'JSON' },
  { id: 'text', label: 'Text' },
  { id: 'xml', label: 'XML' },
  { id: 'form', label: 'Form URL-encoded' },
];

export function RequestEditor({ item }: { item: RequestItem }) {
  const client = useQueryClient();
  const { environmentId, sessionVariables, mergeSessionVariables } = useWorkspace();
  const [draft, setDraft] = useState<RequestItem>(item);
  const [saved, setSaved] = useState<RequestItem>(item);
  const [tab, setTab] = useState<Tab>('params');
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const patch = (p: Partial<RequestItem>) => setDraft((d) => ({ ...d, ...p }));

  const save = useMutation({
    mutationFn: () => api.updateRequest(draft.id, draft),
    onSuccess: (updated) => {
      setDraft(updated);
      setSaved(updated);
      void client.invalidateQueries({ queryKey: keys.collection(updated.collection_id) });
    },
  });

  const execute = useMutation({
    mutationFn: () =>
      api.execute({
        request: specOf(draft),
        collection_id: draft.collection_id,
        environment_id: environmentId,
        variables: sessionVariables,
      }),
    onSuccess: (res) => {
      setResult(res);
      if (Object.keys(res.extracted).length) mergeSessionVariables(res.extracted);
    },
  });

  const saveNow = useCallback(() => {
    if (dirty && !save.isPending) save.mutate();
  }, [dirty, save]);
  const sendNow = useCallback(() => {
    if (!execute.isPending) execute.mutate();
  }, [execute]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === 's') {
        e.preventDefault();
        saveNow();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        sendNow();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [saveNow, sendNow]);

  const copyCurl = () => {
    void navigator.clipboard.writeText(toCurl(draft)).then(() => {
      setNotice('cURL command copied to clipboard');
      setTimeout(() => setNotice(null), 1500);
    });
  };

  const formatJson = () => {
    try {
      patch({ body: { ...draft.body, content: JSON.stringify(JSON.parse(draft.body.content), null, 2) } });
    } catch {
      setNotice('Body is not valid JSON (placeholders like {{id}} must be inside quotes to format)');
      setTimeout(() => setNotice(null), 2500);
    }
  };

  const enabledCount = (rows: { enabled: boolean; key?: string }[]) => rows.filter((r) => r.enabled).length;
  const auth = draft.auth;

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-2 border-b border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2">
          <input
            className="input border-transparent! px-1! text-base font-semibold shadow-none hover:border-slate-300!"
            value={draft.name}
            aria-label="Request name"
            onChange={(e) => patch({ name: e.target.value })}
          />
          {dirty && <span className="text-xs whitespace-nowrap text-amber-600">Unsaved changes</span>}
          <Button size="sm" variant="ghost" onClick={copyCurl} title="Copy as cURL">
            <Terminal className="size-3.5" /> cURL
          </Button>
          <Button size="sm" onClick={saveNow} disabled={!dirty || !draft.name.trim()} loading={save.isPending}>
            <Save className="size-3.5" /> Save
          </Button>
        </div>
        <div className="flex gap-2">
          <select
            className="input w-28! font-mono font-semibold"
            value={draft.method}
            aria-label="Method"
            onChange={(e) => patch({ method: e.target.value as Method })}
          >
            {METHODS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
          <input
            className="input font-mono"
            placeholder="{{baseUrl}}/path"
            aria-label="URL"
            value={draft.url}
            onChange={(e) => patch({ url: e.target.value })}
          />
          <Button variant="primary" onClick={sendNow} loading={execute.isPending} title="Send (Ctrl+Enter)">
            <Send className="size-4" /> Send
          </Button>
        </div>
        {save.error && <Alert>Save failed: {save.error.message}</Alert>}
        {execute.error && <Alert>Send failed: {execute.error.message}</Alert>}
        {notice && <Alert tone="info">{notice}</Alert>}
      </div>

      <div className="flex min-h-0 flex-col bg-white">
        <div className="px-3">
          <Tabs<Tab>
            active={tab}
            onChange={setTab}
            tabs={[
              { id: 'params', label: 'Params', count: enabledCount(draft.params) },
              { id: 'headers', label: 'Headers', count: enabledCount(draft.headers) },
              { id: 'body', label: 'Body' },
              { id: 'auth', label: 'Auth' },
              { id: 'tests', label: 'Assertions', count: enabledCount(draft.assertions) },
              { id: 'extract', label: 'Extract', count: enabledCount(draft.extractions) },
              { id: 'settings', label: 'Settings' },
            ]}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          {tab === 'params' && (
            <KeyValueEditor rows={draft.params} onChange={(params) => patch({ params })} keyPlaceholder="Query parameter" />
          )}
          {tab === 'headers' && (
            <KeyValueEditor rows={draft.headers} onChange={(headers) => patch({ headers })} keyPlaceholder="Header" />
          )}
          {tab === 'body' && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                {BODY_MODES.map((m) => (
                  <label key={m.id} className="flex items-center gap-1">
                    <input
                      type="radio"
                      name="body-mode"
                      checked={draft.body.mode === m.id}
                      onChange={() => patch({ body: { ...draft.body, mode: m.id } })}
                    />
                    {m.label}
                  </label>
                ))}
                {draft.body.mode === 'json' && (
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={formatJson}>
                    <Braces className="size-3.5" /> Format
                  </Button>
                )}
              </div>
              {draft.body.mode === 'form' ? (
                <KeyValueEditor
                  rows={draft.body.form}
                  onChange={(form) => patch({ body: { ...draft.body, form } })}
                  keyPlaceholder="Field"
                />
              ) : draft.body.mode !== 'none' ? (
                <textarea
                  className="input min-h-48 font-mono text-xs"
                  spellCheck={false}
                  aria-label="Request body"
                  value={draft.body.content}
                  onChange={(e) => patch({ body: { ...draft.body, content: e.target.value } })}
                />
              ) : (
                <p className="text-sm text-slate-500">This request has no body.</p>
              )}
            </div>
          )}
          {tab === 'auth' && (
            <div className="max-w-xl space-y-3">
              <div>
                <label className="label" htmlFor="auth-type">
                  Type
                </label>
                <select
                  id="auth-type"
                  className="input"
                  value={auth.type}
                  onChange={(e) => patch({ auth: { ...auth, type: e.target.value as AuthType } })}
                >
                  <option value="none">No auth</option>
                  <option value="bearer">Bearer token</option>
                  <option value="basic">Basic auth</option>
                  <option value="api_key">API key</option>
                </select>
              </div>
              {auth.type === 'bearer' && (
                <Field label="Token" value={auth.token} onChange={(token) => patch({ auth: { ...auth, token } })} />
              )}
              {auth.type === 'basic' && (
                <>
                  <Field label="Username" value={auth.username} onChange={(username) => patch({ auth: { ...auth, username } })} />
                  <Field
                    label="Password"
                    value={auth.password}
                    secret
                    onChange={(password) => patch({ auth: { ...auth, password } })}
                  />
                </>
              )}
              {auth.type === 'api_key' && (
                <>
                  <Field label="Key name" value={auth.key} onChange={(key) => patch({ auth: { ...auth, key } })} />
                  <Field label="Value" value={auth.value} onChange={(value) => patch({ auth: { ...auth, value } })} />
                  <div>
                    <label className="label" htmlFor="auth-location">
                      Add to
                    </label>
                    <select
                      id="auth-location"
                      className="input"
                      value={auth.location}
                      onChange={(e) => patch({ auth: { ...auth, location: e.target.value as 'header' | 'query' } })}
                    >
                      <option value="header">Header</option>
                      <option value="query">Query parameter</option>
                    </select>
                  </div>
                </>
              )}
              <p className="text-xs text-slate-500">
                Tip: reference variables like <code>{'{{token}}'}</code> and mark the value as secret in the environment.
              </p>
            </div>
          )}
          {tab === 'tests' && (
            <AssertionsEditor
              rows={draft.assertions}
              onChange={(assertions) => patch({ assertions })}
              lastResponse={result?.response ?? null}
            />
          )}
          {tab === 'extract' && (
            <ExtractionsEditor rows={draft.extractions} onChange={(extractions) => patch({ extractions })} />
          )}
          {tab === 'settings' && (
            <div className="max-w-xl space-y-3 text-sm">
              <div>
                <label className="label" htmlFor="timeout">
                  Timeout (ms)
                </label>
                <input
                  id="timeout"
                  type="number"
                  min={100}
                  max={300000}
                  className="input"
                  value={draft.settings.timeout_ms}
                  onChange={(e) => patch({ settings: { ...draft.settings, timeout_ms: Number(e.target.value) } })}
                />
              </div>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={draft.settings.follow_redirects}
                  onChange={(e) => patch({ settings: { ...draft.settings, follow_redirects: e.target.checked } })}
                />
                Follow redirects
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={draft.settings.verify_tls}
                  onChange={(e) => patch({ settings: { ...draft.settings, verify_tls: e.target.checked } })}
                />
                Verify TLS certificates
              </label>
              <div>
                <label className="label" htmlFor="description">
                  Description
                </label>
                <textarea
                  id="description"
                  className="input min-h-24"
                  value={draft.description}
                  onChange={(e) => patch({ description: e.target.value })}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="min-h-0 border-t border-slate-200 bg-white">
        <ResponseViewer result={result} loading={execute.isPending} />
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  secret = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  secret?: boolean;
}) {
  const id = `field-${label.toLowerCase().replace(/\s+/g, '-')}`;
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="input font-mono"
        type={secret ? 'password' : 'text'}
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
