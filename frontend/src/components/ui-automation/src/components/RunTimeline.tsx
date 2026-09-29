import React from 'react';
import { Step, StepResult } from '../api/types';
import { CheckCircle2, XCircle, AlertCircle, Clock, Loader2 } from 'lucide-react';
import { formatDuration } from '../utils/formatters';
import { humanizeAction } from '../utils/constants';
import { ActionIcon } from './StepEditor';

interface Props {
  results: StepResult[];
  /** The test case's steps, so each result can be labelled with what it did. */
  steps?: Step[];
  isRunning?: boolean;
  onImageClick?: (path: string) => void;
}

const MARKS = {
  passed: { Icon: CheckCircle2, color: 'text-mint-500', ring: 'bg-mint-50 border-mint-100' },
  failed: { Icon: XCircle, color: 'text-rose-500', ring: 'bg-rose-50 border-rose-100' },
  error: { Icon: AlertCircle, color: 'text-amber-500', ring: 'bg-amber-50 border-amber-100' },
  running: { Icon: Loader2, color: 'text-sky-500', ring: 'bg-sky-50 border-sky-100' },
  pending: { Icon: Clock, color: 'text-ink-muted', ring: 'bg-canvas border-line' },
};

export const RunTimeline = ({ results, steps = [], isRunning, onImageClick }: Props) => {
  const byId = new Map(steps.map(s => [s.id, s]));
  const remaining = steps.length - results.length;

  if (results.length === 0 && !isRunning) {
    return <p className="text-sm text-ink-muted">No steps were executed.</p>;
  }

  return (
    <ol className="relative space-y-3">
      {results.map((result, index) => {
        const mark = MARKS[result.status] || MARKS.pending;
        const step = byId.get(result.step_id);

        return (
          <li key={result.id} className="flex gap-3">
            <div className={`w-8 h-8 shrink-0 rounded-lg border grid place-items-center ${mark.ring}`}>
              <mark.Icon className={`w-4 h-4 ${mark.color} ${result.status === 'running' ? 'animate-spin' : ''}`} />
            </div>

            <div className="card flex-1 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono text-ink-muted">{index + 1}</span>
                    {step ? (
                      <>
                        <ActionIcon action={step.action} className="w-3.5 h-3.5 text-primary-500" />
                        <span className="text-sm font-semibold text-ink capitalize">
                          {humanizeAction(step.action)}
                        </span>
                        {step.selector && (
                          <span className="mono-chip truncate max-w-[260px]" title={step.selector}>
                            {step.selector}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-sm font-semibold text-ink">Step {index + 1}</span>
                    )}
                  </div>
                  {step?.value && (
                    <div className="text-xs text-ink-muted mt-1 truncate">"{step.value}"</div>
                  )}
                </div>
                <span className="text-xs font-mono text-ink-muted shrink-0">
                  {formatDuration(result.duration_ms)}
                </span>
              </div>

              {result.error_message && (
                <pre className="mt-3 text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-xl p-3 font-mono whitespace-pre-wrap overflow-x-auto">
                  {result.error_message}
                </pre>
              )}

              {result.screenshot_path && (
                <button
                  type="button"
                  onClick={() => onImageClick?.(result.screenshot_path!)}
                  className="mt-3 block w-full rounded-xl overflow-hidden border border-line group"
                >
                  <img
                    src={`/${result.screenshot_path}`}
                    alt={`Screenshot after step ${index + 1}`}
                    loading="lazy"
                    className="w-full h-32 object-cover object-top transition-transform group-hover:scale-[1.02]"
                  />
                </button>
              )}
            </div>
          </li>
        );
      })}

      {isRunning && (
        <li className="flex gap-3">
          <div className="w-8 h-8 shrink-0 rounded-lg border bg-sky-50 border-sky-100 grid place-items-center">
            <Loader2 className="w-4 h-4 text-sky-500 animate-spin" />
          </div>
          <div className="card flex-1 p-4 text-sm text-ink-muted">
            Running in Chrome…
            {remaining > 0 && ` ${remaining} step${remaining === 1 ? '' : 's'} to go.`}
          </div>
        </li>
      )}
    </ol>
  );
};
