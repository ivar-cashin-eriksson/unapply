import { useState } from 'react'

import { SERIES_COLOURS } from '@/lib/chart'
import { levelName, placeAmong } from '@/lib/format'
import type { Comparison, SkillLevel } from '@/lib/types'

// One series, so one hue: the first categorical slot, which is also the default
// sequential hue. The candidate's own level is marked by a ring and named in text,
// never by colour alone.
const BAR = SERIES_COLOURS[0]
const INK = '#191919'
const BASE = '#e5e7eb'
const AXIS_TEXT = '#6b7280'

const W = 120
const H = 46
const GAP = 4
const RADIUS = 3
const BOTTOM = 12

function others(n: number): string {
  return `${n} other${n === 1 ? '' : 's'}`
}

/**
 * Other candidates' own levels in a skill as five small bars, level 1 to 5, with
 * the candidate's own level ringed. Hovering a bar names its count; the line under
 * it always says where the candidate falls, so nothing rests on the bars alone.
 */
export function LevelDistribution({ comparison, own, skill }: { comparison: Comparison; own: SkillLevel | null; skill: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(1, ...comparison.levels)
  const band = W / 5
  const plotH = H - BOTTOM
  const summary = `Median ${comparison.median} of ${others(comparison.candidates)}`
  const place = own ? placeAmong(comparison.levels, own) : null
  return (
    <figure className="space-y-1">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-11.5 w-30"
        role="img"
        aria-label={`Other candidates' own levels in ${skill}: ${comparison.levels
          .map((n, i) => `${n} at ${i + 1}`)
          .join(', ')}. ${summary}.${place ? ` Yours: ${place}.` : ''}`}
        onMouseLeave={() => setHover(null)}
      >
        <line x1={0} x2={W} y1={plotH + 0.5} y2={plotH + 0.5} stroke={BASE} strokeWidth={1} />
        {comparison.levels.map((n, i) => {
          const x0 = i * band + GAP / 2
          const w = band - GAP
          const h = n ? Math.max(2, (plotH - 4) * (n / max)) : 0
          const top = plotH - h
          const r = Math.min(RADIUS, h, w / 2)
          const mine = own === i + 1
          return (
            <g key={i}>
              {n > 0 && (
                <path
                  d={`M${x0},${plotH} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + w - r} Q${x0 + w},${top} ${x0 + w},${top + r} V${plotH} Z`}
                  fill={BAR}
                  opacity={hover !== null && hover !== i ? 0.55 : 1}
                />
              )}
              {mine && (
                <rect
                  x={x0 - 1.5}
                  y={Math.min(top, plotH - 4) - 1.5}
                  width={w + 3}
                  height={Math.max(h, 4) + 1.5}
                  rx={RADIUS}
                  fill="none"
                  stroke={INK}
                  strokeWidth={1.5}
                  data-testid="own-level"
                />
              )}
              <text x={x0 + w / 2} y={H - 2} textAnchor="middle" fontSize={9} fill={mine ? INK : AXIS_TEXT} fontWeight={mine ? 600 : 400}>
                {i + 1}
              </text>
              {/* The hit target is the whole column, taller than the bar. */}
              <rect
                x={i * band}
                y={0}
                width={band}
                height={H}
                fill="transparent"
                data-testid={`level-${i + 1}`}
                onMouseEnter={() => setHover(i)}
              />
            </g>
          )
        })}
      </svg>
      <figcaption className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
        {hover !== null
          ? `${hover + 1} ${levelName((hover + 1) as SkillLevel)}: ${others(comparison.levels[hover])}`
          : place
            ? `Others: ${place}`
            : summary}
      </figcaption>
    </figure>
  )
}
