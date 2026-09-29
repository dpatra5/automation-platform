import { Eye, EyeOff, Lock, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { emptyKv, emptyVariable } from '@/lib/request';
import type { KeyValue, Variable } from '@/lib/types';
import { IconButton } from './ui';

function update<T>(rows: T[], index: number, patch: Partial<T>): T[] {
  return rows.map((row, i) => (i === index ? { ...row, ...patch } : row));
}

/** Editable key/value table that always keeps one blank row at the end for quick entry. */
export function KeyValueEditor({
  rows,
  onChange,
  keyPlaceholder = 'Key',
  valuePlaceholder = 'Value',
}: {
  rows: KeyValue[];
  onChange: (rows: KeyValue[]) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}) {
  const display = [...rows, emptyKv()];
  const set = (index: number, patch: Partial<KeyValue>) => {
    const next = index === rows.length ? [...rows, { ...emptyKv(), ...patch }] : update(rows, index, patch);
    onChange(next);
  };

  return (
    <table className="w-full text-sm">
      <tbody>
        {display.map((row, i) => {
          const placeholder = i === rows.length;
          return (
            <tr key={i} className="group">
              <td className="w-8 py-1 pr-1">
                {!placeholder && (
                  <input
                    type="checkbox"
                    aria-label="Enabled"
                    checked={row.enabled}
                    onChange={(e) => set(i, { enabled: e.target.checked })}
                  />
                )}
              </td>
              <td className="w-2/5 py-1 pr-2">
                <input
                  className="input font-mono"
                  placeholder={keyPlaceholder}
                  value={row.key}
                  onChange={(e) => set(i, { key: e.target.value })}
                />
              </td>
              <td className="py-1 pr-2">
                <input
                  className="input font-mono"
                  placeholder={valuePlaceholder}
                  value={row.value}
                  onChange={(e) => set(i, { value: e.target.value })}
                />
              </td>
              <td className="w-8 py-1">
                {!placeholder && (
                  <IconButton label="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </IconButton>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function VariablesEditor({ rows, onChange }: { rows: Variable[]; onChange: (rows: Variable[]) => void }) {
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const display = [...rows, emptyVariable()];
  const set = (index: number, patch: Partial<Variable>) => {
    onChange(index === rows.length ? [...rows, { ...emptyVariable(), ...patch }] : update(rows, index, patch));
  };
  const toggleReveal = (i: number) =>
    setRevealed((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-slate-500 uppercase">
          <th className="w-8" />
          <th className="pb-1 font-medium">Variable</th>
          <th className="pb-1 font-medium">Value</th>
          <th className="w-20 pb-1 text-center font-medium">Secret</th>
          <th className="w-8" />
        </tr>
      </thead>
      <tbody>
        {display.map((row, i) => {
          const placeholder = i === rows.length;
          const hidden = row.secret && !revealed.has(i);
          return (
            <tr key={i}>
              <td className="py-1 pr-1">
                {!placeholder && (
                  <input
                    type="checkbox"
                    aria-label="Enabled"
                    checked={row.enabled}
                    onChange={(e) => set(i, { enabled: e.target.checked })}
                  />
                )}
              </td>
              <td className="w-2/5 py-1 pr-2">
                <input
                  className="input font-mono"
                  placeholder="name"
                  value={row.key}
                  onChange={(e) => set(i, { key: e.target.value })}
                />
              </td>
              <td className="py-1 pr-2">
                <div className="flex items-center gap-1">
                  <input
                    className="input font-mono"
                    placeholder="value"
                    type={hidden ? 'password' : 'text'}
                    autoComplete="off"
                    value={row.value}
                    onChange={(e) => set(i, { value: e.target.value })}
                  />
                  {row.secret && (
                    <IconButton label={hidden ? 'Show value' : 'Hide value'} onClick={() => toggleReveal(i)}>
                      {hidden ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
                    </IconButton>
                  )}
                </div>
              </td>
              <td className="py-1 text-center">
                {!placeholder && (
                  <IconButton
                    label={row.secret ? 'Secret: masked in reports and exports' : 'Mark as secret'}
                    className={row.secret ? 'text-amber-600!' : ''}
                    onClick={() => set(i, { secret: !row.secret })}
                  >
                    <Lock className="size-4" />
                  </IconButton>
                )}
              </td>
              <td className="py-1">
                {!placeholder && (
                  <IconButton label="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </IconButton>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
