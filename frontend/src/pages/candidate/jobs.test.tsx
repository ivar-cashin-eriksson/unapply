import { render, screen, waitFor, within } from '@testing-library/react'

import { AdText } from '@/components/AdText'
import { api, ApiError } from '@/lib/api'
import { adSummary, day, fitLabel, placeText, vacancies } from '@/lib/format'
import { board, candidate, connection, DAIRY, fit, listing } from '@/test/fixtures'
import { renderApp } from '@/test/render'

// Words for the rubric and the assessment, which a candidate never sees.
const HIDDEN = /rubric|criteri|weight|min.?level|estimat|confidence|claim support/i

// Every page here asks how well the candidate fits; tests that check it mock it again.
beforeEach(() => {
  vi.spyOn(api, 'fits').mockResolvedValue([])
  vi.spyOn(api, 'fit').mockResolvedValue(fit())
})

function approved() {
  vi.spyOn(api, 'candidate').mockResolvedValue(
    candidate({ has_profile: true, approved: true, history: ['extracted', 'approved'] }),
  )
}

describe('the job board', () => {
  it('lists the jobs with their vacancies and marks the ones connected', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    renderApp('/candidates/john-doe/jobs')

    const steps = await screen.findByRole('navigation', { name: 'Your steps' })
    expect(within(steps).getByRole('link', { name: /Jobs/ })).toHaveAttribute('aria-current', 'page')
    const jobs = await screen.findByRole('list', { name: 'Jobs' })
    const cards = within(jobs).getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByRole('link', { name: /Senior Data Scientist/ })).toHaveAttribute(
      'href',
      '/candidates/john-doe/jobs/board-fjord-grocery',
    )
    expect(within(cards[0]).getByText('1 vacancy')).toBeInTheDocument()
    expect(within(cards[0]).getByText('Fjord Grocery runs 85 grocery stores across Denmark.')).toBeInTheDocument()
    expect(await within(cards[0]).findByText('Connected')).toBeInTheDocument()
    expect(within(cards[1]).getByText('2 vacancies')).toBeInTheDocument()
    expect(within(cards[1]).getByText('Junior')).toBeInTheDocument()
    expect(within(cards[1]).queryByText('Connected')).toBeNull()
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent('2 jobs')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('shows how well you fit each job: band, place and missed requirements', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    vi.spyOn(api, 'fits').mockResolvedValue([
      fit({ connected: true, place: { rank: 4, of: 37, ranked_at: '2026-11-27T11:00:00' } }),
      fit({
        job: 'board-smoerblomst-dairy',
        band: 'partial',
        missed: [{ filter: 'work_permit', label: 'Work permit: EU required' }],
      }),
    ])
    renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    const first = await within(cards[0]).findByRole('group', { name: 'Your fit' })
    expect(first).toHaveTextContent('Strong fit')
    expect(first).toHaveTextContent("You're #4 of 37")
    expect(within(first).queryByRole('group', { name: "Requirements you don't meet" })).toBeNull()
    const second = within(cards[1]).getByRole('group', { name: 'Your fit' })
    expect(second).toHaveTextContent('Partial fit')
    expect(second).not.toHaveTextContent('#')
    expect(within(second).getByRole('group', { name: "Requirements you don't meet" })).toHaveTextContent(
      'Work permit: EU required',
    )
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('still lists the jobs when the fit does not load', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'fits').mockRejectedValue(new ApiError(500, 'The server broke.'))
    renderApp('/candidates/john-doe/jobs')
    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    expect(screen.queryByRole('group', { name: 'Your fit' })).toBeNull()
  })

  it('searches by words and filters, and clears them', async () => {
    approved()
    const search = vi.spyOn(api, 'board').mockImplementation(async (query = {}) =>
      query.q || query.seniority ? board({ listings: [DAIRY] }) : board(),
    )
    vi.spyOn(api, 'connections').mockResolvedValue([])
    const { user } = renderApp('/candidates/john-doe/jobs')

    await screen.findByRole('list', { name: 'Jobs' })
    await user.type(screen.getByLabelText('Search'), 'milk')
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({ q: 'milk' }))
    expect(await screen.findByText('1 of 2 jobs')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Seniority'), 'junior')
    await user.selectOptions(screen.getByLabelText('Work mode'), 'hybrid')
    await user.selectOptions(screen.getByLabelText('Location'), 'Copenhagen')
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith({
        q: 'milk',
        location: 'Copenhagen',
        work_mode: 'hybrid',
        seniority: 'junior',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}))
    expect(screen.getByLabelText('Search')).toHaveValue('')
    expect(await screen.findByText('2 jobs')).toBeInTheDocument()
  })

  it('says when nothing matches', async () => {
    approved()
    vi.spyOn(api, 'board').mockImplementation(async (query = {}) =>
      query.q ? board({ listings: [] }) : board(),
    )
    vi.spyOn(api, 'connections').mockResolvedValue([])
    const { user } = renderApp('/candidates/john-doe/jobs')
    await user.type(await screen.findByLabelText('Search'), 'astronaut')
    expect(await screen.findByText('No jobs match')).toBeInTheDocument()
  })

  it('offers the demo jobs on an empty board', async () => {
    approved()
    const load = vi.spyOn(api, 'board').mockResolvedValueOnce(board({ listings: [], total: 0 }))
    load.mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    const demo = vi.spyOn(api, 'createBoardDemo').mockResolvedValue({ jobs: ['board-fjord-grocery'] })
    const { user } = renderApp('/candidates/john-doe/jobs')

    expect(await screen.findByText('No jobs on the board yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add the demo jobs' }))
    expect(demo).toHaveBeenCalledOnce()
    expect(await screen.findByRole('list', { name: 'Jobs' })).toBeInTheDocument()
  })

  it('shows an error when the board does not load', async () => {
    approved()
    vi.spyOn(api, 'board').mockRejectedValue(new ApiError(500, 'The server broke.'))
    vi.spyOn(api, 'connections').mockResolvedValue([])
    renderApp('/candidates/john-doe/jobs')
    expect(await screen.findByText("Couldn't load the job board")).toBeInTheDocument()
  })
})

