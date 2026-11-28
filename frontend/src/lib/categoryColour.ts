import { cn } from '@/lib/utils'
import type { SkillCategory } from '@/lib/types'

/**
 * One colour per skill category, used wherever skills are grouped or categorised,
 * so a type of skill looks the same across the app. The category's name is always
 * written next to the colour, so the colour is never the only cue.
 *
 * Classes are written out in full so Tailwind finds them.
 */
const COLOURS: Record<SkillCategory | 'other', { dot: string; border: string }> = {
  technology: { dot: 'bg-blue-500', border: 'border-l-blue-500' },
  method: { dot: 'bg-violet-500', border: 'border-l-violet-500' },
  domain: { dot: 'bg-amber-500', border: 'border-l-amber-500' },
  soft_skill: { dot: 'bg-pink-500', border: 'border-l-pink-500' },
  language: { dot: 'bg-emerald-500', border: 'border-l-emerald-500' },
  certification: { dot: 'bg-cyan-500', border: 'border-l-cyan-500' },
  other: { dot: 'bg-zinc-400', border: 'border-l-zinc-400' },
}

/**
 * The colour classes of a category.
 *
 * @param category - The skill's category; a skill without one counts as "Other".
 */
export function categoryColour(category: SkillCategory | null): { dot: string; border: string } {
  return COLOURS[category ?? 'other']
}

/** Classes that give a card a coloured left edge for its category. */
export function categoryBorder(category: SkillCategory | null): string {
  return cn('border-l-4', categoryColour(category).border)
}
