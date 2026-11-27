import { fireEvent, render, screen } from '@testing-library/react'

import { SpiderChart, type Series } from '@/components/SpiderChart'
import { SERIES_COLOURS } from '@/lib/chart'

const skills = ['python', 'sql', 'spark']
const series: Series[] = [
  {
    id: 'a',
    label: 'Candidate AAAA',
    slot: 2,
    levels: [
      { skill: 'python', own_level: 5, estimated_level: 4, confidence: 0.75, via: null },
      { skill: 'sql', own_level: 3, estimated_level: 3, confidence: 0.5, via: 'dbt' },
      { skill: 'spark', own_level: null, estimated_level: null, confidence: null, via: null },
    ],
  },
]

describe('spider chart', () => {
  it('draws each candidate in the colour of their slot, with a legend and table', () => {
    render(<SpiderChart skills={skills} series={series} view="estimated" />)
    const shape = screen.getByTestId('shape-estimated-2')
    expect(shape).toHaveAttribute('stroke', SERIES_COLOURS[2])
    expect(screen.queryByTestId('shape-own-2')).toBeNull()
    expect(screen.getAllByText('Candidate AAAA')).toHaveLength(2) // legend and table
    expect(screen.getByText('estimated')).toBeInTheDocument()
    expect(screen.queryByText('own')).toBeNull()
    expect(screen.getByRole('row', { name: /^spark/ })).toHaveTextContent('– / –')
  })

  it('tells the values of a point on hover', () => {
    const { container } = render(<SpiderChart skills={skills} series={series} view="both" />)
    // Each drawn point has a mark and a bigger, transparent hit target.
    const targets = container.querySelectorAll('circle[fill="transparent"]')
    expect(targets).toHaveLength(4) // python and sql, estimated and own; spark has none
    fireEvent.mouseEnter(targets[1])
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent('Candidate AAAA · sql')
    expect(tip).toHaveTextContent('Estimated: 3 Working (confidence 0.50)')
    expect(tip).toHaveTextContent('Own: 3 Working')
    expect(tip).toHaveTextContent('From their dbt')
    fireEvent.mouseLeave(container.querySelector('svg[role=img]') as Element)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('needs three skills for a shape', () => {
    render(<SpiderChart skills={['python', 'sql']} series={series} view="both" />)
    expect(screen.getByText(/at least three skills/)).toBeInTheDocument()
    expect(screen.queryByRole('img')).toBeNull()
  })
})
