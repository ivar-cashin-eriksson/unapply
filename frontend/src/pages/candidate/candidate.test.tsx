import { screen, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { ReviewForm } from '@/lib/types'
import { candidate, profile, questions, reviewForm } from '@/test/fixtures'
import { renderApp } from '@/test/render'

// Words for the assessment, which a candidate never sees.
const ASSESSMENT = /estimat|confidence|claim support|overclaim/i

// The profile page asks for the contact details shown when revealed.
beforeEach(() => {
  vi.spyOn(api, 'contact').mockResolvedValue({ name: 'John Doe', email: null, phone: null })
})

describe('the steps', () => {
  it('locks the steps that need an earlier one', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ demo: false }))
    renderApp('/candidates/john-doe/material')
    const steps = await screen.findByRole('navigation', { name: 'Your steps' })
    expect(within(steps).getByRole('link', { name: /Material/ })).toBeInTheDocument()
    for (const step of ['Review', 'Questions', 'Profile']) {
      expect(within(steps).queryByRole('link', { name: new RegExp(step) })).toBeNull()
      expect(within(steps).getByText(step)).toBeInTheDocument()
    }
  })

  it('marks finished steps as done', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(
      candidate({ has_profile: true, approved: true, history: ['extracted', 'approved', 'interviewed'] }),
    )
    vi.spyOn(api, 'profile').mockResolvedValue(profile())
    renderApp('/candidates/john-doe/profile')
    const steps = await screen.findByRole('navigation', { name: 'Your steps' })
    expect(within(steps).getByRole('link', { name: /^Questions\s*\(done\)$/ })).toBeInTheDocument()
  })

  it('says when a candidate cannot be opened', async () => {
    vi.spyOn(api, 'candidate').mockRejectedValue(new ApiError(404, 'No candidate called nobody.'))
    renderApp('/candidates/nobody')
    expect(await screen.findByText("Couldn't open nobody")).toBeInTheDocument()
    expect(screen.getByText('No candidate called nobody.')).toBeInTheDocument()
  })
})

describe('material', () => {
  it('keeps the demo material fixed and builds the profile for free', async () => {
    const summary = vi
      .spyOn(api, 'candidate')
      .mockResolvedValueOnce(candidate())
      .mockResolvedValue(candidate({ has_profile: true, history: ['extracted'] }))
    const extract = vi.spyOn(api, 'extract').mockResolvedValue({
      profile: profile({ approved_by_candidate_at: null }),
      rejected_quotes: 0,
      unsupported: [],
    })
    vi.spyOn(api, 'review').mockResolvedValue(reviewForm())
    const { user, location } = renderApp('/candidates/john-doe/material')

    expect(await screen.findByText('This is the John Doe demo')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Upload files' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Remove cv.md' })).toBeNull()
    expect(screen.getByText('cv.md')).toBeInTheDocument()
    // The demo's files can't change, but they can still be downloaded.
    const download = screen.getByRole('link', { name: 'Download cv.md' })
    expect(download).toHaveAttribute('href', '/api/candidates/john-doe/material/cv.md')
    expect(download).toHaveAttribute('download', 'cv.md')
    expect(screen.getByLabelText('GitHub username')).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Build my profile' }))
    expect(extract).toHaveBeenCalledWith('john-doe')
    expect(await screen.findByRole('heading', { name: 'Review your profile' })).toBeInTheDocument()
    expect(location()).toBe('/candidates/john-doe/review')
    expect(summary).toHaveBeenCalledTimes(2)
  })

  it('uploads dropped files and lists them', async () => {
    vi.spyOn(api, 'candidate')
      .mockResolvedValueOnce(candidate({ demo: false, github: null, material: [] }))
      .mockResolvedValue(candidate({ demo: false, github: null, material: [{ name: 'cv.md', size: 4 }] }))
    const upload = vi.spyOn(api, 'upload').mockResolvedValue([{ name: 'cv.md', size: 4 }])
    const { user } = renderApp('/candidates/jane/material')

    expect(await screen.findByText(/No files yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Build my profile' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Build my profile' })).toHaveAccessibleDescription(
      'Add a file or your GitHub first',
    )
    await user.upload(screen.getByTestId('file-input'), new File(['# CV'], 'cv.md'))
    expect(upload).toHaveBeenCalledWith('jane', [expect.objectContaining({ name: 'cv.md' })])
    expect(await screen.findByRole('button', { name: 'Remove cv.md' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Build my profile' })).toBeEnabled()
  })

  it('explains a refused paid call', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ demo: false }))
    vi.spyOn(api, 'extract').mockRejectedValue(new ApiError(403, 'Paid API calls are disabled.'))
    const { user } = renderApp('/candidates/jane/material')
    await user.click(await screen.findByRole('button', { name: 'Build my profile' }))
    expect(await screen.findByText(/paid calls are off on this server/)).toBeInTheDocument()
  })
})

