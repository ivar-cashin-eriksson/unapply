import { fireEvent, screen, within } from '@testing-library/react'

import { placeAmong } from '@/lib/format'
import { api } from '@/lib/api'
import { candidate, candidateJobs, dashboard } from '@/test/fixtures'
import { renderApp } from '@/test/render'

// The assessment and the rubric: neither is ever shown on a candidate page.
const HIDDEN_FROM_CANDIDATES = /estimat|confidence|claim support|overclaim|rubric|criteri|weight|min.?level/i

function open(data = dashboard(), jobs = candidateJobs()) {
  vi.spyOn(api, 'candidate').mockResolvedValue(
    candidate({ has_profile: true, approved: true, history: ['extracted', 'reviewed'] }),
  )
  const get = vi.spyOn(api, 'dashboard').mockResolvedValue(data)
  const getJobs = vi.spyOn(api, 'candidateJobs').mockResolvedValue(jobs)
  const rendered = renderApp('/candidates/john-doe/dashboard')
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

describe('your jobs on the dashboard', () => {
  it('shows each job with its stage and fit, and the success rate', async () => {
    const { getJobs } = open()
    const jobs = await screen.findByRole('list', { name: 'Jobs you connected to' })
    expect(getJobs).toHaveBeenCalledWith('john-doe')
    const rows = within(jobs).getAllByRole('listitem').filter((li) => li.parentElement === jobs)
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
  })

  it('names the skills common among those revealed, where they were not', async () => {
    open()
    const group = await screen.findByRole('group', { name: /Common among those revealed: Junior Data Scientist/ })
    expect(within(group).getByRole('list', { name: 'Not in your profile' })).toHaveTextContent('kafkadbt')
    expect(within(group).getByRole('list', { name: 'You rated lower than most of them' })).toHaveTextContent('sql')
    // Too few revealed: only a note, and nothing for a job where they were revealed.
    expect(screen.getAllByText(/show once at least 5 others are revealed/)).toHaveLength(1)
    expect(screen.getAllByRole('group', { name: /Common among those revealed/ })).toHaveLength(1)
  })

  it('points to the board before any connection', async () => {
    open(
      dashboard(),
      candidateJobs({ jobs: [], connected: 0, revealed: 0, requested: 0, revealed_rate: null, requested_rate: null }),
    )
    expect(await screen.findByText(/You haven't connected to a job yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'job board' })).toHaveAttribute('href', '/candidates/john-doe/jobs')
    expect(screen.queryByLabelText('Your success rate')).toBeNull()
  })

  it('never shows a level, weight or other assessment word in the jobs', async () => {
    open()
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
