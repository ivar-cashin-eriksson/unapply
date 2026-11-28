import { categoryColour } from '@/lib/categoryColour'
import { categoryLabel } from '@/lib/format'
import type { SkillCategory } from '@/lib/types'
import { cn } from '@/lib/utils'

/** A small round dot in the category's colour, hidden from screen readers. */
export function CategoryDot({ category, className }: { category: SkillCategory | null; className?: string }) {
  return (
    <span
      aria-hidden
      data-category={category ?? 'other'}
      className={cn('inline-block size-2.5 shrink-0 rounded-full', categoryColour(category).dot, className)}
    />
  )
}

/** A group's heading: the category's dot and name. */
export function CategoryHeading({ category }: { category: SkillCategory | null }) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
      <CategoryDot category={category} />
      {categoryLabel(category)}
    </h3>
  )
}