describe('a listing', () => {
  it('shows the ad and vacancies, and connects the profile', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing({ vacancies: 3 }))
    const connections = vi.spyOn(api, 'connections').mockResolvedValueOnce([])
    connections.mockResolvedValue([connection()])
    const connect = vi.spyOn(api, 'connect').mockResolvedValue(connection())
    const { user } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    expect(await screen.findByRole('heading', { level: 1, name: /Senior Data Scientist/ })).toBeInTheDocument()
    expect(screen.getByText('3 vacancies')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'What we are looking for' })).toBeInTheDocument()
    expect(screen.getByText('Strong Python and SQL.')).toBeInTheDocument()
    expect(screen.getByText('A demo job: the company is invented.')).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Connect my profile' }))
    expect(connect).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery')
    const region = await screen.findByRole('region', { name: 'Your connection' })
    expect(region).toHaveTextContent('Connected on 27 Nov 2026')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('shows your fit before connecting, and your place after', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    const connections = vi.spyOn(api, 'connections').mockResolvedValueOnce([])
    connections.mockResolvedValue([connection()])
    vi.spyOn(api, 'connect').mockResolvedValue(connection())
    const fits = vi
      .spyOn(api, 'fit')
      .mockResolvedValueOnce(
        fit({ band: 'good', missed: [{ filter: 'location', label: 'Location: Copenhagen' }] }),
      )
      .mockResolvedValue(
        fit({
          band: 'good',
          missed: [{ filter: 'location', label: 'Location: Copenhagen' }],
          connected: true,
          place: { rank: 3, of: 13, ranked_at: '2026-11-27T12:00:00' },
        }),
      )
    const { user } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    const region = await screen.findByRole('region', { name: 'How well you fit' })
    expect(region).toHaveTextContent('Good fit')
    expect(region).toHaveTextContent('From your own levels')
    expect(within(region).getByRole('group', { name: "Requirements you don't meet" })).toHaveTextContent(
      'Location: Copenhagen',
    )
    expect(region).toHaveTextContent('Connect to see your place among the connected candidates.')
    expect(fits).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery')

    await user.click(await screen.findByRole('button', { name: 'Connect my profile' }))
    await waitFor(() => expect(region).toHaveTextContent("You're #3 of 13 connected candidates"))
    expect(region).toHaveTextContent('in the latest ranking on 27 Nov 2026')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('says when you are connected but not ranked yet', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    vi.spyOn(api, 'fit').mockResolvedValue(fit({ band: 'low', connected: true }))
    renderApp('/candidates/john-doe/jobs/board-fjord-grocery')
    const region = await screen.findByRole('region', { name: 'How well you fit' })
    expect(region).toHaveTextContent('Low fit')
    expect(region).toHaveTextContent('Not ranked yet')
    expect(within(region).queryByRole('group', { name: "Requirements you don't meet" })).toBeNull()
  })

  it('withdraws, and says why when that is refused', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    const connections = vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    const withdraw = vi
      .spyOn(api, 'withdraw')
      .mockRejectedValueOnce(new ApiError(409, 'The employer has revealed you for this job.'))
      .mockResolvedValueOnce(undefined)
    const { user } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    await user.click(await screen.findByRole('button', { name: 'Withdraw' }))
    expect(await screen.findByText("Couldn't withdraw")).toBeInTheDocument()
    expect(screen.getByText('The employer has revealed you for this job.')).toBeInTheDocument()

    connections.mockResolvedValue([])
    await user.click(screen.getByRole('button', { name: 'Withdraw' }))
    expect(withdraw).toHaveBeenCalledTimes(2)
    expect(await screen.findByRole('button', { name: 'Connect my profile' })).toBeEnabled()
  })

  it('needs an approved profile to connect', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true, approved: false }))
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    renderApp('/candidates/john-doe/jobs/board-fjord-grocery')
    expect(await screen.findByRole('button', { name: 'Connect my profile' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'go to your review' })).toHaveAttribute(
      'href',
      '/candidates/john-doe/review',
    )
  })

  it('goes back to all jobs', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'board').mockResolvedValue(board())
    const { user, location } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')
    await user.click(await screen.findByRole('link', { name: 'All jobs' }))
    expect(location()).toBe('/candidates/john-doe/jobs')
  })

  it('says when a job is not on the board', async () => {
    approved()
    vi.spyOn(api, 'listing').mockRejectedValue(new ApiError(404, "No job 'gone' on the board."))
    vi.spyOn(api, 'connections').mockResolvedValue([])
    renderApp('/candidates/john-doe/jobs/gone')
    expect(await screen.findByText("Couldn't open the job")).toBeInTheDocument()
  })
})

