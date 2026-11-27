import { useState } from 'react'

import { SERIES_COLOURS, type LevelView } from '@/lib/chart'
import { LEVELS } from '@/lib/format'
import type { SkillLevel, SkillLevels } from '@/lib/types'

export interface Series {
  /** Stable key, such as the profile id. */
  id: string
  label: string
  /**
   * Colour slot, 0 to MAX_COMPARED - 1. It belongs to the candidate while they
   * are compared, so removing another candidate never repaints them.
   */
  slot: number
  /** One per skill, in the chart's skill order. */
  levels: SkillLevels[]
}

interface Props {
  skills: string[]
  /** At most `MAX_COMPARED`, each with its own slot. */
  series: Series[]
  view: LevelView
}

const SIZE = 400
const CENTRE = SIZE / 2
const RADIUS = 130
// Room on the sides for skill names, wrapped to lines of about LINE characters.
const PAD = 72
const LINE = 13
// Sizes in chart units; the chart is drawn at about 0.7 of them in the side panel.
const LABEL = 16
const RING_LABEL = 13
const WIDTH = SIZE + 2 * PAD
const GRID = '#e5e7eb'

interface Hover {
  series: Series
  colour: string
  skill: number
  x: number
  y: number
}

/**
 * A spider (radar) chart of candidates' levels in a rubric's skills, 0 at the
 * centre to 5 (expert) at the edge. Estimated levels are solid shapes, own levels
 * dashed, so the two read apart without colour. A table with every value follows
 * the chart, for screen readers and for exact numbers.
 */
