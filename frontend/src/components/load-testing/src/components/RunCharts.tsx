import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { formatMs, formatRps } from '@/lib/format';
import { profilePoints, type ChartPoint } from '@/lib/timeseries';
import type { ConfigSummary } from '@/lib/types';

const axis = { stroke: 'currentColor', fontSize: 11, tickLine: false, axisLine: false } as const;
const grid = { strokeDasharray: '3 3', stroke: 'currentColor', strokeOpacity: 0.12 } as const;
const tooltipStyle = {
  contentStyle: {
    borderRadius: 8,
    border: '1px solid rgb(148 163 184 / 0.3)',
    background: 'rgb(15 23 42 / 0.92)',
    color: '#f8fafc',
    fontSize: 12,
  },
  labelStyle: { color: '#cbd5e1' },
  labelFormatter: (s: unknown) => `t = ${String(s)} s`,
};

const COLORS = {
  attempted: '#6366f1',
  accepted: '#10b981',
  rateLimited: '#f59e0b',
  errors: '#f43f5e',
  p50: '#0ea5e9',
  p90: '#8b5cf6',
  p99: '#f43f5e',
};

interface ChartProps {
  data: ChartPoint[];
  height?: number;
}

export function ThroughputChart({ data, height = 280 }: ChartProps) {
  return (
    <div className="text-slate-500 dark:text-slate-400" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <defs>
            {(['accepted', 'rateLimited', 'errors'] as const).map((k) => (
              <linearGradient key={k} id={`grad-${k}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS[k]} stopOpacity={0.45} />
                <stop offset="100%" stopColor={COLORS[k]} stopOpacity={0.05} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="second"
            {...axis}
            tickFormatter={(v: number) => `${v}s`}
            minTickGap={24}
          />
          <YAxis {...axis} width={56} tickFormatter={(v: number) => formatRps(v)} />
          <Tooltip
            {...tooltipStyle}
            formatter={(v, name) => [`${formatRps(Number(v))} rps`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
          <Area
            type="monotone"
            dataKey="accepted"
            name="Accepted"
            stackId="1"
            stroke={COLORS.accepted}
            fill="url(#grad-accepted)"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="rateLimited"
            name="429"
            stackId="1"
            stroke={COLORS.rateLimited}
            fill="url(#grad-rateLimited)"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="errors"
            name="Errors"
            stackId="1"
            stroke={COLORS.errors}
            fill="url(#grad-errors)"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="attempted"
            name="Attempted"
            stroke={COLORS.attempted}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LatencyChart({ data, height = 280 }: ChartProps) {
  const withLatency = data.filter((d) => d.p50 !== null || d.p99 !== null);
  return (
    <div className="text-slate-500 dark:text-slate-400" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={withLatency} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="second"
            {...axis}
            tickFormatter={(v: number) => `${v}s`}
            minTickGap={24}
          />
          <YAxis {...axis} width={56} tickFormatter={(v: number) => `${v}`} unit=" ms" />
          <Tooltip {...tooltipStyle} formatter={(v, name) => [formatMs(Number(v)), name]} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
          {(['p50', 'p90', 'p99'] as const).map((k) => (
            <Line
              key={k}
              type="monotone"
              dataKey={k}
              name={k}
              stroke={COLORS[k]}
              strokeWidth={k === 'p99' ? 2 : 1.5}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface CapacityPoint {
  asked: number;
  accepted: number;
}

export function ProfileChart({
  steps,
  height = 160,
}: {
  steps: ConfigSummary['profile'];
  height?: number;
}) {
  return (
    <div className="text-slate-500 dark:text-slate-400" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={profilePoints(steps)} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={[0, 'dataMax']}
            {...axis}
            tickFormatter={(v: number) => `${v}s`}
          />
          <YAxis {...axis} width={56} />
          <Tooltip {...tooltipStyle} formatter={(v) => [`${formatRps(Number(v))} rps`, 'target']} />
          <Area
            type="linear"
            dataKey="rate"
            stroke={COLORS.attempted}
            fill={COLORS.attempted}
            fillOpacity={0.15}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CapacityChart({ data, height = 240 }: { data: CapacityPoint[]; height?: number }) {
  return (
    <div className="text-slate-500 dark:text-slate-400" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid {...grid} />
          <XAxis
            dataKey="asked"
            {...axis}
            type="number"
            domain={['dataMin', 'dataMax']}
            unit=" rps"
          />
          <YAxis {...axis} width={56} />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(v) => `asked ${formatRps(Number(v))} rps`}
            formatter={(v) => [`${formatRps(Number(v))} rps`, 'accepted']}
          />
          <Line
            type="monotone"
            dataKey="accepted"
            stroke={COLORS.accepted}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
