import { screen, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { Shortlist } from '@/lib/types'
import { job, shortlist } from '@/test/fixtures'
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
    expect(screen.getByText('Reveals: 0 of 10')).toBeInTheDocument()
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

  it('explains each criterion with the quotes it cites', async () => {
    const { user } = open()
    const first = await screen.findByRole('heading', { name: 'Candidate A1A1' })
    const why = within(first.closest('li') as HTMLElement).getByRole('button', { name: /Why/ })
    expect(why).toHaveAttribute('aria-expanded', 'false')
    await user.click(why)
    expect(why).toHaveAttribute('aria-expanded', 'true')
    const reasons = screen.getByRole('region', { name: 'Reasons for Candidate A1A1' })
    expect(within(reasons).getByText('Strong Python')).toBeInTheDocument()
    expect(within(reasons).getByText('python: level used for a1a1.')).toBeInTheDocument()
    expect(within(reasons).getByText(/Built forecasts in Python \(a1a1\)/)).toBeInTheDocument()
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

  it('records a reveal and an application request', async () => {
    const record = vi.spyOn(api, 'recordIntent').mockImplementation(async (_job, profileId, kind) => ({
      id: kind === 'reveal' ? 1 : 2,
      job_id: 'job-1',
      profile_id: profileId,
      kind,
      recorded_at: '2026-11-27T10:00:00',
    }))
    const { user } = open()
    await screen.findByRole('heading', { name: '3 ranked' })

    await user.click(screen.getByRole('button', { name: 'Reveal Candidate A1A1' }))
    expect(record).toHaveBeenCalledWith('fjord-grocery', 'a1a1', 'reveal')
    expect(await screen.findByText(/Reveal of Candidate A1A1 recorded\. No payment is taken/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reveal requested Candidate A1A1' })).toBeDisabled()
    expect(screen.getByText('Reveals: 1 of 10')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Request application from Candidate B0B0' }))
    expect(record).toHaveBeenCalledWith('fjord-grocery', 'b0b0', 'request_application')
    expect(await screen.findByText(/Application request to Candidate B0B0 recorded/)).toBeInTheDocument()
    expect(within(card('Candidate B0B0')).getByText('Application requested', { selector: '[data-slot=badge]' })).toBeInTheDocument()
    // The candidate's name is never asked for or shown.
    expect(document.body.textContent).not.toMatch(/john|jane|@/i)
  })

  it('shows earlier requests, and stops reveals at the quota', async () => {
    const data = shortlist({
      reveal_quota: 1,
      intents: [{ id: 1, job_id: 'job-1', profile_id: 'a1a1', kind: 'reveal', recorded_at: '2026-11-27T10:00:00' }],
    })
    open(data)
    expect(await screen.findByText('Reveals: 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reveal requested Candidate A1A1' })).toBeDisabled()
    const other = screen.getByRole('button', { name: 'Reveal Candidate B0B0' })
    expect(other).toBeDisabled()
    expect(other).toHaveAttribute('title', 'All reveals for this job are used')
    expect(screen.getByRole('button', { name: 'Request application from Candidate B0B0' })).toBeEnabled()
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
