import { screen, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { RubricForm } from '@/lib/types'
import { job, rubric } from '@/test/fixtures'
import { renderApp } from '@/test/render'

describe('job ad', () => {
  it('keeps the demo ad fixed and drafts the rubric for free', async () => {
    vi.spyOn(api, 'job')
      .mockResolvedValueOnce(job({ has_rubric: false, history: [] }))
      .mockResolvedValue(job())
    const setAd = vi.spyOn(api, 'setAd')
    const extract = vi.spyOn(api, 'extractRubric').mockResolvedValue({
      job: {
        id: 'job-1',
        company: 'Fjord Grocery',
        title: 'Senior Data Scientist',
        ad_text: '',
        rubric: rubric(),
        reveal_quota: 5,
        created_at: '2026-11-01T10:00:00Z',
      },
      dropped: [],
    })
    vi.spyOn(api, 'rubric').mockResolvedValue(rubric())
    const { user, location } = renderApp('/jobs/fjord-grocery/ad')

    expect(await screen.findByText('This is the Fjord Grocery demo')).toBeInTheDocument()
    expect(screen.getByLabelText('Ad')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Job title')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Draft the rubric' }))
    expect(setAd).not.toHaveBeenCalled()
    expect(extract).toHaveBeenCalledWith('fjord-grocery')
    expect(await screen.findByRole('heading', { name: 'Rubric' })).toBeInTheDocument()
    expect(location()).toBe('/jobs/fjord-grocery/rubric')
  })

  it('saves an edited ad before drafting', async () => {
    const empty = job({ name: 'analyst', demo: false, ad: { ad: '', company: null, title: null }, has_rubric: false, history: [] })
    vi.spyOn(api, 'job').mockResolvedValue(empty)
    const setAd = vi.spyOn(api, 'setAd').mockResolvedValue(empty)
    vi.spyOn(api, 'extractRubric').mockRejectedValue(new ApiError(403, 'Paid API calls are disabled.'))
    const { user } = renderApp('/jobs/analyst/ad')

    const draft = await screen.findByRole('button', { name: 'Draft the rubric' })
    expect(draft).toBeDisabled()
    await user.type(screen.getByLabelText('Ad'), 'Analyst wanted in Oslo.')
    await user.type(screen.getByLabelText('Company'), 'Acme')
    await user.click(draft)
    expect(setAd).toHaveBeenCalledWith('analyst', { ad: 'Analyst wanted in Oslo.', company: 'Acme', title: null })
    expect(await screen.findByText("Couldn't draft the rubric")).toBeInTheDocument()
    expect(screen.getByText(/paid calls are off on this server/)).toBeInTheDocument()
  })

  it('locks the rubric step until there is one', async () => {
    vi.spyOn(api, 'job').mockResolvedValue(job({ has_rubric: false, history: [] }))
    renderApp('/jobs/fjord-grocery/ad')
    const steps = await screen.findByRole('navigation', { name: 'Job steps' })
    expect(within(steps).queryByRole('link', { name: /Rubric/ })).toBeNull()
  })
})

describe('rubric editor', () => {
  function openRubric(data = rubric()) {
    vi.spyOn(api, 'job').mockResolvedValue(job())
    vi.spyOn(api, 'rubric').mockResolvedValue(data)
    return renderApp('/jobs/fjord-grocery/rubric')
  }

  it('shows the hard filters and criteria with the quotes from the ad', async () => {
    openRubric()
    expect(await screen.findByDisplayValue('Strong Python')).toBeInTheDocument()
    expect(screen.getByText('“Python and SQL required”')).toBeInTheDocument()
    expect(screen.getByText('Added by you: no quote from the ad.')).toBeInTheDocument()
    expect(screen.getByLabelText('Locations')).toHaveValue('Copenhagen')
    expect(screen.getByLabelText('Minimum years of experience')).toHaveValue('4')
    expect(screen.getByText('Version 1')).toBeInTheDocument()
    expect(screen.getByText('Draft')).toBeInTheDocument()
    const must = screen.getByRole('region', { name: 'Must-haves' })
    expect(within(must).getByDisplayValue('Strong Python')).toBeInTheDocument()
    const nice = screen.getByRole('region', { name: 'Nice-to-haves' })
    expect(within(nice).getByDisplayValue('Spark experience')).toBeInTheDocument()
  })

  it('edits, removes and adds criteria, approves, and saves the whole form', async () => {
    const save = vi.spyOn(api, 'saveRubric').mockResolvedValue(rubric({ version: 2, approved_at: '2026-11-02T10:00:00Z' }))
    const { user } = openRubric()

    const weight = await screen.findByRole('radiogroup', { name: 'Weight of Strong Python' })
    await user.click(within(weight).getByRole('radio', { name: '3 medium' }))
    await user.click(screen.getByRole('button', { name: 'Remove Spark experience' }))
    expect(screen.getByRole('button', { name: 'Keep Spark experience' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add a nice-to-have' }))
    await user.type(screen.getAllByPlaceholderText('What is asked for').at(-1)!, 'Danish')
    const years = screen.getByLabelText('Minimum years of experience')
    await user.clear(years)
    await user.type(years, '5y')
    await user.click(screen.getByLabelText(/I approve this rubric/))
    await user.click(screen.getByRole('button', { name: 'Save and approve' }))

    const sent = save.mock.calls[0][1] as RubricForm
    expect(sent.approve).toBe(true)
    expect(sent.company).toBe('Fjord Grocery')
    expect(sent.hard_filters.min_years_experience).toBe(5)
    expect(sent.criteria).toEqual([
      expect.objectContaining({ id: 'c-python', keep: true, weight: 3, min_level: 4 }),
      expect.objectContaining({ id: 'c-spark', keep: false }),
      { id: null, keep: true, kind: 'nice_to_have', description: 'Danish', skill: null, min_level: null, weight: 3 },
    ])
  })

  it('drops a new criterion outright when removed', async () => {
    const save = vi.spyOn(api, 'saveRubric').mockResolvedValue(rubric({ version: 2 }))
    const { user } = openRubric()
    await user.click(await screen.findByRole('button', { name: 'Add a must-have' }))
    await user.click(screen.getByRole('button', { name: 'Remove the new criterion' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect((save.mock.calls[0][1] as RubricForm).criteria).toHaveLength(2)
  })

  it('shows why a rubric could not be saved, such as a locked version', async () => {
    vi.spyOn(api, 'saveRubric').mockRejectedValue(
      new ApiError(409, 'Rubric version 1 was matched against, so it can no longer change.'),
    )
    const { user } = openRubric()
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByText("Couldn't save the rubric")).toBeInTheDocument()
    expect(screen.getByText(/can no longer change/)).toBeInTheDocument()
  })

  it('points to the ad when there is no rubric yet', async () => {
    vi.spyOn(api, 'job').mockResolvedValue(job({ has_rubric: false, history: [] }))
    renderApp('/jobs/fjord-grocery/rubric')
    expect(await screen.findByText('No rubric yet')).toBeInTheDocument()
  })
})