export function SpiderChart({ skills, series, view }: Props) {
  const [hover, setHover] = useState<Hover | null>(null)
  const n = skills.length
  if (n < 3) {
    return <p className="text-sm text-muted-foreground">The rubric needs at least three skills to draw a chart.</p>
  }
  const angle = (i: number) => (2 * Math.PI * i) / n - Math.PI / 2
  const point = (i: number, level: number) => {
    const r = (RADIUS * level) / 5
    return { x: CENTRE + r * Math.cos(angle(i)), y: CENTRE + r * Math.sin(angle(i)) }
  }
  const polygon = (levels: (number | null)[]) =>
    levels.map((l, i) => point(i, l ?? 0)).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const kinds: ('estimated' | 'own')[] = view === 'both' ? ['estimated', 'own'] : [view]
  const value = (s: SkillLevels, kind: 'estimated' | 'own') => (kind === 'own' ? s.own_level : s.estimated_level)

  return (
    <figure className="space-y-4">
      <Legend series={series} view={view} />
      <div className="relative mx-auto w-full max-w-[580px]">
        <svg
          viewBox={`${-PAD} 0 ${WIDTH} ${SIZE}`}
          className="h-auto w-full overflow-visible"
          role="img"
          aria-label={`Levels in ${n} skills, 0 to 5, for ${series.map((s) => s.label).join(', ') || 'no one'}. The table below has every value.`}
          onMouseLeave={() => setHover(null)}
        >
          {/* Rings for levels 1 to 5, and a spoke per skill: hairline, recessive. */}
          {LEVELS.map((l) => (
            <polygon key={l.value} points={polygon(skills.map(() => l.value))} fill="none" stroke={GRID} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {skills.map((skill, i) => {
            const end = point(i, 5)
            return (
              <line
                key={skill}
                x1={CENTRE}
                y1={CENTRE}
                x2={end.x}
                y2={end.y}
                stroke={GRID}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )
          })}
          {/* Ring numbers between the first and last spokes, away from the points. */}
          {[1, 3, 5].map((l) => {
            const p = point(-0.5, l)
            return (
              <text
                key={l}
                x={p.x}
                y={p.y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-muted-foreground"
                fontSize={RING_LABEL}
              >
                {l}
              </text>
            )
          })}
          {skills.map((skill, i) => {
            const p = point(i, 5.7)
            const cos = Math.cos(angle(i))
            const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end'
            const lines = wrap(skill)
            return (
              <text
                key={skill}
                x={p.x}
                y={p.y - ((lines.length - 1) * LABEL * 1.15) / 2}
                textAnchor={anchor}
                dominantBaseline="middle"
                className="fill-foreground"
                fontSize={LABEL}
              >
                {lines.map((line, k) => (
                  <tspan key={k} x={p.x} dy={k === 0 ? 0 : LABEL * 1.15}>
                    {line}
                  </tspan>
                ))}
              </text>
            )
          })}

          {series.map((s) => {
            const colour = SERIES_COLOURS[s.slot]
            return kinds.map((kind) => (
              <polygon
                key={`${s.id}-${kind}`}
                data-testid={`shape-${kind}-${s.slot}`}
                points={polygon(s.levels.map((l) => value(l, kind)))}
                fill={kind === 'estimated' ? colour : 'none'}
                fillOpacity={kind === 'estimated' ? 0.1 : 0}
                stroke={colour}
                strokeWidth={2}
                strokeDasharray={kind === 'own' ? '5 4' : undefined}
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            ))
          })}
          {series.map((s) =>
            kinds.map((kind) =>
              s.levels.map((l, i) => {
                const level = value(l, kind)
                if (level === null) return null
                const p = point(i, level)
                const colour = SERIES_COLOURS[s.slot]
                return (
                  <g key={`${s.id}-${kind}-${l.skill}`}>
                    {/* A 2px white ring keeps overlapping points apart. */}
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={5.5}
                      fill={kind === 'own' ? 'white' : colour}
                      stroke={kind === 'own' ? colour : 'white'}
                      strokeWidth={2}
                      vectorEffect="non-scaling-stroke"
                    />
                    {/* The hit target is bigger than the mark. */}
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={14}
                      fill="transparent"
                      onMouseEnter={() => setHover({ series: s, colour, skill: i, x: p.x, y: p.y })}
                    />
                  </g>
                )
              }),
            ),
          )}
        </svg>
        {hover && <Tooltip hover={hover} />}
      </div>
      <LevelsTable skills={skills} series={series} />
    </figure>
  )
}

function Legend({ series, view }: { series: Series[]; view: LevelView }) {
  return (
    <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      {series.map((s) => (
        <span key={s.id} className="flex items-center gap-2">
          <span className="size-3 rounded-full" style={{ background: SERIES_COLOURS[s.slot] }} aria-hidden />
          {s.label}
        </span>
      ))}
      <span className="flex items-center gap-4 text-muted-foreground">
        {view !== 'own' && (
          <span className="flex items-center gap-1.5">
            <svg width="22" height="6" aria-hidden>
              <line x1="0" y1="3" x2="22" y2="3" stroke="currentColor" strokeWidth="2" />
            </svg>
            estimated
          </span>
        )}
        {view !== 'estimated' && (
          <span className="flex items-center gap-1.5">
            <svg width="22" height="6" aria-hidden>
              <line x1="0" y1="3" x2="22" y2="3" stroke="currentColor" strokeWidth="2" strokeDasharray="5 4" />
            </svg>
            own
          </span>
        )}
      </span>
    </figcaption>
  )
}

function Tooltip({ hover }: { hover: Hover }) {
  const l = hover.series.levels[hover.skill]
  // The tooltip sits above the point, in the chart's own coordinates (as %).
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 w-max max-w-56 -translate-x-1/2 -translate-y-full rounded-md border bg-popover px-3 py-2 text-xs shadow-md"
      style={{ left: `${((hover.x + PAD) / WIDTH) * 100}%`, top: `calc(${(hover.y / SIZE) * 100}% - 10px)` }}
    >
      <p className="flex items-center gap-1.5 font-medium">
        <span className="size-2 rounded-full" style={{ background: hover.colour }} aria-hidden />
        {hover.series.label} · {l.skill}
      </p>
      <p>Estimated: {describe(l.estimated_level)}{l.confidence !== null && ` (confidence ${l.confidence.toFixed(2)})`}</p>
      <p>Own: {describe(l.own_level)}</p>
      {l.via && <p className="text-muted-foreground">From their {l.via}</p>}
    </div>
  )
}

/** Split a skill name into lines of about LINE characters, at spaces. */
function wrap(label: string): string[] {
  const lines: string[] = []
  for (const word of label.split(' ')) {
    const last = lines.length - 1
    if (last >= 0 && lines[last].length + 1 + word.length <= LINE) lines[last] += ` ${word}`
    else lines.push(word)
  }
  return lines
}

function describe(level: SkillLevel | null): string {
  const l = LEVELS.find((x) => x.value === level)
  return l ? `${l.value} ${l.name}` : 'none'
}

/** Every value of the chart, as a table. */
export function LevelsTable({ skills, series }: { skills: string[]; series: Series[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="pb-2 text-left text-xs text-muted-foreground">
          Levels 1 to 5: estimated / own. A dash means none.
        </caption>
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th scope="col" className="py-2 pr-4 font-medium">
              Skill
            </th>
            {series.map((s) => (
              <th key={s.id} scope="col" className="py-2 pr-4 font-medium">
                <span className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: SERIES_COLOURS[s.slot] }} aria-hidden />
                  {s.label}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {skills.map((skill, k) => (
            <tr key={skill} className="border-b last:border-0">
              <th scope="row" className="py-1.5 pr-4 text-left font-normal">
                {skill}
              </th>
              {series.map((s) => {
                const l = s.levels[k]
                return (
                  <td
                    key={s.id}
                    className="py-1.5 pr-4 tabular-nums"
                    aria-label={`estimated ${l?.estimated_level ?? 'none'}, own ${l?.own_level ?? 'none'}${l?.via ? `, via ${l.via}` : ''}`}
                  >
                    {l?.estimated_level ?? '–'} / {l?.own_level ?? '–'}
                    {l?.via && (
                      <span className="text-xs text-muted-foreground" title={`From their ${l.via}`}>
                        {' '}
                        via {l.via}
                      </span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
