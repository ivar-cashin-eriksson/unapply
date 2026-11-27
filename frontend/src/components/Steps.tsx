import { Check } from 'lucide-react'
import { NavLink } from 'react-router'

import { cn } from '@/lib/utils'

export interface Step {
  /** Path relative to the flow, such as "review". */
  to: string
  label: string
  done: boolean
  /** Not reachable yet; shown, but not a link. */
  locked?: boolean
}

/** Numbered steps across the top of a flow; the current one is highlighted. */
export function Steps({ steps, label }: { steps: Step[]; label: string }) {
  return (
    <nav aria-label={label} className="mb-8">
      <ol className="flex flex-wrap items-center gap-2">
        {steps.map((s, i) => (
          <li key={s.to} className="flex items-center gap-2">
            {i > 0 && <span className="h-px w-6 bg-border" aria-hidden />}
            {s.locked ? (
              <span
                className="flex items-center gap-2 rounded-full px-3 py-1.5 text-sm text-muted-foreground/70"
                aria-disabled
              >
                <Bubble n={i + 1} done={false} active={false} />
                {s.label}
              </span>
            ) : (
              <NavLink
                to={s.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 rounded-full px-3 py-1.5 text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
                    isActive
                      ? 'bg-accent font-medium text-accent-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Bubble n={i + 1} done={s.done} active={isActive} />
                    {s.label}
                    {s.done && <span className="sr-only"> (done)</span>}
                  </>
                )}
              </NavLink>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

function Bubble({ n, done, active }: { n: number; done: boolean; active: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        'flex size-6 items-center justify-center rounded-full border text-xs font-medium',
        done && 'border-primary bg-primary text-primary-foreground',
        !done && active && 'border-primary text-primary',
        !done && !active && 'border-border',
      )}
    >
      {done ? <Check className="size-3.5" /> : n}
    </span>
  )
}
