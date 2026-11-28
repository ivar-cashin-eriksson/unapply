import { screen, waitFor, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { CandidateAnswer, Shortlist } from '@/lib/types'
import { job, revealed, shortlist } from '@/test/fixtures'
import { renderApp } from '@/test/render'

const PRODUCTION = 'Has this candidate deployed models to production?'
const TEAM = 'Has this candidate managed a team?'

function answer(question: string, patch: Partial<CandidateAnswer> = {}): CandidateAnswer {
  return {
    question,
    answer: 'Yes. Her forecasts run in production.',
    answered: true,
    evidence: [{ id: 'e1', source: 'cv', quote: 'Built forecasts in Python, in production since 2022.' }],
    model: 'replay:hand-written placeholder',
    problems: [],
    asked_at: '2026-11-28T10:00:00',
    ...patch,
  }
}

function open(data: Shortlist) {
  vi.spyOn(api, 'job').mockResolvedValue(job({ approved: true, history: ['extracted', 'rubric'] }))
  vi.spyOn(api, 'shortlist').mockResolvedValue(data)
  return renderApp('/jobs/fjord-grocery/shortlist')
}

function withKim(): { data: Shortlist; id: string } {
  const data = shortlist()
  data.candidates[0] = revealed(data.candidates[0])
  return { data, id: data.candidates[0].profile_id }
}

describe('asking about a revealed candidate', () => {
  it('is offered only for revealed candidates', async () => {
    const options = vi.spyOn(api, 'askOptions')
    const { data } = withKim()
    open(data)
    await screen.findByRole('heading', { name: /Kim Berg/ })
    expect(screen.getAllByRole('button', { name: /^Ask about/ })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Ask about Kim Berg' })).toBeInTheDocument()
    // Nothing is loaded until the questions are opened.
    expect(options).not.toHaveBeenCalled()
  })

  it('answers the demo questions with their quotes, and sends the conversation along', async () => {
    const { data, id } = withKim()
    vi.spyOn(api, 'askOptions').mockResolvedValue({ suggested: [PRODUCTION, TEAM] })
    const ask = vi
      .spyOn(api, 'ask')
      .mockResolvedValueOnce(answer(PRODUCTION))
      .mockResolvedValueOnce(
        answer(TEAM, { answered: false, answer: 'Nothing in the material says she has managed a team.', evidence: [] }),
      )
    const { user } = open(data)
    const kim = (await screen.findByRole('heading', { name: /Kim Berg/ })).closest('li') as HTMLElement

    await user.click(within(kim).getByRole('button', { name: 'Ask about Kim Berg' }))
    const region = await within(kim).findByRole('region', { name: 'Questions about Kim Berg' })
    expect(region).toHaveTextContent("Answers come from Kim Berg's own material only")
    expect(region).toHaveTextContent('Nothing is saved')
    const suggested = within(region).getByRole('group', { name: 'Suggested questions' })

    await user.click(within(suggested).getByRole('button', { name: PRODUCTION }))
    expect(ask).toHaveBeenLastCalledWith('fjord-grocery', id, PRODUCTION, [])
    const answers = await within(region).findByRole('list', { name: 'Answers' })
    expect(answers).toHaveTextContent('Yes. Her forecasts run in production.')
    expect(answers).toHaveTextContent('Built forecasts in Python, in production since 2022. (cv)')
    expect(within(answers).queryByText("The material doesn't answer this")).toBeNull()
    // A question asked once can't be asked again from its button.
    expect(within(suggested).getByRole('button', { name: PRODUCTION })).toBeDisabled()
    expect(within(suggested).getByRole('button', { name: PRODUCTION })).toHaveAccessibleDescription(
      'Already asked; the answer is above',
    )

    await user.click(within(suggested).getByRole('button', { name: TEAM }))
    expect(ask).toHaveBeenLastCalledWith('fjord-grocery', id, TEAM, [
      { question: PRODUCTION, answer: 'Yes. Her forecasts run in production.' },
    ])
    await waitFor(() => expect(within(answers).getAllByRole('listitem')).toHaveLength(2))
    const second = within(answers).getAllByRole('listitem')[1]
    expect(second).toHaveTextContent("The material doesn't answer this")
    expect(second).toHaveTextContent('Nothing in the material says she has managed a team.')

    // Closing and opening again keeps the conversation: it lives on the page.
    await user.click(within(kim).getByRole('button', { name: 'Ask about Kim Berg' }))
    expect(within(kim).queryByRole('region', { name: 'Questions about Kim Berg' })).toBeNull()
    await user.click(within(kim).getByRole('button', { name: 'Ask about Kim Berg' }))
    expect(within(kim).getAllByRole('list', { name: 'Answers' })[0]).toHaveTextContent('managed a team')
  })

  it('says a question of your own needs a paid call when they are off', async () => {
    const { data, id } = withKim()
    vi.spyOn(api, 'askOptions').mockResolvedValue({ suggested: [PRODUCTION] })
    const ask = vi.spyOn(api, 'ask').mockRejectedValue(new ApiError(403, 'paid calls are off'))
    const { user } = open(data)
    const kim = (await screen.findByRole('heading', { name: /Kim Berg/ })).closest('li') as HTMLElement
    await user.click(within(kim).getByRole('button', { name: 'Ask about Kim Berg' }))
    const region = await within(kim).findByRole('region', { name: 'Questions about Kim Berg' })

    const button = within(region).getByRole('button', { name: 'Ask' })
    expect(button).toBeDisabled()
    await user.type(within(region).getByLabelText('Question about Kim Berg'), 'Has she used Kubernetes?')
    await user.click(button)
    expect(ask).toHaveBeenCalledWith('fjord-grocery', id, 'Has she used Kubernetes?', [])
    const alert = await within(region).findByRole('alert')
    expect(alert).toHaveTextContent('needs a paid model call')
    expect(alert).toHaveTextContent('Try one of the demo questions above.')
    // The question stays in the box, to try again.
    expect(within(region).getByLabelText('Question about Kim Berg')).toHaveValue('Has she used Kubernetes?')
  })

  it('shows either the questions or the messages, not both', async () => {
    const { data } = withKim()
    vi.spyOn(api, 'askOptions').mockResolvedValue({ suggested: [PRODUCTION] })
    vi.spyOn(api, 'employerThread').mockResolvedValue({ messages: [], unread: 0 })
    vi.spyOn(api, 'employerRead').mockResolvedValue({ messages: [], unread: 0 })
    const { user } = open(data)
    const kim = (await screen.findByRole('heading', { name: /Kim Berg/ })).closest('li') as HTMLElement
    const askButton = within(kim).getByRole('button', { name: 'Ask about Kim Berg' })
    const messagesButton = within(kim).getByRole('button', { name: 'Messages with Kim Berg' })

    await user.click(askButton)
    await within(kim).findByRole('region', { name: 'Questions about Kim Berg' })
    await user.click(messagesButton)
    await within(kim).findByRole('region', { name: 'Thread with Kim Berg' })
    expect(within(kim).queryByRole('region', { name: 'Questions about Kim Berg' })).toBeNull()
    expect(askButton).toHaveAttribute('aria-expanded', 'false')

    await user.click(askButton)
    expect(await within(kim).findByRole('region', { name: 'Questions about Kim Berg' })).toBeInTheDocument()
    expect(within(kim).queryByRole('region', { name: 'Thread with Kim Berg' })).toBeNull()
    expect(messagesButton).toHaveAttribute('aria-expanded', 'false')
  })
})
