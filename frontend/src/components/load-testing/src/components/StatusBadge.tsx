import { Badge, type Tone } from '@/components/ui/Badge';
import type { RunStatus, ScanItemStatus, ScanStatus } from '@/lib/types';

const statusTone: Record<RunStatus, Tone> = {
  running: 'brand',
  stopping: 'warning',
  completed: 'success',
  interrupted: 'warning',
  failed: 'danger',
};

const statusLabel: Record<RunStatus, string> = {
  running: 'Running',
  stopping: 'Stopping',
  completed: 'Completed',
  interrupted: 'Interrupted',
  failed: 'Failed',
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const live = status === 'running' || status === 'stopping';
  return (
    <Badge tone={statusTone[status]} dot pulse={live}>
      {statusLabel[status]}
    </Badge>
  );
}

export function VerdictBadge({
  pass,
  na = 'n/a',
}: {
  pass: boolean | null | undefined;
  na?: string;
}) {
  if (pass === true) return <Badge tone="success">Pass</Badge>;
  if (pass === false) return <Badge tone="danger">Fail</Badge>;
  return <Badge tone="neutral">{na}</Badge>;
}

const scanTone: Record<ScanStatus | ScanItemStatus, Tone> = {
  discovering: 'brand',
  discovered: 'info',
  running: 'brand',
  completed: 'success',
  cancelled: 'neutral',
  failed: 'danger',
  pending: 'neutral',
  interrupted: 'warning',
  skipped: 'warning',
};

export function ScanStatusBadge({ status }: { status: ScanStatus | ScanItemStatus }) {
  const live = status === 'discovering' || status === 'running';
  return (
    <Badge tone={scanTone[status]} dot pulse={live}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}
