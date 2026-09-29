import { FileCode2, CheckCircle2, XCircle } from 'lucide-react'
import type { GeneratedTestScript, ScriptValidationResult } from '../models/testScript.types'

interface TestScriptViewerProps {
  script: GeneratedTestScript | null
  validation: ScriptValidationResult | null
}

export function TestScriptViewer({ script, validation }: TestScriptViewerProps) {
  if (!script) return null
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
        <FileCode2 className="w-4 h-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-900">Generated Automation Script</h3>
        <span className="ml-auto text-xs text-slate-400">{script.id}</span>
      </div>
      <div className="p-6 space-y-3">
        {validation && (
          <div
            className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${
              validation.valid
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                : 'bg-red-50 border-red-200 text-red-700'
            }`}
          >
            {validation.valid ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <XCircle className="w-3.5 h-3.5" />
            )}
            <span>
              {validation.valid
                ? 'Script passed validation'
                : `${validation.errors.length} error(s) — script blocked`}
            </span>
          </div>
        )}
        <pre className="text-xs bg-slate-900 text-slate-100 rounded-lg p-4 overflow-auto max-h-80">
          {JSON.stringify(script, null, 2)}
        </pre>
        {validation && validation.errors.length > 0 && (
          <ul className="text-xs text-red-700 list-disc pl-5 space-y-0.5">
            {validation.errors.map((e) => (
              <li key={`${e.code}-${e.field}`}>
                <span className="font-mono">{e.field}</span> — {e.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