describe('review', () => {
  function openReview(form = reviewForm()) {
    const summary = candidate({ has_profile: true, history: ['extracted'] })
    vi.spyOn(api, 'candidate').mockResolvedValue(summary)
    vi.spyOn(api, 'review').mockResolvedValue(form)
    return renderApp('/candidates/john-doe/review')
  }

  it('rates and removes skills, approves, and saves the whole form', async () => {
    const save = vi.spyOn(api, 'saveReview').mockResolvedValue(profile())
    vi.spyOn(api, 'questions').mockResolvedValue(questions())
    const { user, location } = openReview()
    // Once saved, the summary says the profile is approved.
    vi.mocked(api.candidate).mockResolvedValue(
      candidate({ has_profile: true, approved: true, history: ['extracted', 'approved'] }),
    )

    const python = await screen.findByRole('radiogroup', { name: 'Your level in python' })
    await user.click(within(python).getByRole('radio', { name: '3 Working' }))
    await user.click(screen.getByRole('checkbox', { name: 'Keep cobol' }))
    expect(screen.getByText(/2 of 2 skills rated/)).toBeInTheDocument()
    await user.click(screen.getByLabelText(/I approve this profile/))
    await user.click(screen.getByRole('button', { name: 'Save and approve' }))

    const sent = save.mock.calls[0][1] as ReviewForm
    expect(sent.approve).toBe(true)
    expect(sent.skills.find((s) => s.name === 'python')?.level).toBe(3)
    expect(sent.skills.find((s) => s.name === 'cobol')?.keep).toBe(false)
    expect(sent.skills.find((s) => s.name === 'forecasting')?.level).toBe(4)
    expect(await screen.findByRole('heading', { name: 'A few questions' })).toBeInTheDocument()
    expect(location()).toBe('/candidates/john-doe/questions')
  })

  it('filters skills by name', async () => {
    const { user } = openReview()
    await user.type(await screen.findByLabelText('Filter skills'), 'fore')
    expect(screen.getByRole('checkbox', { name: 'Keep forecasting' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Keep python' })).toBeNull()
    await user.clear(screen.getByLabelText('Filter skills'))
    await user.type(screen.getByLabelText('Filter skills'), 'rust')
    expect(screen.getByText('No skill matches “rust”.')).toBeInTheDocument()
  })

  it('shows the quotes behind a skill when asked', async () => {
    const { user } = openReview()
    const python = (await screen.findByRole('checkbox', { name: 'Keep python' })).closest('li')!
    const toggle = within(python).getByRole('button', { name: /From your material: 1 quote/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(within(python).getByText('“Python (pandas, scikit-learn)”')).toBeInTheDocument()
    expect(within(screen.getByRole('checkbox', { name: 'Keep cobol' }).closest('li')!).getByText(/your own statement/)).toBeInTheDocument()
  })

  it('edits experience and preferences, and adds a skill', async () => {
    const save = vi.spyOn(api, 'saveReview').mockResolvedValue(profile({ approved_by_candidate_at: null }))
    const { user } = openReview()

    await user.click(await screen.findByRole('tab', { name: /Experience/ }))
    const end = screen.getByLabelText('End')
    await user.type(end, '2024-06')
    await user.click(screen.getByRole('tab', { name: /Preferences/ }))
    const locations = screen.getByLabelText('Locations')
    await user.clear(locations)
    await user.type(locations, 'Copenhagen, Aarhus')
    await user.click(screen.getByRole('button', { name: 'Remote' }))
    // Skills are added in the Skills tab, next to the ones found; there is no other tab.
    expect(screen.queryByRole('tab', { name: /Add skills/ })).toBeNull()
    await user.click(screen.getByRole('tab', { name: /Skills/ }))
    await user.click(screen.getByRole('button', { name: 'Add a skill' }))
    await user.type(screen.getByLabelText('Skill'), 'matlab')
    const level = screen.getByRole('radiogroup', { name: 'Your level in matlab' })
    await user.click(within(level).getByRole('radio', { name: /^3 / }))
    await user.type(screen.getByLabelText('Where you used it'), 'Thesis, 2018')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const sent = save.mock.calls[0][1] as ReviewForm
    expect(sent.approve).toBe(false)
    expect(sent.experiences[0].end).toBe('2024-06')
    expect(sent.preferences.locations).toEqual(['Copenhagen', 'Aarhus'])
    expect(sent.preferences.work_modes).toEqual(['hybrid', 'remote'])
    expect(sent.add_skills).toEqual([{ name: 'matlab', category: 'technology', level: 3, note: 'Thesis, 2018' }])
  })

  it("fills in John's review in the demo", async () => {
    const filled = reviewForm({ approve: true, headline: 'Filled in' })
    vi.spyOn(api, 'demoReview').mockResolvedValue(filled)
    const { user } = openReview()
    await user.click(await screen.findByRole('button', { name: "Fill in John's review" }))
    expect(screen.getByLabelText('Headline')).toHaveValue('Filled in')
    expect(screen.getByRole('button', { name: 'Save and approve' })).toBeInTheDocument()
  })

  it('shows why a review was refused', async () => {
    vi.spyOn(api, 'saveReview').mockRejectedValue(
      new ApiError(422, 'add_skills: matlab needs a note saying where you used it.'),
    )
    const { user } = openReview()
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByText("Couldn't save your review")).toBeInTheDocument()
    expect(screen.getByText(/needs a note/)).toBeInTheDocument()
  })

  it('points to the material when there is no profile yet', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate())
    renderApp('/candidates/john-doe/review')
    expect(await screen.findByText('No profile to review yet')).toBeInTheDocument()
  })

  it('shows no assessment', async () => {
    openReview()
    await screen.findByRole('heading', { name: 'Review your profile' })
    expect(document.body.textContent).not.toMatch(ASSESSMENT)
  })
})

describe('questions', () => {
  function openQuestions(data = questions(), history = ['extracted', 'approved']) {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true, approved: true, history }))
    vi.spyOn(api, 'questions').mockResolvedValue(data)
    vi.spyOn(api, 'profile').mockResolvedValue(profile())
    return renderApp('/candidates/john-doe/questions')
  }

  it('sends only the questions answered', async () => {
    const answer = vi.spyOn(api, 'answer').mockResolvedValue({ answered: 1 })
    const { user, location } = openQuestions()
    const send = await screen.findByRole('button', { name: /Send/ })
    expect(send).toBeDisabled()
    expect(screen.getByText('Tell us about a SQL query you wrote that you are proud of.')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/SQL query/), 'A churn model in BigQuery.')
    expect(screen.getByRole('button', { name: 'Send 1 answer' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Send 1 answer' }))
    expect(answer).toHaveBeenCalledWith('john-doe', { answers: { sql: 'A churn model in BigQuery.' } })
    expect(await screen.findByRole('heading', { name: 'Data scientist in retail forecasting' })).toBeInTheDocument()
    expect(location()).toBe('/candidates/john-doe/profile')
  })

  it("fills in John's answers in the demo", async () => {
    vi.spyOn(api, 'demoAnswers').mockResolvedValue({ answers: { sql: 'S', spark: 'P' } })
    const { user } = openQuestions()
    await user.click(await screen.findByRole('button', { name: "Fill in John's answers" }))
    expect(screen.getByRole('button', { name: 'Send 2 answers' })).toBeEnabled()
  })

  it('prepares questions, and says when there are none', async () => {
    const prepare = vi
      .spyOn(api, 'prepareQuestions')
      .mockResolvedValueOnce(questions({ waiting: [] }))
      .mockResolvedValueOnce(questions())
    const { user } = openQuestions(questions({ waiting: [] }))
    await user.click(await screen.findByRole('button', { name: 'Prepare my questions' }))
    expect(await screen.findByText('No questions for now')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Prepare my questions' }))
    expect(await screen.findByText('Where have you used Spark, and on how much data?')).toBeInTheDocument()
    expect(prepare).toHaveBeenCalledTimes(2)
  })

  it('shows earlier answers, and offers more questions', async () => {
    openQuestions(
      questions({ waiting: [], answered: [{ skill: 'sql', text: 'About SQL?', answer: 'Lots of it.' }] }),
      ['extracted', 'approved', 'interviewed'],
    )
    expect(await screen.findByText('Lots of it.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask me more questions' })).toBeInTheDocument()
    expect(screen.getByText(/You can ask for that assessment at any time/)).toBeInTheDocument()
  })

  it('waits for an approved profile', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true }))
    renderApp('/candidates/john-doe/questions')
    expect(await screen.findByText('Approve your profile first')).toBeInTheDocument()
  })
})

