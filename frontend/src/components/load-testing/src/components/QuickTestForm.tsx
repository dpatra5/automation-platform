import { Plus, Trash2, Users, Gauge } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Field, Input, Select } from '@/components/ui/Field';
import { cn } from '@/lib/cn';
import {
  buildYaml,
  DEFAULT_PLAN,
  emptyStep,
  type HttpMethod,
  type LoadPattern,
  type QuickPlan,
  type QuickStep,
} from '@/lib/quickPlan';

const METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

const textarea =
  'block w-full rounded-md border-0 bg-white px-3 py-1.5 font-mono text-xs text-slate-900 shadow-xs ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-inset focus:ring-brand-500 focus:outline-none dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-700';

interface Props {
  onChange: (yaml: string) => void;
}

/** A form for the common case: a few requests, a load pattern, and pass/fail limits. */
export function QuickTestForm({ onChange }: Props) {
  const [plan, setPlan] = useState<QuickPlan>(DEFAULT_PLAN);

  useEffect(() => onChange(buildYaml(plan)), [plan, onChange]);

  const set = <K extends keyof QuickPlan>(key: K, value: QuickPlan[K]) =>
    setPlan((p) => ({ ...p, [key]: value }));
  const setStep = (index: number, patch: Partial<QuickStep>) =>
    setPlan((p) => ({ ...p, steps: p.steps.map((s, i) => (i === index ? { ...s, ...patch } : s)) }));
  const users = plan.pattern === 'users';

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2">
        <Field label="Test name">
          <Input value={plan.name} onChange={(e) => set('name', e.target.value)} />
        </Field>
        <Field label="Target base URL" hint="Its host is added to the safety allowlist.">
          <Input value={plan.baseUrl} onChange={(e) => set('baseUrl', e.target.value)} />
        </Field>
        <Field
          label="Headers sent with every request"
          hint="One per line, e.g. Authorization: Bearer {{token}}"
          className="md:col-span-2"
        >
          <textarea
            rows={2}
            className={textarea}
            value={plan.headers}
            onChange={(e) => set('headers', e.target.value)}
          />
        </Field>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Load pattern</h3>
        <div role="radiogroup" aria-label="Load pattern" className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ['users', Users, 'Virtual users', 'Like a JMeter thread group: users loop through the steps with think time.'],
              ['rps', Gauge, 'Requests per second', 'Fixed arrival rate, independent of response times.'],
            ] as const
          ).map(([id, Icon, title, description]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={plan.pattern === id}
              onClick={() => set('pattern', id as LoadPattern)}
              className={cn(
                'flex gap-3 rounded-lg p-3 text-left ring-1 transition-colors',
                plan.pattern === id
                  ? 'bg-brand-600/5 ring-2 ring-brand-500'
                  : 'ring-slate-200 hover:bg-slate-50 dark:ring-slate-800 dark:hover:bg-slate-800/40',
              )}
            >
              <Icon className="mt-0.5 size-4 shrink-0 text-brand-600" />
              <span>
                <span className="block text-sm font-medium">{title}</span>
                <span className="block text-xs text-slate-500 dark:text-slate-400">{description}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {users ? (
            <>
              <Field label="Users">
                <Input inputMode="numeric" value={plan.users} onChange={(e) => set('users', e.target.value)} />
              </Field>
              <Field label="Ramp-up" hint="e.g. 10s">
                <Input value={plan.rampUp} onChange={(e) => set('rampUp', e.target.value)} />
              </Field>
              <Field label="Hold for" hint="after ramp-up">
                <Input value={plan.duration} onChange={(e) => set('duration', e.target.value)} />
              </Field>
              <Field label="Think time" hint="1s or 500ms-2s">
                <Input value={plan.thinkTime} onChange={(e) => set('thinkTime', e.target.value)} />
              </Field>
              <Field label="Iterations / user" hint="blank = until time">
                <Input inputMode="numeric" value={plan.iterations} onChange={(e) => set('iterations', e.target.value)} />
              </Field>
            </>
          ) : (
            <>
              <Field label="Requests / second">
                <Input inputMode="decimal" value={plan.rps} onChange={(e) => set('rps', e.target.value)} />
              </Field>
              <Field label="Duration" hint="e.g. 30s, 5m">
                <Input value={plan.duration} onChange={(e) => set('duration', e.target.value)} />
              </Field>
            </>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            Requests {users && <span className="font-normal text-slate-500">(run in order by each user)</span>}
          </h3>
          <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => set('steps', [...plan.steps, emptyStep()])}>
            Add request
          </Button>
        </div>
        {plan.steps.map((step, i) => (
          <div key={i} className="space-y-3 rounded-lg p-3 ring-1 ring-slate-200 dark:ring-slate-800">
            <div className="flex items-end gap-2">
              <Field label="Name" className="w-40">
                <Input value={step.name} placeholder={`step ${i + 1}`} onChange={(e) => setStep(i, { name: e.target.value })} />
              </Field>
              <Field label="Method" className="w-28">
                <Select value={step.method} onChange={(e) => setStep(i, { method: e.target.value as HttpMethod })}>
                  {METHODS.map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Path" className="flex-1">
                <Input className="font-mono" value={step.path} onChange={(e) => setStep(i, { path: e.target.value })} />
              </Field>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Remove request ${i + 1}`}
                disabled={plan.steps.length === 1}
                onClick={() => set('steps', plan.steps.filter((_, j) => j !== i))}
                icon={<Trash2 className="size-4" />}
              />
            </div>
            {step.method !== 'GET' && step.method !== 'DELETE' && (
              <Field label="Body (JSON or text)">
                <textarea rows={2} className={textarea} value={step.body} onChange={(e) => setStep(i, { body: e.target.value })} />
              </Field>
            )}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Field label="Expect status" hint="blank = any 2xx/3xx">
                <Input value={step.expectStatus} placeholder="200, 201" onChange={(e) => setStep(i, { expectStatus: e.target.value })} />
              </Field>
              <Field label="Max response (ms)">
                <Input inputMode="numeric" value={step.maxMs} onChange={(e) => setStep(i, { maxMs: e.target.value })} />
              </Field>
              <Field label="Body contains">
                <Input value={step.bodyContains} onChange={(e) => setStep(i, { bodyContains: e.target.value })} />
              </Field>
              {users && (
                <>
                  <Field label="Save as variable" hint="use later as {{name}}">
                    <Input value={step.extractVar} placeholder="token" onChange={(e) => setStep(i, { extractVar: e.target.value })} />
                  </Field>
                  <Field label="From JSON path">
                    <Input className="font-mono" value={step.extractPath} placeholder="$.token" onChange={(e) => setStep(i, { extractPath: e.target.value })} />
                  </Field>
                </>
              )}
            </div>
          </div>
        ))}
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Use <code>{'{{variable}}'}</code> anywhere, plus built-ins like <code>{'{{$uuid}}'}</code>,{' '}
          <code>{'{{$vu}}'}</code>, <code>{'{{$iteration}}'}</code>, <code>{'{{$randomInt}}'}</code>.
        </p>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Pass / fail criteria</h3>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <Field label="95th percentile under (ms)">
            <Input inputMode="numeric" value={plan.p95Ms} onChange={(e) => set('p95Ms', e.target.value)} />
          </Field>
          <Field label="Error rate under (%)">
            <Input inputMode="decimal" value={plan.errorRatePct} onChange={(e) => set('errorRatePct', e.target.value)} />
          </Field>
          {users && (
            <Field label="Cap throughput (req/s)" hint="optional">
              <Input inputMode="decimal" value={plan.maxRps} onChange={(e) => set('maxRps', e.target.value)} />
            </Field>
          )}
        </div>
      </section>
    </div>
  );
}
