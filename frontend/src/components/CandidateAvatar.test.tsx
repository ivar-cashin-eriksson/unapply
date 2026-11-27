import { render } from '@testing-library/react'

import { CandidateAvatar } from '@/components/CandidateAvatar'

describe('CandidateAvatar', () => {
  it('draws a decorative SVG with nothing fetched from outside', () => {
    const { container } = render(<CandidateAvatar avatar={7} />)
    const svg = container.querySelector('svg') as SVGElement
    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).toHaveAttribute('data-avatar', '7')
    expect(container.querySelector('image, use, [href], [src]')).toBeNull()
    expect(container.querySelectorAll('rect').length).toBeGreaterThan(1)
  })

  it('looks different for different numbers', () => {
    const one = render(<CandidateAvatar avatar={1} />).container.innerHTML
    const two = render(<CandidateAvatar avatar={2} />).container.innerHTML
    expect(one).not.toBe(two)
  })
})