describe('profile', () => {
  it('shows the profile as employers will see it, without any assessment', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true, approved: true, history: ['approved'] }))
    vi.spyOn(api, 'profile').mockResolvedValue(profile())
    renderApp('/candidates/john-doe/profile')

    expect(await screen.findByRole('heading', { name: 'Data scientist in retail forecasting' })).toBeInTheDocument()
    expect(screen.getByText('Mar 2020 – now')).toBeInTheDocument()
    expect(screen.getByText('5 Expert')).toBeInTheDocument()
    expect(screen.getByText('Not rated')).toBeInTheDocument()
    expect(screen.getByText('Copenhagen')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(ASSESSMENT)
  })

  it('sets the contact details an employer sees once they reveal you', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(
      candidate({ demo: false, has_profile: true, approved: true, history: ['approved'] }),
    )
    vi.spyOn(api, 'profile').mockResolvedValue(profile())
    const save = vi
      .spyOn(api, 'saveContact')
      .mockResolvedValue({ name: 'John Doe', email: 'john@example.org', phone: null })
    const { user } = renderApp('/candidates/john-doe/profile')
    const card = await screen.findByRole('region', { name: 'Shown when revealed' })
    expect(await within(card).findByLabelText('Full name')).toHaveValue('John Doe')
    await user.type(within(card).getByLabelText('Email'), 'john@example.org')
    await user.click(within(card).getByRole('button', { name: 'Save' }))
    expect(save).toHaveBeenCalledWith('john-doe', { name: 'John Doe', email: 'john@example.org', phone: null })
    expect(await screen.findByText('Your contact details are saved.')).toBeInTheDocument()
  })

  it('shows a demo candidate their details from the CV, read-only', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(
      candidate({ demo: true, has_profile: true, approved: true, history: ['approved'] }),
    )
    vi.spyOn(api, 'profile').mockResolvedValue(profile())
    renderApp('/candidates/john-doe/profile')
    const card = await screen.findByRole('region', { name: 'Shown when revealed' })
    expect(await within(card).findByText('John Doe')).toBeInTheDocument()
    expect(within(card).queryByRole('textbox')).toBeNull()
    expect(card).toHaveTextContent('In the demo, these come from the CV.')
  })

  it('says a draft is not seen by employers yet', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(candidate({ has_profile: true, history: ['extracted'] }))
    vi.spyOn(api, 'profile').mockResolvedValue(profile({ approved_by_candidate_at: null }))
    renderApp('/candidates/john-doe/profile')
    expect(await screen.findByText('Not approved yet')).toBeInTheDocument()
  })
})
