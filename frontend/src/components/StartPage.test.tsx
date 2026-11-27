import { screen } from '@testing-library/react'

import { api } from '@/lib/api'
import { candidate, job } from '@/test/fixtures'
import { renderApp } from '@/test/render'

describe('the candidates start page', () => {
  it('lists the candidates to open', async () => {
    vi.spyOn(api, 'candidates').mockResolvedValue(['jane-doe', 'john-doe'])
    renderApp('/candidates')
    expect(await screen.findByRole('link', { name: 'jane-doe' })).toHaveAttribute(
      'href',
      '/candidates/jane-doe/material',
    )
  })

  it('has a friendly empty state pointing to the demo', async () => {
    vi.spyOn(api, 'candidates').mockResolvedValue([])
    renderApp('/candidates')
    expect(await screen.findByText('No candidates yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /John Doe demo/ })).toBeInTheDocument()
  })

  it('makes a typed name valid and creates the candidate', async () => {
    vi.spyOn(api, 'candidates').mockResolvedValue([])
    const jane = candidate({ name: 'jane-doe', demo: false, github: null, material: [] })
    const create = vi.spyOn(api, 'createCandidate').mockResolvedValue(jane)
    vi.spyOn(api, 'candidate').mockResolvedValue(jane)
    const { user, location } = renderApp('/candidates')
    const button = screen.getByRole('button', { name: 'Create' })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Name'), 'Jane Doe')
    expect(screen.getByLabelText('Name')).toHaveValue('jane-doe')
    await user.click(button)
    expect(create).toHaveBeenCalledWith('jane-doe', null)
    expect(await screen.findByRole('heading', { name: 'Your material' })).toBeInTheDocument()
    expect(location()).toBe('/candidates/jane-doe/material')
  })

  it('shows why the list could not load', async () => {
    vi.spyOn(api, 'candidates').mockRejectedValue(new Error('Database is locked'))
    renderApp('/candidates')
    expect(await screen.findByText('Database is locked')).toBeInTheDocument()
  })
})

describe('the home page', () => {
  it('starts a demo and opens it', async () => {
    const create = vi.spyOn(api, 'createDemoJob').mockResolvedValue(job())
    vi.spyOn(api, 'job').mockResolvedValue(job({ has_rubric: false, history: [] }))
    const { user, location } = renderApp('/')
    await user.click(screen.getByRole('button', { name: /Fjord Grocery demo/ }))
    expect(create).toHaveBeenCalled()
    expect(await screen.findByRole('heading', { name: 'The job ad' })).toBeInTheDocument()
    expect(location()).toBe('/jobs/fjord-grocery/ad')
  })

  it('says when a page does not exist', () => {
    renderApp('/nowhere')
    expect(screen.getByText("There's nothing here")).toBeInTheDocument()
  })
})
