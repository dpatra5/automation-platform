import { useQueryClient } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { useEffect, useRef, useState, type SyntheticEvent } from 'react';

import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { onUnauthorized, tokenStore } from '@/lib/api';

/** Prompts for the API bearer token whenever the server responds 401. */
export function TokenPrompt() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const ref = useRef<HTMLDialogElement>(null);
  const qc = useQueryClient();

  useEffect(() => onUnauthorized(() => setOpen(true)), []);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const onSubmit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    tokenStore.set(value.trim());
    setValue('');
    setOpen(false);
    void qc.invalidateQueries();
  };

  return (
    <dialog
      ref={ref}
      onCancel={(e) => e.preventDefault()}
      aria-labelledby="token-title"
      className="m-auto w-full max-w-sm rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-slate-900/60 backdrop:backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
    >
      <form onSubmit={onSubmit} className="space-y-4 p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-brand-50 p-2 text-brand-600 dark:bg-brand-500/10">
            <KeyRound className="size-5" />
          </div>
          <div>
            <h2 id="token-title" className="text-base font-semibold">
              Authentication required
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Enter the API token configured via <code>LT_API_TOKEN</code>.
            </p>
          </div>
        </div>
        <Field label="API token" hint="Stored for this browser tab only.">
          <Input
            type="password"
            autoComplete="off"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" className="w-full" disabled={!value.trim()}>
          Continue
        </Button>
      </form>
    </dialog>
  );
}
