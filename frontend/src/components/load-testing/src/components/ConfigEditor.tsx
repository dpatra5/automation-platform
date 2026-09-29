import { useRef, type KeyboardEvent } from 'react';

import { cn } from '@/lib/cn';

interface ConfigEditorProps {
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
  id?: string;
  className?: string;
}

const INDENT = '  ';

/** Lightweight YAML editor: monospace, line numbers, and Tab/Shift-Tab indentation. */
export function ConfigEditor({ value, onChange, invalid, id, className }: ConfigEditorProps) {
  const gutter = useRef<HTMLDivElement>(null);
  const lines = value.split('\n').length;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Tab') return;
    e.preventDefault();
    const el = e.currentTarget;
    const { selectionStart: start, selectionEnd: end } = el;
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    if (e.shiftKey) {
      const removed = value.startsWith(INDENT, lineStart) ? INDENT.length : 0;
      if (!removed) return;
      onChange(value.slice(0, lineStart) + value.slice(lineStart + removed));
      requestAnimationFrame(() => el.setSelectionRange(start - removed, end - removed));
    } else {
      onChange(value.slice(0, start) + INDENT + value.slice(end));
      requestAnimationFrame(() =>
        el.setSelectionRange(start + INDENT.length, start + INDENT.length),
      );
    }
  };

  return (
    <div
      className={cn(
        'flex overflow-hidden rounded-lg bg-slate-950 font-mono text-[13px] leading-5 ring-1 ring-slate-800 focus-within:ring-2 focus-within:ring-brand-500',
        invalid && 'ring-rose-500',
        className,
      )}
    >
      <div
        ref={gutter}
        aria-hidden
        className="overflow-hidden border-r border-slate-800 bg-slate-900/60 px-3 py-3 text-right text-slate-600 select-none"
      >
        {Array.from({ length: lines }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onScroll={(e) => {
          if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop;
        }}
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        autoCorrect="off"
        aria-label="Load profile YAML"
        aria-invalid={invalid || undefined}
        wrap="off"
        className="min-h-0 flex-1 resize-none bg-transparent px-3 py-3 text-slate-100 caret-brand-500 outline-none placeholder:text-slate-600"
        placeholder="version: 1&#10;base_url: http://127.0.0.1:8080&#10;…"
      />
    </div>
  );
}
