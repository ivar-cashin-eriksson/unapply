import { screen, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { Shortlist } from '@/lib/types'
import { job, revealed, shortlist } from '@/test/fixtures'
import { renderApp } from '@/test/render'

function open(data: Shortlist = shortlist(), summary = job({ approved: true, history: ['extracted', 'rubric'] })) {
  vi.spyOn(api, 'job').mockResolvedValue(summary)
  const load = vi.spyOn(api, 'shortlist').mockResolvedValue(data)
  return { load, ...renderApp('/jobs/fjord-grocery/shortlist') }
}

function card(alias: string) {
  return screen.getByRole('heading', { name: alias }).closest('li') as HTMLElement
}

describe('shortlist', () => {
  it('waits for an approved rubric', async () => {
    vi.spyOn(api, 'job').mockResolvedValue(job({ approved: false }))
    const load = vi.spyOn(api, 'shortlist')
    renderApp('/jobs/fjord-grocery/shortlist')
    expect(await screen.findByText('Approve the rubric first')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the rubric' })).toBeInTheDocument()
    expect(load).not.toHaveBeenCalled()
    const steps = screen.getByRole('navigation', { name: 'Job steps' })
    expect(within(steps).queryByRole('link', { name: /Shortlist/ })).toBeNull()
  })

  it('lists anonymised candidates in rank order with their totals', async () => {
    open()
    expect(await screen.findByRole('heading', { name: '3 ranked' })).toBeInTheDocument()
    const names = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(names).toEqual(['Candidate A1A1', 'Candidate B0B0', 'Candidate C2C2'])
    expect(screen.getByRole('meter', { name: 'Total for Candidate A1A1' })).toHaveAttribute('aria-valuenow', '90')
    expect(within(card('Candidate A1A1')).getByLabelText('Rank 1')).toBeInTheDocument()
    // Unknown filters are said, but don't exclude.
    expect(within(card('Candidate A1A1')).getByText(/Not known: work permit/)).toBeInTheDocument()
    expect(screen.getByText('Reveals used: 0 of 10')).toBeInTheDocument()
    // How far candidates got, beside the vacancies.
    const counts = screen.getByRole('group', { name: 'How far candidates got' })
    expect(counts).toHaveTextContent('1 vacancy')
    expect(counts).toHaveTextContent('3 connected')
    expect(counts).toHaveTextContent('0 applications')
  })

  it("shows each candidate's own avatar beside the alias", async () => {
    const data = shortlist()
    open(data)
    await screen.findByRole('heading', { name: '3 ranked' })
    for (const c of data.candidates) {
      const avatar = card(c.alias).querySelector('svg[data-avatar]')
      expect(avatar).toHaveAttribute('data-avatar', String(c.avatar))
      expect(avatar).toHaveAttribute('aria-hidden', 'true')
    }
  })

  it('shows the scorer’s total beside the own rating and the estimate', async () => {
    open()
    const first = within(await screen.findByRole('heading', { name: 'Candidate B0B0' }).then((h) => h.closest('li') as HTMLElement))
    expect(first.getByText('Baseline total')).toBeInTheDocument()
    expect(first.getByRole('meter', { name: 'Total for Candidate B0B0' })).toHaveAttribute('aria-valuenow', '60')
    expect(first.getByRole('meter', { name: 'Own rating for Candidate B0B0' })).toHaveAttribute('aria-valuenow', '80')
    expect(first.getByRole('meter', { name: 'Estimated from evidence for Candidate B0B0' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    )
    expect(screen.getByText(/sets the rank/)).toBeInTheDocument()
    // Without the profile the match was made on, the two baseline scores aren't shown.
    const failed = within(card('Candidate C2C2'))
    expect(failed.getAllByText('Profile changed since matching')).toHaveLength(2)
  })

  it('puts candidates who fail a hard filter below a divider, scored and named', async () => {
    const { user } = open()
    const divider = await screen.findByRole('separator', { name: /Don't meet the requirements/ })
    expect(divider).toHaveTextContent('1')
    const passing = screen.getByRole('list', { name: 'Meet the requirements' })
    const failing = screen.getByRole('list', { name: "Don't meet the requirements" })
    expect(within(passing).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Candidate A1A1',
      'Candidate B0B0',
    ])
    const failed = card('Candidate C2C2')
    expect(failing).toContainElement(failed)
    expect(failed).not.toBeNull()
    expect(within(failed).getByText(/Doesn't meet work permit:/).closest('p')).toHaveTextContent(
      "Doesn't meet work permit: No permit to work in the EU.",
    )
    // Scored like the rest, and still last, though its total is the highest.
    expect(within(failed).getByRole('meter', { name: 'Total for Candidate C2C2' })).toHaveAttribute('aria-valuenow', '95')
    expect(within(failed).getByLabelText('Rank 3')).toBeInTheDocument()
    expect(failed.querySelector('[data-failed]')).toHaveClass('bg-destructive/5')
    expect(card('Candidate A1A1').querySelector('[data-failed]')).toBeNull()
    // Its reasons are there too.
    await user.click(within(failed).getByRole('button', { name: /Why/ }))
    expect(screen.getByRole('region', { name: 'Reasons for Candidate C2C2' })).toHaveTextContent('python: level used for c2c2.')
  })

  it('has no divider when everyone meets the requirements', async () => {
    const data = shortlist()
    data.ranking.candidates = data.ranking.candidates.filter((c) => c.passed_hard_filters)
    open(data)
    await screen.findByRole('heading', { name: '2 ranked' })
    expect(screen.queryByRole('separator', { name: /Don't meet/ })).toBeNull()
    expect(screen.queryByRole('list', { name: "Don't meet the requirements" })).toBeNull()
  })

  it('explains each criterion, with how many quotes support it but not the quotes, before a reveal', async () => {
    const { user } = open()
    await user.click(within(await screen.findByRole('heading', { name: 'Candidate A1A1' }).then((h) => h.closest('li') as HTMLElement)).getByRole('button', { name: /Why/ }))
    const reasons = screen.getByRole('region', { name: 'Reasons for Candidate A1A1' })
    expect(within(reasons).getByText('python: level used for a1a1.')).toBeInTheDocument()
    expect(within(reasons).getByText(/1 quote supports this, shown once you reveal the candidate/)).toBeInTheDocument()
    expect(within(reasons).queryByText(/Built forecasts/)).toBeNull()
    expect(document.body.textContent).not.toMatch(/Built forecasts|Forecasts demand/)
  })

  it('explains each criterion with the quotes it cites, once revealed', async () => {
    const data = shortlist()
    data.candidates[0] = revealed(data.candidates[0])
    const { user } = open(data)
    const first = await screen.findByRole('heading', { name: /Candidate A1A1/ })
    const why = within(first.closest('li') as HTMLElement).getByRole('button', { name: /Why/ })
    expect(why).toHaveAttribute('aria-expanded', 'false')
    await user.click(why)
    expect(why).toHaveAttribute('aria-expanded', 'true')
    const reasons = screen.getByRole('region', { name: 'Reasons for Candidate A1A1' })
    expect(within(reasons).getByText('Strong Python')).toBeInTheDocument()
    expect(within(reasons).getByText('python: level used for a1a1.')).toBeInTheDocument()
    expect(within(reasons).getByText(/Built forecasts in Python \(a1a1\)/)).toBeInTheDocument()
    expect(within(reasons).queryByText(/shown once you reveal/)).toBeNull()
    expect(within(reasons).getByRole('meter', { name: 'Strong Python: score' })).toHaveAttribute('aria-valuenow', '90')
    // The baseline doesn't read criteria without a skill, and says so.
    expect(within(reasons).getByText(/it names no skill/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Hard filters' })).toHaveTextContent('Location: meets it')
    expect(screen.getByRole('region', { name: 'Experience' })).toHaveTextContent('Data Scientist · Example Retail · Mar 2019 – now')
  })

  it('compares up to three candidates, keeping each one’s colour', async () => {
    const { user } = open()
    await screen.findByRole('heading', { name: '3 ranked' })
    expect(screen.getByText(/Tick “Compare” on up to 3 candidates/)).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: 'Compare Candidate A1A1' }))
    await user.click(screen.getByRole('checkbox', { name: 'Compare Candidate B0B0' }))
    const chart = screen.getByRole('img', { name: /Levels in 3 skills.*Candidate A1A1, Candidate B0B0/ })
    expect(chart).toBeInTheDocument()
    // Both levels by default: a solid estimated and a dashed own shape each.
    expect(screen.getByTestId('shape-estimated-0')).toBeInTheDocument()
    expect(screen.getByTestId('shape-own-1')).toHaveAttribute('stroke-dasharray', '5 4')

    // The table has every value, including where a level comes from a related skill.
    const table = screen.getByRole('table')
    const sql = within(table).getByRole('row', { name: /^sql/ })
    expect(sql).toHaveTextContent('4 / 4')
    expect(sql).toHaveTextContent('3 / 3 via dbt')
    expect(within(table).getByRole('row', { name: /^spark/ })).toHaveTextContent('– / –')

    // Only own levels.
    await user.click(screen.getByRole('radio', { name: 'Own' }))
    expect(screen.queryByTestId('shape-estimated-0')).toBeNull()
    expect(screen.getByTestId('shape-own-0')).toBeInTheDocument()

    // Taking the first out leaves the second in its own colour slot.
    await user.click(screen.getByRole('checkbox', { name: 'Compare Candidate A1A1' }))
    expect(screen.queryByTestId('shape-own-0')).toBeNull()
    expect(screen.getByTestId('shape-own-1')).toBeInTheDocument()
  })

  it('keeps the comparison when switching scorers', async () => {
    const { load, user } = open()
    await screen.findByRole('heading', { name: '3 ranked' })
    await user.click(screen.getByRole('checkbox', { name: 'Compare Candidate B0B0' }))
    await user.click(screen.getByRole('radio', { name: 'Estimated' }))
    await user.click(screen.getByRole('radio', { name: 'LLM' }))
    expect(load).toHaveBeenLastCalledWith('fjord-grocery', 'llm')
    expect(await screen.findByRole('checkbox', { name: 'Compare Candidate B0B0' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Estimated' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('shape-estimated-0')).toBeInTheDocument()
  })

  it('stops at three compared', async () => {
    const data = shortlist()
    const extra = { ...data.candidates[0], profile_id: 'd3d3', alias: 'Candidate D3D3' }
    data.candidates.push(extra)
    data.ranking.candidates.push({ ...data.ranking.candidates[0], profile_id: 'd3d3', match_id: 'm-d3d3', rank: 4 })
    const { user } = open(data)
    await screen.findByRole('heading', { name: '4 ranked' })
    for (const alias of ['A1A1', 'B0B0', 'C2C2']) {
      await user.click(screen.getByRole('checkbox', { name: `Compare Candidate ${alias}` }))
    }
    expect(screen.getByRole('checkbox', { name: 'Compare Candidate D3D3' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Compare Candidate B0B0' }))
    expect(screen.getByRole('checkbox', { name: 'Compare Candidate D3D3' })).toBeEnabled()
  })

  it('reveals, then requests an application, through one button', async () => {
    const reveal = vi.spyOn(api, 'reveal').mockResolvedValue(shortlist().candidates[0].progress)
    const request = vi.spyOn(api, 'requestApplication').mockResolvedValue(shortlist().candidates[0].progress)
    const { load, user } = open()
    await screen.findByRole('heading', { name: '3 ranked' })
    expect(within(card('Candidate A1A1')).queryByRole('button', { name: /Request application/ })).toBeNull()
    expect(document.body.textContent).not.toMatch(/Kim Berg|@/)

    // Reveal: the shortlist is read again, now with who it is.
    const afterReveal = shortlist({ counts: { connected: 3, revealed: 1, requested: 0, applied: 0 } })
    afterReveal.candidates[0] = revealed(afterReveal.candidates[0])
    load.mockResolvedValue(afterReveal)
    await user.click(screen.getByRole('button', { name: 'Reveal: Candidate A1A1' }))
    expect(reveal).toHaveBeenCalledWith('fjord-grocery', 'a1a1')
    expect(await screen.findByText(/Candidate A1A1 is revealed\. No payment is taken/)).toBeInTheDocument()
    const shown = await screen.findByRole('heading', { name: 'Kim Berg (Candidate A1A1)' })
    const li = within(shown.closest('li') as HTMLElement)
    expect(li.getByRole('link', { name: 'kim@example.org' })).toHaveAttribute('href', 'mailto:kim@example.org')
    expect(li.getByText('+45 11 22 33 44')).toBeInTheDocument()
    expect(li.getByText('Revealed', { selector: '[data-slot=badge]' })).toBeInTheDocument()
    expect(screen.getByText('Reveals used: 1 of 10')).toBeInTheDocument()

    // Then the same button asks them to apply.
    const afterRequest = shortlist({ counts: { connected: 3, revealed: 1, requested: 1, applied: 0 } })
    afterRequest.candidates[0] = revealed(afterRequest.candidates[0], 'requested')
    load.mockResolvedValue(afterRequest)
    await user.click(li.getByRole('button', { name: 'Request application: Kim Berg' }))
    expect(request).toHaveBeenCalledWith('fjord-grocery', 'a1a1')
    expect(await screen.findByText('Kim Berg is asked to apply.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Waiting for application: Kim Berg' })).toBeDisabled()
    expect(screen.getByRole('group', { name: 'How far candidates got' })).toHaveTextContent('1 asked to apply')
  })

  it('shows an application, a decline, and stops reveals at the quota', async () => {
    const data = shortlist({ reveal_quota: 2, counts: { connected: 3, revealed: 2, requested: 2, applied: 1 } })
    data.candidates[0] = revealed(data.candidates[0], 'applied')
    data.candidates[1] = revealed(data.candidates[1], 'declined', 'Sam Lund')
    open(data)
    expect(await screen.findByText('Reveals used: 2 of 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Applied: Kim Berg' })).toBeDisabled()
    const application = screen.getByRole('region', { name: 'Application from Kim Berg' })
    expect(application).toHaveTextContent('Dear Fjord Grocery, I would like to apply.')
    expect(within(application).getByRole('link', { name: 'cv.pdf' })).toHaveAttribute(
      'href',
      '/api/jobs/fjord-grocery/candidates/a1a1/files/7',
    )
    expect(screen.getByRole('button', { name: 'Declined: Sam Lund' })).toBeDisabled()
    expect(screen.queryByRole('region', { name: 'Application from Sam Lund' })).toBeNull()
    const other = screen.getByRole('button', { name: 'Reveal: Candidate C2C2' })
    expect(other).toBeDisabled()
    expect(other).toHaveAttribute('title', 'All reveals for this job are used')
  })

  it('says why a step was refused', async () => {
    vi.spyOn(api, 'reveal').mockRejectedValue(new ApiError(409, 'all 10 reveals for this job are used'))
    const { user } = open()
    await user.click(await screen.findByRole('button', { name: 'Reveal: Candidate B0B0' }))
    expect(await screen.findByText('all 10 reveals for this job are used')).toBeInTheDocument()
  })

  it('matches when no one is ranked yet, and switches scorers', async () => {
    const empty = shortlist({ ranking: { ...shortlist().ranking, candidates: [] }, candidates: [] })
    const { load, user } = open(empty)
    const match = vi.spyOn(api, 'match').mockResolvedValue(shortlist().ranking)
    expect(await screen.findByText('No one is ranked yet')).toBeInTheDocument()
    expect(screen.getByText(/The baseline is plain code/)).toBeInTheDocument()

    load.mockResolvedValue(shortlist())
    await user.click(screen.getByRole('button', { name: 'Match candidates' }))
    expect(match).toHaveBeenCalledWith('fjord-grocery', 'baseline')
    expect(await screen.findByRole('heading', { name: '3 ranked' })).toBeInTheDocument()
    expect(await screen.findByText('Ranked 3 candidates.')).toBeInTheDocument()

    load.mockResolvedValue(empty)
    await user.click(screen.getByRole('radio', { name: 'LLM' }))
    expect(load).toHaveBeenLastCalledWith('fjord-grocery', 'llm')
    expect(await screen.findByText(/the LLM scorer replays recorded answers/)).toBeInTheDocument()
  })

  it('says how to go on when matching is refused', async () => {
    const empty = shortlist({ ranking: { ...shortlist().ranking, candidates: [] }, candidates: [] })
    const { user } = open(empty, job({ demo: false, approved: true }))
    vi.spyOn(api, 'match').mockRejectedValue(new ApiError(403, 'Paid calls are off.'))
    await user.click(await screen.findByRole('radio', { name: 'LLM' }))
    expect(await screen.findByText(/makes paid model calls/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Match candidates' }))
    expect(await screen.findByText(/Try the demo/)).toBeInTheDocument()
  })
})
