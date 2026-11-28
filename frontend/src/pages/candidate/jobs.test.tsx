import { render, screen, waitFor, within } from '@testing-library/react'

import { AdText } from '@/components/AdText'
import { api, ApiError } from '@/lib/api'
import { adSummary, day, fitLabel, placeText, vacancies } from '@/lib/format'
import { board, candidate, connection, DAIRY, fit, listing, progressed } from '@/test/fixtures'
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
    // How far the job's candidates got.
    const counts = within(cards[0]).getByRole('group', { name: 'How far candidates got' })
    expect(counts).toHaveTextContent('13 connected')
    expect(counts).toHaveTextContent('2 revealed')
    expect(counts).toHaveTextContent('1 asked to apply')
    expect(counts).toHaveTextContent('0 applications')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('shows the requests to apply on top, and each stage on its card', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([
      progressed('requested'),
      progressed('applied', { job: DAIRY.name, listing: DAIRY }),
    ])
    renderApp('/candidates/john-doe/jobs')
    const requests = await screen.findByRole('region', { name: 'Asked to apply' })
    expect(requests).toHaveTextContent('Fjord Grocery ApS asked you to apply for Senior Data Scientist')
    expect(within(requests).getByRole('link', { name: 'Answer' })).toHaveAttribute(
      'href',
      '/candidates/john-doe/jobs/board-fjord-grocery',
    )
    // Only waiting requests are listed there.
    expect(requests).not.toHaveTextContent('Junior')
    const cards = within(screen.getByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    expect(within(cards[0]).getByText('Asked to apply', { selector: '[data-slot=badge]' })).toBeInTheDocument()
    expect(within(cards[1]).getByText('Applied', { selector: '[data-slot=badge]' })).toBeInTheDocument()
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

  it('filters by work permit, vacancies and skills in the advanced section', async () => {
    approved()
    const search = vi.spyOn(api, 'board').mockImplementation(async (query = {}) =>
      query.skill?.length ? board({ listings: [listing()] }) : board(),
    )
    vi.spyOn(api, 'connections').mockResolvedValue([])
    const { user } = renderApp('/candidates/john-doe/jobs')

    await screen.findByRole('list', { name: 'Jobs' })
    const toggle = screen.getByRole('button', { name: 'Advanced' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('Work permit')).toBeNull()
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const advanced = screen.getByRole('group', { name: 'Advanced filters' })
    // Only what listings show: no filter by skill level.
    expect(within(advanced).getAllByRole('combobox')).toHaveLength(3)
    expect(within(screen.getByLabelText('Vacancies')).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Any',
      'At least 2 vacancies',
    ])
    await user.selectOptions(screen.getByLabelText('Work permit'), 'EU')
    await user.selectOptions(screen.getByLabelText('Vacancies'), '2')
    await user.selectOptions(screen.getByLabelText('Skills in the ad'), 'python')
    await user.selectOptions(screen.getByLabelText('Skills in the ad'), 'sql')
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith({ work_permit: 'EU', min_vacancies: 2, skill: ['python', 'sql'] }),
    )
    // A chosen skill leaves the list, and each filter shows as a chip.
    expect(within(screen.getByLabelText('Skills in the ad')).queryByRole('option', { name: 'python' })).toBeNull()
    const chips = screen.getByRole('list', { name: 'Active filters' })
    expect(within(chips).getAllByRole('listitem').map((c) => c.textContent)).toEqual([
      'Work permit: EU',
      'At least 2 vacancies',
      'Skill: python',
      'Skill: sql',
    ])
    expect(await screen.findByText('1 of 2 jobs')).toBeInTheDocument()

    await user.click(within(chips).getByRole('button', { name: 'Remove Skill: python' }))
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith({ work_permit: 'EU', min_vacancies: 2, skill: ['sql'] }),
    )
    await user.click(screen.getAllByRole('button', { name: 'Clear filters' })[0])
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}))
    expect(screen.queryByRole('list', { name: 'Active filters' })).toBeNull()
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('adds a filter from any pill on a card, shown as a removable chip', async () => {
    approved()
    const search = vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'fits').mockResolvedValue([
      fit({ band: 'good' }),
      fit({ job: DAIRY.name, band: 'low', missed: [{ filter: 'location', label: 'Location: Copenhagen' }] }),
    ])
    const { user } = renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    const fjord = cards[0]
    expect(within(fjord).getByRole('group', { name: 'Named in the ad' })).toHaveTextContent(
      'pythonsqltime series forecasting',
    )
    const pills: [string, object][] = [
      ['Senior', { seniority: 'senior' }],
      ['Hybrid', { work_mode: 'hybrid' }],
      ['Copenhagen', { location: 'Copenhagen' }],
      ['EU work permit', { work_permit: 'EU' }],
      ['1 vacancy', { min_vacancies: 1 }],
      ['python', { skill: ['python'] }],
    ]
    for (const [name, expected] of pills) {
      await user.click(within(fjord).getByRole('link', { name }))
      await waitFor(() => expect(search).toHaveBeenLastCalledWith(expect.objectContaining(expected)))
    }
    await user.click(await within(fjord).findByRole('link', { name: /Good fit/ }))
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ candidate: 'john-doe', fit: 'good' })),
    )
    const chips = screen.getByRole('list', { name: 'Active filters' })
    expect(within(chips).getAllByRole('listitem').map((c) => c.textContent)).toEqual([
      'Fit: Good fit',
      'Location: Copenhagen',
      'Work mode: Hybrid',
      'Seniority: Senior',
      'Work permit: EU',
      'At least 1 vacancy',
      'Skill: python',
    ])
    // The selects follow, and the advanced section opens for the filters it holds.
    expect(screen.getByLabelText('Seniority')).toHaveValue('senior')
    expect(screen.getByLabelText('Location')).toHaveValue('Copenhagen')
    // A missed requirement finds the jobs with requirements you don't meet.
    await user.click(within(cards[1]).getByRole('link', { name: /Location: Copenhagen/ }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ fit: 'not_met' })))

    await user.click(within(chips).getByRole('button', { name: 'Remove Seniority: Senior' }))
    await waitFor(() => expect(search.mock.lastCall?.[0]?.seniority).toBeUndefined())
    expect(screen.getByLabelText('Seniority')).toHaveValue('')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('opens the advanced section by itself when the address has its filters', async () => {
    approved()
    const search = vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    renderApp('/candidates/john-doe/jobs?skill=sql&work_permit=EU')
    expect(await screen.findByRole('group', { name: 'Advanced filters' })).toBeInTheDocument()
    expect(screen.getByLabelText('Work permit')).toHaveValue('EU')
    expect(search).toHaveBeenLastCalledWith({ skill: ['sql'], work_permit: 'EU' })
  })

  it('filters by your fit and sorts best fit first', async () => {
    approved()
    const search = vi.spyOn(api, 'board').mockImplementation(async (query = {}) =>
      query.fit === 'not_met' ? board({ listings: [DAIRY] }) : query.sort === 'fit' ? board({ listings: [DAIRY, listing()] }) : board(),
    )
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'fits').mockResolvedValue([
      fit({ band: 'good' }),
      fit({
        job: DAIRY.name,
        band: 'strong',
        missed: [{ filter: 'work_permit', label: 'Work permit: EU required' }],
      }),
    ])
    const { user } = renderApp('/candidates/john-doe/jobs')

    const fitFilter = await screen.findByLabelText('Fit')
    expect(within(fitFilter).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Any',
      'Strong fit',
      'Good fit',
      'Partial fit',
      'Low fit',
      'Requirements not met',
    ])
    const sort = screen.getByLabelText('Sort')
    expect(sort).toHaveValue('newest')
    // Newest first asks nothing about the candidate.
    expect(search).toHaveBeenLastCalledWith({})

    await user.selectOptions(sort, 'fit')
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({ candidate: 'john-doe', sort: 'fit' }))
    await waitFor(() => {
      const cards = within(screen.getByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
      expect(cards[0]).toHaveTextContent('Strong fit')
    })
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent('2 jobs')

    await user.selectOptions(screen.getByLabelText('Fit'), 'not_met')
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith({ candidate: 'john-doe', fit: 'not_met', sort: 'fit' }),
    )
    expect(await screen.findByText('1 of 2 jobs')).toBeInTheDocument()

    // Clearing the filters keeps the order.
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({ candidate: 'john-doe', sort: 'fit' }))
    expect(screen.getByLabelText('Fit')).toHaveValue('')
    expect(screen.getByLabelText('Sort')).toHaveValue('fit')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('keeps the jobs and the filters on screen while the next search loads', async () => {
    approved()
    vi.spyOn(api, 'board').mockImplementation((query = {}) =>
      query.q ? new Promise(() => {}) : Promise.resolve(board()),
    )
    vi.spyOn(api, 'connections').mockResolvedValue([])
    const { user } = renderApp('/candidates/john-doe/jobs')
    await screen.findByRole('list', { name: 'Jobs' })
    const input = screen.getByLabelText('Search')
    await user.type(input, 'milk')
    expect(await screen.findByText(/searching/)).toBeInTheDocument()
    // The same input, still focused, and the last results still listed.
    expect(screen.getByLabelText('Search')).toBe(input)
    expect(input).toHaveFocus()
    expect(within(screen.getByRole('list', { name: 'Jobs' })).getAllByRole('listitem')).toHaveLength(2)
  })

  it('offers no fit filter or sort without a band', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'fits').mockResolvedValue([fit({ band: null }), fit({ job: DAIRY.name, band: null })])
    renderApp('/candidates/john-doe/jobs')
    await screen.findByRole('list', { name: 'Jobs' })
    await screen.findByLabelText('Seniority')
    expect(screen.queryByLabelText('Fit')).toBeNull()
    expect(screen.queryByLabelText('Sort')).toBeNull()
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

  it('connects and withdraws from a card, as on the listing', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    const connections = vi.spyOn(api, 'connections').mockResolvedValue([])
    const fits = vi.spyOn(api, 'fits').mockResolvedValue([])
    const connect = vi.spyOn(api, 'connect').mockResolvedValue(connection())
    const withdraw = vi.spyOn(api, 'withdraw').mockResolvedValue(undefined)
    const { user } = renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    const button = await within(cards[0]).findByRole('button', { name: 'Connect my profile: Senior Data Scientist, Pricing and Forecasting' })
    expect(button).toHaveTextContent('Connect my profile')
    expect(within(cards[1]).getByRole('button', { name: /^Connect my profile: / })).toBeEnabled()
    expect(screen.queryByRole('link', { name: 'go to your review' })).toBeNull()

    connections.mockResolvedValue([connection()])
    await user.click(button)
    expect(connect).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery')
    expect(await screen.findByText('Your profile is connected to Fjord Grocery ApS.')).toBeInTheDocument()
    expect(await within(cards[0]).findByText('Connected')).toBeInTheDocument()
    // The fit is asked again, for the place among the connected.
    expect(fits.mock.calls.length).toBeGreaterThan(1)
    // The other card is unchanged.
    expect(within(cards[1]).getByRole('button', { name: /^Connect my profile: / })).toBeEnabled()

    connections.mockResolvedValue([])
    await user.click(within(cards[0]).getByRole('button', { name: 'Withdraw: Senior Data Scientist, Pricing and Forecasting' }))
    expect(withdraw).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery')
    expect(await screen.findByText('You withdrew from Fjord Grocery ApS.')).toBeInTheDocument()
    expect(
      await within(cards[0]).findByRole('button', { name: 'Connect my profile: Senior Data Scientist, Pricing and Forecasting' }),
    ).toBeEnabled()
    expect(within(cards[0]).queryByText('Connected')).toBeNull()
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)
  })

  it('says on the card why a withdrawal was refused', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    vi.spyOn(api, 'withdraw').mockRejectedValue(new ApiError(409, 'The employer has revealed you for this job.'))
    const { user } = renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    await user.click(await within(cards[0]).findByRole('button', { name: 'Withdraw: Senior Data Scientist, Pricing and Forecasting' }))
    expect(await within(cards[0]).findByText("Couldn't withdraw")).toBeInTheDocument()
    expect(within(cards[0]).getByText('The employer has revealed you for this job.')).toBeInTheDocument()
    expect(within(cards[1]).queryByText("Couldn't withdraw")).toBeNull()
  })

  it('offers no withdrawal on a card once revealed', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([progressed('requested')])
    renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    expect(
      await within(cards[0]).findByText('Fjord Grocery ApS revealed you on 27 Nov 2026; the connection stays.'),
    ).toBeInTheDocument()
    expect(within(cards[0]).queryByRole('button', { name: /Withdraw|Connect my profile/ })).toBeNull()
    expect(within(cards[1]).getByRole('button', { name: /^Connect my profile: / })).toBeEnabled()
  })

  it('needs an approved profile to connect from a card', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true, approved: false }))
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([])
    renderApp('/candidates/john-doe/jobs')

    const cards = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')
    for (const card of cards) {
      expect(await within(card).findByRole('button', { name: /^Connect my profile: / })).toBeDisabled()
    }
    expect(screen.getByRole('link', { name: 'go to your review' })).toHaveAttribute('href', '/candidates/john-doe/review')
  })

  it('shows no card actions until the connections load', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockReturnValue(new Promise(() => {}))
    renderApp('/candidates/john-doe/jobs')
    await screen.findByRole('list', { name: 'Jobs' })
    expect(screen.queryByRole('button', { name: /Connect my profile|Withdraw/ })).toBeNull()
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
  it('links each pill to the board filtered by it', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing({ vacancies: 3 }))
    vi.spyOn(api, 'connections').mockResolvedValue([])
    vi.spyOn(api, 'fit').mockResolvedValue(fit({ band: 'good' }))
    const search = vi.spyOn(api, 'board').mockResolvedValue(board())
    const { user, location } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    await screen.findByRole('heading', { level: 1, name: /Senior Data Scientist/ })
    const jobs = '/candidates/john-doe/jobs'
    const links: [string | RegExp, string][] = [
      ['3 vacancies', `${jobs}?min_vacancies=3`],
      ['Senior', `${jobs}?seniority=senior`],
      ['Hybrid', `${jobs}?work_mode=hybrid`],
      ['EU work permit', `${jobs}?work_permit=EU`],
      ['Copenhagen', `${jobs}?location=Copenhagen`],
      ['time series forecasting', `${jobs}?skill=time+series+forecasting`],
      [/Good fit/, `${jobs}?fit=good`],
    ]
    for (const [name, href] of links) expect(screen.getByRole('link', { name })).toHaveAttribute('href', href)
    expect(screen.getByRole('group', { name: 'Named in the ad' })).toHaveTextContent('pythonsqltime series forecasting')
    expect(document.querySelector('main')?.textContent).not.toMatch(HIDDEN)

    await user.click(screen.getByRole('link', { name: 'python' }))
    await waitFor(() => expect(location()).toBe(jobs))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({ skill: ['python'] }))
    const chips = await screen.findByRole('list', { name: 'Active filters' })
    expect(chips).toHaveTextContent('Skill: python')
  })

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

  it('once revealed, says so and offers no withdrawal', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([progressed('revealed')])
    renderApp('/candidates/john-doe/jobs/board-fjord-grocery')
    const region = await screen.findByRole('region', { name: 'Your connection' })
    expect(region).toHaveTextContent('Revealed on 27 Nov 2026')
    expect(region).toHaveTextContent('has seen your name, contact details and the quotes')
    expect(screen.queryByRole('button', { name: 'Withdraw' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Asked to apply' })).toBeNull()
  })

  it('applies with a letter and a file when asked', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    const connections = vi.spyOn(api, 'connections').mockResolvedValue([progressed('requested')])
    const apply = vi.spyOn(api, 'apply').mockResolvedValue(progressed('applied'))
    const { user } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    const asked = await screen.findByRole('region', { name: 'Asked to apply' })
    expect(asked).toHaveTextContent('Fjord Grocery ApS asks you to apply')
    const send = within(asked).getByRole('button', { name: 'Apply' })
    expect(send).toBeDisabled()
    await user.type(within(asked).getByLabelText('Cover letter'), 'I would like to apply.')
    const file = new File(['# John Doe'], 'cv.md', { type: 'text/markdown' })
    await user.upload(within(asked).getByLabelText('Files'), file)
    expect(send).toBeEnabled()

    connections.mockResolvedValue([progressed('applied')])
    await user.click(send)
    expect(apply).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery', 'I would like to apply.', [file])
    const sent = await screen.findByRole('region', { name: 'Your application' })
    expect(sent).toHaveTextContent('You applied')
    expect(sent).toHaveTextContent('I would like to apply.')
    expect(within(sent).getByRole('link', { name: 'cv.md' })).toHaveAttribute(
      'href',
      '/api/candidates/john-doe/applications/board-fjord-grocery/files/3',
    )
    expect(await screen.findByText('Your application is sent to Fjord Grocery ApS.')).toBeInTheDocument()
  })

  it('declines, and says why an answer was refused', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    const connections = vi.spyOn(api, 'connections').mockResolvedValue([progressed('requested')])
    const decline = vi
      .spyOn(api, 'decline')
      .mockRejectedValueOnce(new ApiError(409, 'you already applied for this job'))
      .mockResolvedValueOnce(progressed('declined'))
    const { user } = renderApp('/candidates/john-doe/jobs/board-fjord-grocery')

    const asked = await screen.findByRole('region', { name: 'Asked to apply' })
    await user.click(within(asked).getByRole('button', { name: 'Decline' }))
    expect(await screen.findByText('you already applied for this job')).toBeInTheDocument()

    connections.mockResolvedValue([progressed('declined')])
    await user.click(within(asked).getByRole('button', { name: 'Decline' }))
    expect(decline).toHaveBeenCalledTimes(2)
    expect(await screen.findByRole('region', { name: 'Your application' })).toHaveTextContent('You declined')
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
