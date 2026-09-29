import { Loader2, CheckCircle2, XCircle, Clock, Camera } from 'lucide-react'
import type { SprintGuardExecutionResult } from '../models/rewindExecution.types'

interface ExecutionResultsProps {
  result: SprintGuardExecutionResult | null
  isBusy: boolean
}

const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-slate-50 text-slate-700 border-slate-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  passed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
  cancelled: 'bg-amber-50 text-amber-700 border-amber-200',
}

export function ExecutionResults({ result, isBusy }: ExecutionResultsProps) {
  if (!result && !isBusy) return null
  const status = result?.status ?? 'queued'
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Rewind Execution</h3>
        <span
          className={`ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${STATUS_STYLES[status]}`}
        >
          {status === 'running' || status === 'queued' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : status === 'passed' ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : (
            <XCircle className="w-3.5 h-3.5" />
          )}
          {status}
        </span>
      </div>
      <div className="p-6 space-y-4 text-sm text-slate-700">
        {result?.durationMs != null && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Clock className="w-3.5 h-3.5" />
            <span>{result.durationMs}ms</span>
          </div>
        )}
        {result?.logs && result.logs.length > 0 && (
          <div>
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Logs
            </div>
            <pre className="text-xs bg-slate-50 border border-slate-100 rounded-lg p-3 overflow-auto max-h-56">
              {result.logs.join('\n')}
            </pre>
          </div>
        )}
        {result?.screenshots && result.screenshots.length > 0 && (
          <div>
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
              <Camera className="w-3.5 h-3.5" /> Screenshots
            </div>
            <ul className="text-xs text-slate-600 list-disc pl-5 space-y-0.5">
              {result.screenshots.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        )}
        {result?.error && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            {result.error}
          </div>
        )}
      </div>
    </div>
  )
}
