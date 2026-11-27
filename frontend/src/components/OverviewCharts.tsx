import { useState, type ReactNode } from 'react'

import { SERIES_COLOURS } from '@/lib/chart'
import type { Distribution } from '@/lib/types'
import { cn } from '@/lib/utils'

// One hue for every count on the overview: the first categorical slot, which is
// also the default sequential hue. Nothing here tells series apart by colour.
const BAR = SERIES_COLOURS[0]
const GRID = '#e5e7eb'
const AXIS_TEXT = '#6b7280'

/** "0.6–0.7" for a tenth; the last one includes 1. */
function binLabel(i: number, bins: number): string {
  const from = (i / bins).toFixed(1)
  const to = ((i + 1) / bins).toFixed(1)
  return `${from}–${to}`
}

function candidates(n: number): string {
  return `${n} candidate${n === 1 ? '' : 's'}`
}

export interface HistogramSeries {
  key: string
  label: string
  /** A sentence under the title on what the score is. */
  description: string
  distribution: Distribution
}

const W = 260
const H = 150
const LEFT = 26
const RIGHT = 6
const TOP = 22
const BOTTOM = 20
const GAP = 2
const RADIUS = 4

interface Hover {
  series: string
  bin: number
  count: number
  x: number
  y: number
}

/**
 * Small multiples: a histogram per score, side by side on one shared count axis
 * and the same 0 to 1 scale, so they compare at a glance. Each marks its median.
 * A table with every count follows, for screen readers and exact numbers.
 */
