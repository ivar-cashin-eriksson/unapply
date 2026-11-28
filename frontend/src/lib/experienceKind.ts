import { Briefcase, GraduationCap, Lightbulb, type LucideIcon } from 'lucide-react'

import type { ExperienceKind } from '@/lib/types'

/**
 * How each kind of experience looks: its name, icon and colours, so work,
 * education and personal projects are told apart at a glance wherever they show.
 * The kind's name is always written next to the colour, so the colour is never the
 * only cue.
 *
 * Classes are written out in full so Tailwind finds them.
 */
export const EXPERIENCE_KINDS: Record<
  ExperienceKind,
  { label: string; plural: string; icon: LucideIcon; text: string; dot: string; line: string; border: string }
> = {
  work: {
    label: 'Work',
    plural: 'Work',
    icon: Briefcase,
    text: 'text-sky-700 dark:text-sky-400',
    dot: 'bg-sky-600',
    line: 'border-l-sky-600/40',
    border: 'border-l-sky-600',
  },
  education: {
    label: 'Education',
    plural: 'Education',
    icon: GraduationCap,
    text: 'text-orange-700 dark:text-orange-400',
    dot: 'bg-orange-500',
    line: 'border-l-orange-500/40',
    border: 'border-l-orange-500',
  },
  project: {
    label: 'Project',
    plural: 'Projects',
    icon: Lightbulb,
    text: 'text-teal-700 dark:text-teal-400',
    dot: 'bg-teal-600',
    line: 'border-l-teal-600/40',
    border: 'border-l-teal-600',
  },
}

/** The kinds in the order they are shown: work, then education, then projects. */
export const KIND_ORDER: ExperienceKind[] = ['work', 'education', 'project']

/**
 * Group entries by kind, in `KIND_ORDER`, keeping each entry's index in the list
 * and the list's order within a group. Kinds without entries are left out.
 *
 * @param entries - Entries with a kind.
 */
export function byKind<T extends { kind: ExperienceKind }>(
  entries: T[],
): { kind: ExperienceKind; entries: { entry: T; index: number }[] }[] {
  return KIND_ORDER.map((kind) => ({
    kind,
    entries: entries.map((entry, index) => ({ entry, index })).filter(({ entry }) => entry.kind === kind),
  })).filter((g) => g.entries.length > 0)
}
