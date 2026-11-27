import { avatar, GRID } from '@/lib/avatar'
import { cn } from '@/lib/utils'

/**
 * An unrevealed candidate's avatar: a mirrored pattern in one colour on a light
 * tint of it. Decorative, since the alias beside it names the candidate.
 */
export function CandidateAvatar({ avatar: n, className }: { avatar: number; className?: string }) {
  const { colour, cells } = avatar(n)
  const pad = 1
  const size = GRID + 2 * pad
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className={cn('size-10 shrink-0 rounded-lg', className)}
      aria-hidden
      data-avatar={n}
      shapeRendering="crispEdges"
    >
      <rect width={size} height={size} fill={colour} fillOpacity={0.12} />
      {cells.map(([row, col]) => (
        <rect key={`${row}-${col}`} x={col + pad} y={row + pad} width={1} height={1} fill={colour} />
      ))}
    </svg>
  )
}
