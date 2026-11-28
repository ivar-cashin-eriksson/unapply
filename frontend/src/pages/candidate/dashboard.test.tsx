import { fireEvent, screen, within } from '@testing-library/react'

import { placeAmong } from '@/lib/format'
import { api } from '@/lib/api'
import { candidate, candidateJobs, dashboard } from '@/test/fixtures'
import { renderApp } from '@/test/render'

// The assessment and the rubric: neither is ever shown on a candidate page.
const HIDDEN_FROM_CANDIDATES = /estimat|confidence|claim support|overclaim|rubric|criteri|weight|min.?level/i

function open(data = dashboard(), jobs = candidateJobs(), sheet = '') {
  vi.spyOn(api, 'candidate').mockResolvedValue(
    candidate({ has_profile: true, approved: true, history: ['extracted', 'reviewed'] }),
  )
  const get = vi.spyOn(api, 'dashboard').mockResolvedValue(data)
  const getJobs = vi.spyOn(api, 'candidateJobs').mockResolvedValue(jobs)
  const rendered = renderApp(`/candidates/john-doe/dashboard${sheet && `?sheet=${sheet}`}`)
  return { get, getJobs, ...rendered }
}

describe('the dashboard', () => {
  it('shows the skills by area with own levels and how often the material mentions each', async () => {
    const { get } = open()
    expect(await screen.findByRole('heading', { name: 'Your dashboard' })).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('john-doe')
    const tech = await screen.findByRole('list', { name: 'Technology' })
    const rows = within(tech).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('python')
    expect(rows[0]).toHaveTextContent('4 quotes from your documents')
    expect(rows[1]).toHaveTextContent('2 quotes from your documents, 1 of your statements')
    expect(within(screen.getByRole('list', { name: 'Domain' })).getByText('Not rated')).toBeInTheDocument()
    const numbers = screen.getByLabelText('Your profile in numbers')
    expect(numbers).toHaveTextContent('Compared with12other candidates')
  })

  it("compares with others' own levels only where enough rated the skill", async () => {
    open()
    const chart = await screen.findByRole('img', { name: /Other candidates' own levels in python/ })
    expect(chart).toHaveAccessibleName(expect.stringContaining('Median 4 of 9 others'))
    expect(screen.getByText('Others: 3 lower, 4 the same, 2 higher')).toBeInTheDocument()
    expect(screen.getAllByTestId('own-level')).toHaveLength(1)
    fireEvent.mouseEnter(screen.getByTestId('level-5'))
    expect(screen.getByText('5 Expert: 2 others')).toBeInTheDocument()
    expect(screen.getAllByText('Fewer than 5 others rated it')).toHaveLength(2)
  })

  it('compares nothing with fewer than five others', async () => {
    open(
      dashboard({
        compared_with: 0,
        areas: [
          {
            category: 'technology',
            skills: [{ name: 'python', self_level: 4, documents: 4, statements: 0, comparison: null }],
          },
        ],
      }),
    )
    expect(await screen.findByText(/Comparisons appear once at least 5 other candidates/)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /own levels/ })).toBeNull()
    expect(screen.queryByText(/Fewer than 5 others/)).toBeNull()
  })

  it('suggests skills from the board and the taxonomy', async () => {
    open()
    const board = await screen.findByRole('list', { name: 'Asked for on the job board' })
    expect(within(board).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['excel', 'databricks'])
    expect(screen.getByRole('list', { name: 'Follow from your skills' })).toHaveTextContent(
      'gradient boosting · from lightgbm',
    )
  })

  it('never shows an assessment word or anything from a rubric', async () => {
    open()
    await screen.findByRole('heading', { name: 'Your dashboard' })
    expect(document.body.textContent).not.toMatch(HIDDEN_FROM_CANDIDATES)
  })

  it('is locked until there is a profile', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate())
    const get = vi.spyOn(api, 'dashboard')
    renderApp('/candidates/john-doe/dashboard')
    expect(await screen.findByText('No profile yet')).toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
  })
})

