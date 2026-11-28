import { render, screen } from '@testing-library/react'

import { CategoryDot, CategoryHeading } from '@/components/CategoryColour'
import { categoryBorder, categoryColour } from '@/lib/categoryColour'
import { CATEGORIES } from '@/lib/format'

describe('category colours', () => {
  it('gives every category its own colour, and Other one more', () => {
    const dots = [...CATEGORIES.map((c) => c.value), null].map((c) => categoryColour(c).dot)
    expect(new Set(dots).size).toBe(CATEGORIES.length + 1)
  })

  it('treats a skill without a category as Other', () => {
    expect(categoryBorder(null)).toContain('border-l-4')
    render(<CategoryDot category={null} />)
    expect(document.querySelector('[data-category="other"]')).not.toBeNull()
  })

  it('writes the name next to the colour, and hides the dot from screen readers', () => {
    render(<CategoryHeading category="soft_skill" />)
    expect(screen.getByRole('heading', { name: 'Soft skill' })).toBeInTheDocument()
    expect(document.querySelector('[data-category="soft_skill"]')).toHaveAttribute('aria-hidden')
  })
})
