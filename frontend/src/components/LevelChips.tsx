import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { LEVELS } from '@/lib/format'
import type { SkillLevel } from '@/lib/types'

const ON =
  'data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

interface Props {
  /** The level chosen, or null for none. */
  value: SkillLevel | null
  onChange: (level: SkillLevel | null) => void
  /** What is rated, for screen readers, such as "Your level in python". */
  label: string
  disabled?: boolean
  /** Show only the numbers, with names as tooltips (for narrow places). */
  compact?: boolean
}

/**
 * Pick a level from 1 (aware) to 5 (expert) as a row of chips. Choosing the chosen
 * chip again clears it. Arrow keys move between chips, Space or Enter chooses.
 */
export function LevelChips({ value, onChange, label, disabled, compact }: Props) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={1}
      aria-label={label}
      value={value === null ? '' : String(value)}
      onValueChange={(v) => onChange(v ? (Number(v) as SkillLevel) : null)}
      disabled={disabled}
      className="flex-wrap"
    >
      {LEVELS.map((l) => (
        <ToggleGroupItem
          key={l.value}
          value={String(l.value)}
          aria-label={`${l.value} ${l.name}`}
          title={`${l.value} · ${l.name}: ${l.meaning}`}
          className={`rounded-full px-2.5 ${ON}`}
        >
          {compact ? l.value : `${l.value} ${l.name}`}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

/** A level shown, not chosen: "4 Advanced" as a chip, or nothing. */
export function LevelChip({ level }: { level: SkillLevel | null }) {
  const l = LEVELS.find((x) => x.value === level)
  if (!l) return null
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground"
      title={l.meaning}
    >
      <span className="flex gap-0.5" aria-hidden>
        {LEVELS.map((x) => (
          <span
            key={x.value}
            className={`size-1.5 rounded-full ${x.value <= l.value ? 'bg-primary' : 'bg-primary/20'}`}
          />
        ))}
      </span>
      {l.value} {l.name}
    </span>
  )
}
