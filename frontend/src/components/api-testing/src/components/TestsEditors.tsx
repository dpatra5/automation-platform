import { Plus, Trash2, Wand2 } from 'lucide-react';

import { emptyAssertion, emptyExtraction, inferSchema, tryParseJson } from '@/lib/request';
import type { Assertion, AssertionSource, Extraction, ExtractionSource, Operator, ResponseData } from '@/lib/types';
import { Button, IconButton } from './ui';

const SOURCES: { id: AssertionSource; label: string }[] = [
  { id: 'status', label: 'Status code' },
  { id: 'response_time', label: 'Response time (ms)' },
  { id: 'json', label: 'JSON path' },
  { id: 'header', label: 'Header' },
  { id: 'body', label: 'Body text' },
  { id: 'json_schema', label: 'JSON Schema' },
];

const OPERATORS: { id: Operator; label: string }[] = [
  { id: 'equals', label: 'equals' },
  { id: 'not_equals', label: 'not equals' },
  { id: 'contains', label: 'contains' },
  { id: 'not_contains', label: 'not contains' },
  { id: 'exists', label: 'exists' },
  { id: 'not_exists', label: 'does not exist' },
  { id: 'lt', label: '<' },
  { id: 'lte', label: '<=' },
  { id: 'gt', label: '>' },
  { id: 'gte', label: '>=' },
  { id: 'matches', label: 'matches regex' },
  { id: 'type_is', label: 'type is' },
];

const NEEDS_PROPERTY: AssertionSource[] = ['json', 'header'];
const NO_EXPECTED: Operator[] = ['exists', 'not_exists'];

const PRESETS: { label: string; value: Partial<Assertion> }[] = [
  { label: 'Status 2xx', value: { source: 'status', operator: 'equals', expected: '2xx' } },
  { label: 'Time < 1000 ms', value: { source: 'response_time', operator: 'lt', expected: '1000' } },
  { label: 'JSON field exists', value: { source: 'json', property: '$.id', operator: 'exists', expected: '' } },
  {
    label: 'Content-Type is JSON',
    value: { source: 'header', property: 'content-type', operator: 'contains', expected: 'json' },
  },
];

function placeholderFor(a: Assertion): string {
  if (a.operator === 'type_is') return 'string | number | integer | boolean | array | object | null';
  if (a.source === 'status') return '200 or 2xx';
  if (a.operator === 'matches') return 'regular expression';
  return 'expected value (supports {{variables}})';
}

export function AssertionsEditor({
  rows,
  onChange,
  lastResponse,
}: {
  rows: Assertion[];
  onChange: (rows: Assertion[]) => void;
  lastResponse: ResponseData | null;
}) {
  const set = (i: number, patch: Partial<Assertion>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const parsed = lastResponse ? tryParseJson(lastResponse.body) : { ok: false as const };

  const addSchemaFromResponse = () => {
    if (!parsed.ok) return;
    const schema = JSON.stringify(inferSchema(parsed.value), null, 2);
    onChange([...rows, emptyAssertion({ source: 'json_schema', operator: 'equals', expected: schema })]);
  };

  return (
    <div className="space-y-3">
      {rows.length === 0 && <p className="text-sm text-slate-500">No assertions yet. Add one to turn this request into a test.</p>}
      {rows.map((a, i) => (
        <div key={i} className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-2.5"
            aria-label="Enabled"
            checked={a.enabled}
            onChange={(e) => set(i, { enabled: e.target.checked })}
          />
          <select
            className="input w-44! shrink-0"
            value={a.source}
            onChange={(e) => set(i, { source: e.target.value as AssertionSource })}
          >
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          {a.source === 'json_schema' ? (
            <textarea
              className="input min-h-28 font-mono text-xs"
              spellCheck={false}
              placeholder='{"type": "object", "required": ["id"]}'
              value={a.expected}
              onChange={(e) => set(i, { expected: e.target.value })}
            />
          ) : (
            <>
              {NEEDS_PROPERTY.includes(a.source) && (
                <input
                  className="input w-48! shrink-0 font-mono"
                  placeholder={a.source === 'json' ? '$.data.id' : 'Header name'}
                  value={a.property}
                  onChange={(e) => set(i, { property: e.target.value })}
                />
              )}
              <select
                className="input w-36! shrink-0"
                value={a.operator}
                onChange={(e) => set(i, { operator: e.target.value as Operator })}
              >
                {OPERATORS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
              {!NO_EXPECTED.includes(a.operator) && (
                <input
                  className="input font-mono"
                  placeholder={placeholderFor(a)}
                  value={a.expected}
                  onChange={(e) => set(i, { expected: e.target.value })}
                />
              )}
            </>
          )}
          <IconButton label="Remove assertion" className="mt-1" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            <Trash2 className="size-4" />
          </IconButton>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" onClick={() => onChange([...rows, emptyAssertion()])}>
          <Plus className="size-3.5" /> Add assertion
        </Button>
        {PRESETS.map((p) => (
          <Button key={p.label} size="sm" variant="ghost" onClick={() => onChange([...rows, emptyAssertion(p.value)])}>
            + {p.label}
          </Button>
        ))}
        <Button
          size="sm"
          variant="ghost"
          disabled={!parsed.ok}
          title={parsed.ok ? 'Infer a JSON Schema from the last response' : 'Send the request first to get a JSON response'}
          onClick={addSchemaFromResponse}
        >
          <Wand2 className="size-3.5" /> Schema from last response
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        JSON paths look like <code>$.items[0].id</code>; <code>.length</code> gives array size. Numbers, booleans
        and <code>null</code> are compared as JSON.
      </p>
    </div>
  );
}

const EXTRACT_SOURCES: { id: ExtractionSource; label: string; placeholder: string }[] = [
  { id: 'json', label: 'JSON path', placeholder: '$.token' },
  { id: 'header', label: 'Header', placeholder: 'Location' },
  { id: 'regex', label: 'Regex on body', placeholder: 'id=(\\d+)' },
  { id: 'status', label: 'Status code', placeholder: '' },
];

export function ExtractionsEditor({ rows, onChange }: { rows: Extraction[]; onChange: (rows: Extraction[]) => void }) {
  const set = (i: number, patch: Partial<Extraction>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-500">
        Capture values from the response into variables. They are available as <code>{'{{name}}'}</code> in the
        following requests of a run, and in later sends from this workspace (session variables).
      </p>
      {rows.map((e, i) => {
        const source = EXTRACT_SOURCES.find((s) => s.id === e.source);
        return (
          <div key={i} className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label="Enabled"
              checked={e.enabled}
              onChange={(ev) => set(i, { enabled: ev.target.checked })}
            />
            <input
              className="input w-44! font-mono"
              placeholder="variable name"
              value={e.variable}
              onChange={(ev) => set(i, { variable: ev.target.value })}
            />
            <span className="text-sm text-slate-400">←</span>
            <select
              className="input w-40!"
              value={e.source}
              onChange={(ev) => set(i, { source: ev.target.value as ExtractionSource })}
            >
              {EXTRACT_SOURCES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            {e.source !== 'status' && (
              <input
                className="input font-mono"
                placeholder={source?.placeholder}
                value={e.property}
                onChange={(ev) => set(i, { property: ev.target.value })}
              />
            )}
            <IconButton label="Remove extraction" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
              <Trash2 className="size-4" />
            </IconButton>
          </div>
        );
      })}
      <Button size="sm" onClick={() => onChange([...rows, emptyExtraction()])}>
        <Plus className="size-3.5" /> Add extraction
      </Button>
    </div>
  );
}
