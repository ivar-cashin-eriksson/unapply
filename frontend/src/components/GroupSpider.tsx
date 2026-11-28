import { SERIES_COLOURS } from '@/lib/chart'
import { LEVELS } from '@/lib/format'
import type { GroupSkill } from '@/lib/types'

interface Props {
  skills: GroupSkill[]
  /** What the group is called in the legend and table, such as "Revealed". */
  label: string
}

const SIZE = 400
const CENTRE = SIZE / 2
const RADIUS = 130
// Room on the sides for skill names, wrapped to lines of about LINE characters.
const PAD = 72
const LINE = 13
const LABEL = 16
const RING_LABEL = 13
const GRID = '#e5e7eb'
const YOU = SERIES_COLOURS[0]
const THEM = SERIES_COLOURS[1]

/**
 * A spider (radar) chart of the candidate's own levels next to the median of a
 * group's own levels, 0 at the centre to 5 (expert) at the edge. The candidate is
 * a solid shape, the group dashed, so the two read apart without colour. A table
 * with every value follows, for screen readers and exact numbers. Needs three
 * skills for a shape; with fewer, only the table is shown.
 */
export function GroupSpider({ skills, label }: Props) {
  const n = skills.length
  const angle = (i: number) => (2 * Math.PI * i) / n - Math.PI / 2
  const point = (i: number, level: number) => {
    const r = (RADIUS * level) / 5
    return { x: CENTRE + r * Math.cos(angle(i)), y: CENTRE + r * Math.sin(angle(i)) }
  }
  const polygon = (levels: number[]) =>
    levels.map((l, i) => point(i, l)).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const you = skills.map((s) => s.own_level ?? 0)
  const them = skills.map((s) => s.median)

  return (
    <figure className="space-y-4">
      <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <span className="flex items-center gap-2">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke={YOU} strokeWidth="2" />
          </svg>
          You
        </span>
        <span className="flex items-center gap-2">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke={THEM} strokeWidth="2" strokeDasharray="5 4" />
          </svg>
          {label}: median
        </span>
        <span className="text-muted-foreground">Own levels, 0 to 5</span>
      </figcaption>
      {n >= 3 && (
        <div className="mx-auto w-full max-w-[520px]">
          <svg
            viewBox={`${-PAD} 0 ${SIZE + 2 * PAD} ${SIZE}`}
            className="h-auto w-full overflow-visible"
            role="img"
            aria-label={`Your own levels and the median of ${label.toLowerCase()} in ${n} skills, 0 to 5. The table below has every value.`}
          >
            {LEVELS.map((l) => (
              <polygon
                key={l.value}
                points={polygon(skills.map(() => l.value))}
                fill="none"
                stroke={GRID}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {skills.map((s, i) => {
              const end = point(i, 5)
              return (
                <line
                  key={s.skill}
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
            {skills.map((s, i) => {
              const p = point(i, 5.7)
              const cos = Math.cos(angle(i))
              const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end'
              const lines = wrap(s.skill)
              return (
                <text
                  key={s.skill}
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
            <polygon
              data-testid="shape-group"
              points={polygon(them)}
              fill="none"
              stroke={THEM}
              strokeWidth={2}
              strokeDasharray="5 4"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
            <polygon
              data-testid="shape-you"
              points={polygon(you)}
              fill={YOU}
              fillOpacity={0.12}
              stroke={YOU}
              strokeWidth={2}
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
            {skills.map((s, i) => {
              if (s.own_level === null) return null
              const p = point(i, s.own_level)
              return (
                <circle
                  key={s.skill}
                  cx={p.x}
                  cy={p.y}
                  r={5}
                  fill={YOU}
                  stroke="white"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              )
            })}
          </svg>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="pb-2 text-left text-xs text-muted-foreground">
            Own levels 1 to 5. A dash means you don&apos;t list it or gave no level.
          </caption>
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="py-2 pr-4 font-medium">
                Skill
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                You
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                {label}: median
              </th>
            </tr>
          </thead>
          <tbody>
            {skills.map((s) => (
              <tr key={s.skill} className="border-b last:border-0">
                <th scope="row" className="py-1.5 pr-4 text-left font-normal">
                  {s.skill}
                </th>
                <td className="py-1.5 pr-4 tabular-nums">{s.own_level ?? '–'}</td>
                <td className="py-1.5 pr-4 tabular-nums">{s.median}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
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
