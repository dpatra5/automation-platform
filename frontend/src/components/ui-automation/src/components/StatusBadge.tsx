import React from 'react';
import { RunStatus } from '../api/types';
import { RUN_STATUS_COLORS } from '../utils/constants';
import { CheckCircle2, XCircle, AlertCircle, Clock, Loader2 } from 'lucide-react';

interface Props {
  status?: RunStatus;
  className?: string;
}

const ICONS = {
  pending: Clock,
  running: Loader2,
  passed: CheckCircle2,
  failed: XCircle,
  error: AlertCircle,
};

export const StatusBadge = ({ status = 'pending', className = '' }: Props) => {
  const colorClass = RUN_STATUS_COLORS[status] || RUN_STATUS_COLORS.pending;
  const Icon = ICONS[status] || Clock;

  return (
    <span className={`chip ${colorClass} ${className}`}>
      <Icon className={`w-3.5 h-3.5 ${status === 'running' ? 'animate-spin' : ''}`} />
      <span className="capitalize">{status}</span>
    </span>
  );
};
