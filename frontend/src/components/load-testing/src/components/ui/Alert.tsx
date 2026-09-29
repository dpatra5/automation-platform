import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

type AlertTone = 'info' | 'success' | 'warning' | 'danger';

const styles: Record<AlertTone, { box: string; icon: ReactNode }> = {
  info: {
    box: 'bg-sky-50 text-sky-800 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-200',
    icon: <Info className="size-4" />,
  },
  success: {
    box: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-200',
    icon: <CheckCircle2 className="size-4" />,
  },
  warning: {
    box: 'bg-amber-50 text-amber-900 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-200',
    icon: <AlertTriangle className="size-4" />,
  },
  danger: {
    box: 'bg-rose-50 text-rose-800 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-200',
    icon: <XCircle className="size-4" />,
  },
};

interface AlertProps {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Alert({ tone = 'info', title, children, className, action }: AlertProps) {
  const s = styles[tone];
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={cn('flex gap-3 rounded-lg px-4 py-3 text-sm ring-1 ring-inset', s.box, className)}
    >
      <span className="mt-0.5 shrink-0">{s.icon}</span>
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="break-words whitespace-pre-wrap opacity-90">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function ErrorAlert({
  error,
  title = 'Something went wrong',
}: {
  error: unknown;
  title?: string;
}) {
  if (!error) return null;
  const message =
    error instanceof Error ? error.message : typeof error === 'string' ? error : 'Unexpected error';
  return (
    <Alert tone="danger" title={title}>
      {message}
    </Alert>
  );
}
