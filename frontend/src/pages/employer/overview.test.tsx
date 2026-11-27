import { fireEvent, screen, within } from '@testing-library/react'

import { api } from '@/lib/api'
import type { Overview } from '@/lib/types'
import { job, overview } from '@/test/fixtures'
import { renderApp } from '@/test/render'

function open(data: Overview = overview()) {
  vi.spyOn(api, 'job').mockResolvedValue(job({ approved: true, history: ['extracted', 'rubric'] }))
  const load = vi.spyOn(api, 'overview').mockResolvedValue(data)
  return { load, ...renderApp('/jobs/fjord-grocery/overview') }
}

function meters(list: string) {
  const items = within(screen.getByRole('list', { name: list })).getAllByRole('meter')
  return items.map((m) => [m.getAttribute('aria-label'), m.getAttribute('aria-valuenow')])
}

describe('overview', () => {
  it('waits for an approved rubric', async () => {
    vi.spyOn(api, 'job').mockResolvedValue(job({ approved: false }))
    const load = vi.spyOn(api, 'overview')
    renderApp('/jobs/fjord-grocery/overview')
    expect(await screen.findByText('Approve the rubric first')).toBeInTheDocument()
    expect(load).not.toHaveBeenCalled()
    const steps = screen.getByRole('navigation', { name: 'Job steps' })
    expect(within(steps).queryByRole('link', { name: /Overview/ })).toBeNull()
  })

  it('shows the counts, the funnel and the vacancies', async () => {
    open()
    const candidates = await screen.findByLabelText('Candidates')
    expect(within(candidates).getByText('Connected').nextSibling).toHaveTextContent('4')
    expect(within(candidates).getByText('Matched').nextSibling).toHaveTextContent('3')
    expect(within(candidates).getByText('Meet every requirement').nextSibling).toHaveTextContent('2')
    expect(meters('How far candidates got')).toEqual([
      ['Connected', '4'],
      ['Revealed', '2'],
      ['Asked to apply', '1'],
      ['Applied', '1'],
    ])
    expect(screen.getByText(/1 vacancy: 1 application, enough to fill it\./)).toBeInTheDocument()
  })

  it('lists the failed filters and the skills, most common first', async () => {
    open()
    await screen.findByLabelText('Candidates')
    expect(meters('Requirements not met')).toEqual([
      ['Work permit', '1'],
      ['Location', '0'],
    ])
    expect(screen.getByText('1 not known (not excluded)')).toBeInTheDocument()
    expect(meters("The rubric's skills")).toEqual([
      ['python', '3'],
      ['sql', '2'],
      ['spark', '1'],
    ])
    expect(screen.getByText('1 more with a related skill')).toBeInTheDocument()
    expect(meters('Other common skills')).toEqual([
      ['docker', '2'],
      ['git', '1'],
    ])
  })

  it('draws a histogram per score with its median, and every count in a table', async () => {
    open()
    expect(await screen.findByRole('img', { name: /Baseline total: .* median 0\.90/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Own rating: .* median 0\.85/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Estimated from evidence: .* median 0\.72/ })).toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByTestId('bin-totals-9'))
    expect(screen.getByRole('tooltip')).toHaveTextContent('0.9–1.0: 2 candidates')
    const row = screen.getByRole('rowheader', { name: '0.9–1.0' }).closest('tr') as HTMLElement
    expect(within(row).getAllByRole('cell').map((c) => c.textContent)).toEqual(['2', '0', '0'])
  })

  it('reloads with the LLM scorer', async () => {
    const { load } = open()
    await screen.findByLabelText('Candidates')
    load.mockResolvedValue(overview({ scorer: 'llm', matched: 0, passed_hard_filters: 0 }))
    fireEvent.click(screen.getByRole('radio', { name: 'LLM' }))
    expect(await screen.findByText('No one is matched yet')).toBeInTheDocument()
    expect(load).toHaveBeenLastCalledWith('fjord-grocery', 'llm')
    expect(screen.getByRole('link', { name: 'Go to the shortlist' })).toBeInTheDocument()
  })

  it('shows nothing about one candidate', async () => {
    open()
    await screen.findByLabelText('Candidates')
    expect(document.body.textContent).not.toMatch(/Candidate [A-Z0-9]{4}|John|Doe/)
  })
})