export function Histograms({ series }: { series: HistogramSeries[] }) {
  const [hover, setHover] = useState<Hover | null>(null)
  const max = Math.max(1, ...series.flatMap((s) => s.distribution.bins))
  const bins = series[0]?.distribution.bins.length ?? 10
  const plotW = W - LEFT - RIGHT
  const plotH = H - TOP - BOTTOM
  const band = plotW / bins
  const y = (n: number) => TOP + plotH - (plotH * n) / max
  const ticks = max > 1 ? [0, Math.round(max / 2), max].filter((t, i, a) => a.indexOf(t) === i) : [0, 1]

  return (
    <figure className="space-y-4">
      <div className="grid gap-6 sm:grid-cols-3">
        {series.map((s) => (
          <div key={s.key} className="space-y-1">
            <h3 className="text-sm font-medium">{s.label}</h3>
            <p className="text-xs text-muted-foreground">{s.description}</p>
            <div className="relative">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              className="h-auto w-full overflow-visible"
              role="img"
              aria-label={`${s.label}: candidates per tenth from 0 to 1${
                s.distribution.median === null ? '' : `, median ${s.distribution.median.toFixed(2)}`
              }. The table below has every count.`}
              onMouseLeave={() => setHover(null)}
            >
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={LEFT} x2={W - RIGHT} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
                  <text x={LEFT - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill={AXIS_TEXT}>
                    {t}
                  </text>
                </g>
              ))}
              {s.distribution.bins.map((n, i) => {
                const x0 = LEFT + i * band + GAP / 2
                const w = band - GAP
                const top = y(n)
                const h = TOP + plotH - top
                const r = Math.min(RADIUS, h, w / 2)
                const active = hover?.series === s.key && hover.bin === i
                return (
                  <g key={i}>
                    {n > 0 && (
                      <path
                        d={`M${x0},${TOP + plotH} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + w - r} Q${x0 + w},${top} ${x0 + w},${top + r} V${TOP + plotH} Z`}
                        fill={BAR}
                        opacity={hover && !active ? 0.55 : 1}
                      />
                    )}
                    {/* The hit target is the whole column, taller than the bar. */}
                    <rect
                      x={LEFT + i * band}
                      y={TOP}
                      width={band}
                      height={plotH}
                      fill="transparent"
                      data-testid={`bin-${s.key}-${i}`}
                      onMouseEnter={() => setHover({ series: s.key, bin: i, count: n, x: x0 + w / 2, y: top })}
                    />
                  </g>
                )
              })}
              {s.distribution.median !== null && (
                <MedianMark x={LEFT + plotW * s.distribution.median} median={s.distribution.median} />
              )}
              {[0, 0.5, 1].map((v) => (
                <text
                  key={v}
                  x={LEFT + plotW * v}
                  y={H - 4}
                  textAnchor={v === 0 ? 'start' : v === 1 ? 'end' : 'middle'}
                  fontSize={10}
                  fill={AXIS_TEXT}
                >
                  {v}
                </text>
              ))}
            </svg>
            {hover?.series === s.key && (
              <div
                role="tooltip"
                className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md bg-foreground px-2.5 py-1.5 text-xs whitespace-nowrap text-background shadow"
                style={{ left: `${(hover.x / W) * 100}%`, top: `calc(${(hover.y / H) * 100}% - 4px)` }}
              >
                <span className="tabular-nums">{binLabel(hover.bin, bins)}</span>: {candidates(hover.count)}
              </div>
            )}
            </div>
          </div>
        ))}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Show as a table</summary>
        <table className="mt-2 w-full max-w-xl text-sm">
          <caption className="sr-only">Candidates per tenth of each score</caption>
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="py-1 pr-4 font-medium">
                Score
              </th>
              {series.map((s) => (
                <th key={s.key} scope="col" className="py-1 pr-4 text-right font-medium">
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {Array.from({ length: bins }, (_, i) => (
              <tr key={i} className="border-b last:border-0">
                <th scope="row" className="py-1 pr-4 text-left font-normal">
                  {binLabel(i, bins)}
                </th>
                {series.map((s) => (
                  <td key={s.key} className="py-1 pr-4 text-right">
                    {s.distribution.bins[i]}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <th scope="row" className="py-1 pr-4 text-left font-medium">
                Median
              </th>
              {series.map((s) => (
                <td key={s.key} className="py-1 pr-4 text-right">
                  {s.distribution.median === null ? '–' : s.distribution.median.toFixed(2)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </details>
    </figure>
  )
}

function MedianMark({ x, median }: { x: number; median: number }) {
  return (
    <g aria-hidden>
      <line x1={x} x2={x} y1={TOP - 4} y2={H - BOTTOM} stroke="#191919" strokeWidth={1.5} strokeDasharray="3 3" />
      <text
        x={x}
        y={TOP - 8}
        textAnchor={median > 0.8 ? 'end' : median < 0.2 ? 'start' : 'middle'}
        fontSize={10}
        fill="#191919"
      >
        Median {median.toFixed(2)}
      </text>
    </g>
  )
}

export interface Meter {
  label: string
  value: number
  /** The whole the value is out of; the bar is value / of. */
  of: number
  /** The figure on the right; by default "value of of". */
  figure?: ReactNode
  /** A line under the label. */
  note?: ReactNode
}

/**
 * A meter list: a name, a bar and a figure per row, the bars aligned. The figures
 * are always printed, so no value rests on the bar alone.
 */
export function MeterList({ meters, label, className }: { meters: Meter[]; label: string; className?: string }) {
  return (
    <ul aria-label={label} className={cn('space-y-3', className)}>
      {meters.map((m) => {
        const share = m.of > 0 ? Math.min(1, m.value / m.of) : 0
        return (
          <li key={m.label} className="grid grid-cols-[minmax(8rem,12rem)_1fr_auto] items-center gap-x-3 gap-y-0.5">
            <span className="truncate text-sm" title={m.label}>
              {m.label}
            </span>
            <span
              className="h-2 overflow-hidden rounded-full bg-muted"
              role="meter"
              aria-label={m.label}
              aria-valuemin={0}
              aria-valuemax={m.of}
              aria-valuenow={m.value}
            >
              <span
                className="block h-full rounded-full"
                style={{ width: `${share * 100}%`, backgroundColor: BAR }}
              />
            </span>
            <span className="text-right text-sm tabular-nums text-muted-foreground">
              {m.figure ?? `${m.value} of ${m.of}`}
            </span>
            {m.note && <span className="col-span-3 text-xs text-muted-foreground sm:col-start-1">{m.note}</span>}
          </li>
        )
      })}
    </ul>
  )
}
