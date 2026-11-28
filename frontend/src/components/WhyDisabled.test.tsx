import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { WhyDisabled } from '@/components/WhyDisabled'
import { Button } from '@/components/ui/button'

describe('WhyDisabled', () => {
  it('leaves an enabled control alone', async () => {
    const user = userEvent.setup()
    render(
      <WhyDisabled reason={false}>
        <Button>Send</Button>
      </WhyDisabled>,
    )
    const button = screen.getByRole('button', { name: 'Send' })
    expect(button).not.toHaveAccessibleDescription()
    // The wrapper takes no focus of its own: the keyboard goes straight to the button.
    await user.tab()
    expect(button).toHaveFocus()
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('keeps the control when the reason goes, so it stays the same element', () => {
    const { rerender } = render(
      <WhyDisabled reason="Paste the job ad first">
        <Button disabled>Draft</Button>
      </WhyDisabled>,
    )
    const before = screen.getByRole('button', { name: 'Draft' })
    rerender(
      <WhyDisabled reason={false}>
        <Button>Draft</Button>
      </WhyDisabled>,
    )
    expect(screen.getByRole('button', { name: 'Draft' })).toBe(before)
    expect(before).toBeEnabled()
    expect(before).not.toHaveAccessibleDescription()
  })

  it('says why a control is greyed out, to screen readers and in a tooltip', async () => {
    const user = userEvent.setup()
    render(
      <WhyDisabled reason="Answer at least one question first">
        <Button disabled>Send</Button>
      </WhyDisabled>,
    )
    const button = screen.getByRole('button', { name: 'Send' })
    expect(button).toHaveAccessibleDescription('Answer at least one question first')
    expect(screen.queryByRole('tooltip')).toBeNull()
    // The disabled button can't take focus, so the keyboard reaches its wrapper.
    await user.tab()
    expect(button.parentElement).toHaveFocus()
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Answer at least one question first')
  })
})