describe('the ad text', () => {
  it('renders headings, lists and bold as text, never as HTML', () => {
    render(<AdText text={'# Title\n\n**Acme** <b>hi</b>\n\n- one\n  wrapped\n- two'} />)
    expect(screen.getByRole('heading', { name: 'Title' })).toBeInTheDocument()
    expect(screen.getByText('Acme').tagName).toBe('STRONG')
    expect(screen.getByText(/<b>hi<\/b>/)).toBeInTheDocument()
    const items = screen.getAllByRole('listitem')
    expect(items.map((i) => i.textContent)).toEqual(['one wrapped', 'two'])
  })

  it('leaves out a top heading that repeats the title', () => {
    render(<AdText text={['# Analyst', '', 'Come work with us.', '', '# Other'].join('\n')} title="Analyst" />)
    expect(screen.queryByRole('heading', { name: 'Analyst' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Other' })).toBeInTheDocument()
  })

  it('summarises an ad by its first plain paragraph', () => {
    expect(adSummary(listing().ad)).toBe('Fjord Grocery runs 85 grocery stores across Denmark.')
    expect(adSummary('# Only a title')).toBe('')
  })

  it('formats fit bands and places', () => {
    expect(fitLabel('strong')).toBe('Strong fit')
    expect(fitLabel('good')).toBe('Good fit')
    expect(fitLabel('partial')).toBe('Partial fit')
    expect(fitLabel('low')).toBe('Low fit')
    expect(placeText({ rank: 4, of: 37, ranked_at: '2026-11-27T11:00:00' })).toBe("You're #4 of 37")
  })

  it('formats vacancies and days', () => {
    expect(vacancies(1)).toBe('1 vacancy')
    expect(vacancies(3)).toBe('3 vacancies')
    expect(day('2026-11-05T10:00:00')).toBe('5 Nov 2026')
  })
})