describe('the sheets of the dashboard', () => {
  it('opens on the profile and switches sheets', async () => {
    open()
    expect(await screen.findByRole('list', { name: 'Technology' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Jobs you connected to' })).toBeNull()
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Your jobs' }))
    expect(await screen.findByRole('list', { name: 'Jobs you connected to' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Technology' })).toBeNull()
  })
})

describe('your jobs on the dashboard', () => {
  it('shows each job with its stage and fit, and the success rate', async () => {
    const { getJobs } = open(dashboard(), candidateJobs(), 'jobs')
    const jobs = await screen.findByRole('list', { name: 'Jobs you connected to' })
    expect(getJobs).toHaveBeenCalledWith('john-doe')
    const rows = within(jobs).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('Smørblomst Mejeri')
    expect(rows[0]).toHaveTextContent('Good fit')
    expect(rows[0]).toHaveTextContent('Connected')
    expect(rows[1]).toHaveTextContent('Asked to apply')
    expect(rows[1]).toHaveTextContent('Strong fit')
    expect(rows[2]).toHaveTextContent('No longer on the board')
    expect(within(rows[1]).getByRole('link', { name: /Senior Data Scientist/ })).toHaveAttribute(
      'href',
      '/candidates/john-doe/jobs/board-fjord-grocery',
    )
    const rate = screen.getByLabelText('Your success rate')
    expect(rate).toHaveTextContent('Connected3jobs')
    expect(rate).toHaveTextContent('Revealed33%1 of 3')
    expect(rate).toHaveTextContent('Asked to apply33%1 of 3')
    // Only a job with a group to compare with links to the comparison.
    expect(screen.getAllByRole('button', { name: /Compare with others/ })).toHaveLength(1)
  })

  it('points to the board before any connection', async () => {
    open(
      dashboard(),
      candidateJobs({ jobs: [], connected: 0, revealed: 0, requested: 0, revealed_rate: null, requested_rate: null }),
      'jobs',
    )
    expect(await screen.findByText(/You haven't connected to a job yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'job board' })).toHaveAttribute('href', '/candidates/john-doe/jobs')
    expect(screen.queryByLabelText('Your success rate')).toBeNull()
  })
})

describe('compared on jobs', () => {
  it('opens the comparison for a job from its row', async () => {
    open(dashboard(), candidateJobs(), 'jobs')
    fireEvent.click(await screen.findByRole('button', { name: 'Compare with others: Junior Data Scientist' }))
    expect(await screen.findByRole('group', { name: 'Compared with: Revealed' })).toBeInTheDocument()
    expect(screen.getByLabelText('Job')).toHaveValue('board-smoerblomst-dairy')
  })

  it('shows where the candidate stands out and where the others are ahead', async () => {
    open(dashboard(), candidateJobs(), 'compare')
    const group = await screen.findByRole('group', { name: 'Compared with: Revealed' })
    expect(within(group).getByRole('list', { name: 'You rated higher than most of them' })).toHaveTextContent('python')
    expect(within(group).getByRole('list', { name: 'You list, few of them do' })).toHaveTextContent('lightgbm')
    expect(within(group).getByRole('list', { name: 'Not in your profile' })).toHaveTextContent('kafkadbt')
    expect(within(group).getByRole('list', { name: 'You rated lower than most of them' })).toHaveTextContent('sql')
  })

  it('draws a spider chart of own levels against the group median, with a table', async () => {
    open(dashboard(), candidateJobs(), 'compare')
    expect(await screen.findByRole('img', { name: /Your own levels and the median of revealed in 4 skills/ })).toBeVisible()
    expect(screen.getByTestId('shape-you')).toBeInTheDocument()
    expect(screen.getByTestId('shape-group')).toBeInTheDocument()
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('python43')
    expect(rows[3]).toHaveTextContent('kafka–3.5')
  })

  it('switches between the groups there are enough of', async () => {
    open(dashboard(), candidateJobs(), 'compare')
    await screen.findByRole('group', { name: 'Compared with: Revealed' })
    const groups = screen.getByLabelText('Compare with')
    expect(within(groups).getByRole('radio', { name: 'Applied' })).toBeDisabled()
    expect(within(groups).getByRole('radio', { name: 'Applied' })).toHaveAccessibleDescription('Fewer than 5 others')
    fireEvent.click(within(groups).getByRole('radio', { name: 'Asked to apply' }))
    const group = await screen.findByRole('group', { name: 'Compared with: Asked to apply' })
    expect(within(group).queryByRole('list', { name: 'You rated higher than most of them' })).toBeNull()
    expect(within(group).getByRole('list', { name: 'You list, few of them do' })).toHaveTextContent(
      'lightgbmretail analytics',
    )
  })

  it('explains the group-size rule when there is nothing to compare', async () => {
    const jobs = candidateJobs()
    open(dashboard(), { ...jobs, jobs: jobs.jobs.map((j) => ({ ...j, groups: [] })) }, 'compare')
    expect(await screen.findByText(/Nothing to compare yet/)).toHaveTextContent('at least 5 others')
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('never shows an assessment word or anything from a rubric', async () => {
    open(dashboard(), candidateJobs(), 'compare')
    await screen.findByRole('group', { name: 'Compared with: Revealed' })
    expect(document.body.textContent).not.toMatch(HIDDEN_FROM_CANDIDATES)
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Your jobs' }))
    await screen.findByRole('list', { name: 'Jobs you connected to' })
    expect(document.body.textContent).not.toMatch(HIDDEN_FROM_CANDIDATES)
  })
})

describe('placeAmong', () => {
  it('counts the others below, at and above a level', () => {
    expect(placeAmong([1, 2, 3, 4, 5], 1)).toBe('0 lower, 1 the same, 14 higher')
    expect(placeAmong([1, 2, 3, 4, 5], 5)).toBe('10 lower, 5 the same, 0 higher')
  })
})
