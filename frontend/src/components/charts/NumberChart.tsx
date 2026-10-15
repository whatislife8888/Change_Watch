/**
 * NumberChart.tsx — a tracked number (price, count...) over time, plus a compact Sparkline.
 *
 * Chart rules we follow (from our data-viz checklist):
 * - One series, so no legend: the heading above the chart names what is plotted.
 * - 2 px lume line with round joins; hairline (1 px, solid) horizontal gridlines in the hairline colour.
 * - Salmon dots (8 px, with a 2 px surface-coloured ring) mark the checks where the page itself changed.
 * - Axis text uses text colours, never the data colour; y ticks are compact (1.2K, 74.9K).
 * - A vertical crosshair + tooltip that leads with the value. Every value is also in the table view,
 *   so the tooltip never gates information.
 */
import { useMemo, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts';
import type { NumbersOut } from '../../api/types';
import { dayAndTime } from '../../lib/time';
import s from './NumberChart.module.css';

const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 });
const full = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

interface Point { t: number; value: number; raw: string; changed: boolean }

function ChartTooltip({ active, payload, timeZone }: TooltipContentProps<number, string> & { timeZone?: string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as Point;
  return (
    <div className={s.tooltip}>
      <span className={s.tipKey} aria-hidden="true" />
      <strong className="num">{p.raw}</strong>
      <span className={s.tipTime}>{dayAndTime(new Date(p.t).toISOString(), timeZone)}</span>
      {p.changed && <span className={s.tipChanged}>The page changed here</span>}
    </div>
  );
}

/** Small dot drawn only on points where the page changed. */
function ChangeDot(props: { cx?: number; cy?: number; payload?: Point }) {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined || !payload?.changed) return null;
  return <circle cx={cx} cy={cy} r={4} fill="var(--salmon)" stroke="var(--surface)" strokeWidth={2} />;
}

export function NumberChart({ data, label, timeZone }: { data: NumbersOut; label: string; timeZone?: string }) {
  const [table, setTable] = useState(false);
  const points: Point[] = useMemo(() => {
    const changes = data.changed_at.map((c) => Date.parse(c));
    return data.points.map((p, i) => {
      const t = Date.parse(p.t);
      const prev = i > 0 ? Date.parse(data.points[i - 1].t) : -Infinity;
      // A point "saw a change" if a new version was saved between the previous point and this one.
      const changed = changes.some((c) => c > prev && c <= t + 60_000);
      return { t, value: p.value, raw: p.raw, changed };
    });
  }, [data]);

  return (
    <figure className={s.figure}>
      <figcaption className={s.caption}>
        <span>{label}</span>
        <button type="button" className={s.toggle} onClick={() => setTable((v) => !v)} aria-pressed={table}>
          {table ? 'Show chart' : 'Show as table'}
        </button>
      </figcaption>
      {table ? (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead><tr><th>Checked</th><th>Value</th><th>Page changed</th></tr></thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.t}><td className="num">{dayAndTime(new Date(p.t).toISOString(), timeZone)}</td><td className="num">{p.raw}</td><td>{p.changed ? 'Yes' : ''}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={s.chart}>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={points} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid vertical={false} stroke="var(--hairline)" strokeWidth={1} />
              <XAxis
                dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']}
                tickFormatter={(t: number) => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', timeZone }).format(new Date(t))}
                tick={{ fill: 'var(--text-2)', fontSize: 12 }} tickLine={false} axisLine={{ stroke: 'var(--hairline-strong)' }} minTickGap={48}
              />
              <YAxis
                dataKey="value" width={56} tickFormatter={(v: number) => compact.format(v)} domain={['auto', 'auto']}
                tick={{ fill: 'var(--text-2)', fontSize: 12 }} tickLine={false} axisLine={false}
              />
              <Tooltip
                cursor={{ stroke: 'var(--text-3)', strokeWidth: 1 }}
                content={(props) => <ChartTooltip {...(props as TooltipContentProps<number, string>)} timeZone={timeZone} />}
                isAnimationActive={false}
              />
              <Line
                type="monotone" dataKey="value" stroke="var(--lume)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
                dot={<ChangeDot />} activeDot={{ r: 5, fill: 'var(--lume)', stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </figure>
  );
}

/** Tiny trend line (no axes) for lists. Decorative: the latest value is always shown as text beside it. */
export function Sparkline({ values, width = 96, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)} ${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join('');
  const last = values[values.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className={s.spark}>
      <path d={d} fill="none" stroke="var(--text-3)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={height - 2 - ((last - min) / span) * (height - 4)} r={2.5} fill="var(--lume)" />
    </svg>
  );
}

export { full as numberFormat };
