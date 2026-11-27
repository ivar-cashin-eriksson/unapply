import { ChevronDown, Quote } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { splitList, WORK_MODES } from '@/lib/format'
import type { WorkMode } from '@/lib/types'

/** A label above a field, with an optional hint below. */
export function Field({
  label,
  hint,
  children,
  id,
}: {
  label: string
  hint?: string
  children: (id: string) => ReactNode
  id?: string
}) {
  const auto = useId()
  const fieldId = id ?? auto
  return (
    <div className="space-y-1.5">
      <Label htmlFor={fieldId}>{label}</Label>
      {children(fieldId)}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/**
 * A list typed as comma-separated text, such as "Copenhagen, Aarhus". The text is
 * kept as typed while editing, so a trailing comma doesn't vanish.
 */
export function ListInput({
  id,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  id?: string
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [text, setText] = useState(value.join(', '))
  const [seen, setSeen] = useState(value)
  // A new value from outside (such as a filled-in demo) replaces the text.
  if (value !== seen) {
    setSeen(value)
    if (splitList(text).join('\u0000') !== value.join('\u0000')) setText(value.join(', '))
  }
  return (
    <Input
      id={id}
      value={text}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => {
        setText(e.target.value)
        onChange(splitList(e.target.value))
      }}
    />
  )
}

/** A list typed one item per line, such as dealbreakers. Kept as typed while editing. */
export function LinesInput({
  id,
  value,
  onChange,
  rows = 3,
}: {
  id?: string
  value: string[]
  onChange: (value: string[]) => void
  rows?: number
}) {
  const clean = (t: string) =>
    t
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
  const [text, setText] = useState(value.join('\n'))
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    if (clean(text).join('\u0000') !== value.join('\u0000')) setText(value.join('\n'))
  }
  return (
    <Textarea
      id={id}
      rows={rows}
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        onChange(clean(e.target.value))
      }}
    />
  )
}

/** Choose any number of work modes. */
export function WorkModes({
  value,
  onChange,
  label,
  disabled,
}: {
  value: WorkMode[]
  onChange: (value: WorkMode[]) => void
  label: string
  disabled?: boolean
}) {
  return (
    <ToggleGroup
      type="multiple"
      variant="outline"
      size="sm"
      spacing={1}
      aria-label={label}
      value={value}
      disabled={disabled}
      onValueChange={(v) => onChange(v as WorkMode[])}
    >
      {WORK_MODES.map((m) => (
        <ToggleGroupItem
          key={m.value}
          value={m.value}
          className="rounded-full px-3 data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
        >
          {m.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

/** The quotes behind an item, folded away until asked for. */
export function Quotes({ lines, label = 'Evidence' }: { lines: string[]; label?: string }) {
  const [open, setOpen] = useState(false)
  const panel = useId()
  if (!lines.length) {
    return <p className="text-xs text-muted-foreground">No quote: your own statement.</p>
  }
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <Quote className="size-3" aria-hidden />
        {label}: {lines.length} {lines.length === 1 ? 'quote' : 'quotes'}
        <ChevronDown
          className={`size-3 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>
      {open && (
        <ul id={panel} className="mt-2 space-y-1.5 border-l-2 border-primary/20 pl-3">
          {lines.map((line, i) => {
            const at = line.indexOf(': ')
            const source = at > 0 ? line.slice(0, at) : ''
            const quote = at > 0 ? line.slice(at + 2) : line
            return (
              <li key={i} className="text-sm">
                {source && (
                  <span className="mr-1.5 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                    {source}
                  </span>
                )}
                “{quote}”
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
