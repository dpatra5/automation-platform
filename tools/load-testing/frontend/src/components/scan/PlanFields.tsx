import { Field, Input, Select } from '@/components/ui/Field';
import type { LoadPlan } from '@/lib/types';

interface PlanFieldsProps {
  value: LoadPlan;
  onChange: (plan: LoadPlan) => void;
  disabled?: boolean;
}

const num = (v: string): number | null => (v.trim() === '' ? null : Number(v));

export function PlanFields({ value, onChange, disabled }: PlanFieldsProps) {
  const set = <K extends keyof LoadPlan>(key: K, v: LoadPlan[K]) =>
    onChange({ ...value, [key]: v });
  return (
    <fieldset disabled={disabled} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Field
        label="Mode"
        hint={value.mode === 'per-endpoint' ? 'One run per API' : 'One mixed run per host'}
      >
        <Select
          value={value.mode}
          onChange={(e) => set('mode', e.target.value as LoadPlan['mode'])}
        >
          <option value="per-endpoint">Per endpoint</option>
          <option value="combined">Combined</option>
        </Select>
      </Field>
      <Field label="Rate (RPS)" hint="Offered load per run">
        <Input
          type="number"
          min={0.1}
          step="any"
          required
          value={value.rate}
          onChange={(e) => set('rate', Number(e.target.value))}
        />
      </Field>
      <Field label="Duration" hint="e.g. 30s, 2m">
        <Input required value={value.duration} onChange={(e) => set('duration', e.target.value)} />
      </Field>
      <Field label="Warm-up" hint="Optional, at 10% rate">
        <Input
          value={value.warmup ?? ''}
          placeholder="e.g. 5s"
          onChange={(e) => set('warmup', e.target.value.trim() || null)}
        />
      </Field>
      <Field label="Expected limit (RPS)" hint="Optional analysis target">
        <Input
          type="number"
          min={0}
          step="any"
          value={value.expected_limit_rps ?? ''}
          onChange={(e) => set('expected_limit_rps', num(e.target.value))}
        />
      </Field>
    </fieldset>
  );
}
