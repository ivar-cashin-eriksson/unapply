import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'

import { LevelChip, LevelChips } from '@/components/LevelChips'
import type { SkillLevel } from '@/lib/types'

function Chips({ start = null }: { start?: SkillLevel | null }) {
  const [level, setLevel] = useState<SkillLevel | null>(start)
  return (
    <>
      <LevelChips value={level} onChange={setLevel} label="Your level in python" />
      <output>{level ?? 'none'}</output>
    </>
  )
}

describe('LevelChips', () => {
  it('chooses a level, and clears it when chosen again', async () => {
    const user = userEvent.setup()
    render(<Chips />)
    expect(screen.getByRole('radiogroup', { name: 'Your level in python' })).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: '4 Advanced' }))
    expect(screen.getByRole('status')).toHaveTextContent('4')
    expect(screen.getByRole('radio', { name: '4 Advanced' })).toBeChecked()
    await user.click(screen.getByRole('radio', { name: '4 Advanced' }))
    expect(screen.getByRole('status')).toHaveTextContent('none')
  })

  it('works with the keyboard: arrows move, Space chooses', async () => {
    const user = userEvent.setup()
    render(<Chips start={2} />)
    screen.getByRole('radio', { name: '2 Basic' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('radio', { name: '3 Working' })).toHaveFocus()
    await user.keyboard(' ')
    expect(screen.getByRole('status')).toHaveTextContent('3')
  })

  it('shows every level with its name and meaning', () => {
    render(<Chips />)
    const chip = screen.getByRole('radio', { name: '5 Expert' })
    expect(chip).toHaveTextContent('5 Expert')
    expect(chip).toHaveAttribute('title', expect.stringContaining('Deep, recognised expertise'))
  })

  it('can be disabled', () => {
    render(<LevelChips value={3} onChange={() => {}} label="Level" disabled />)
    for (const chip of screen.getAllByRole('radio')) expect(chip).toBeDisabled()
  })
})

describe('LevelChip', () => {
  it('shows a level, or nothing without one', () => {
    const { container, rerender } = render(<LevelChip level={4} />)
    expect(container).toHaveTextContent('4 Advanced')
    rerender(<LevelChip level={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
