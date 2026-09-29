import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface StatProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: 'default' | 'success' | 'warning' | 'danger';
  className?: string;
}

const toneText = {
  default: 'text-slate-900 dark:text-slate-50',
  success: 'text-emerald-600 dark:text-emerald-400',
  warning: 'text-amber-600 dark:text-amber-400',
  danger: 'text-rose-600 dark:text-rose-400',
};

export function Stat({ label, value, sub, icon, tone = 'default', className }: StatProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-slate-200 bg-white px-4 py-3.5 shadow-xs dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">
        <span className="truncate">{label}</span>
        {icon && <span className="text-slate-400 dark:text-slate-500">{icon}</span>}
      </div>
      <div className={cn('mt-1.5 text-2xl font-semibold tabular-nums', toneText[tone])}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
    </div>
  );
}
