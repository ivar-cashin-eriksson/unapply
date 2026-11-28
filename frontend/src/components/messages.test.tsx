import { screen, waitFor, within } from '@testing-library/react'

import { api, ApiError } from '@/lib/api'
import type { Message, Shortlist } from '@/lib/types'
import { board, candidate, connection, fit, job, listing, progressed, revealed, shortlist } from '@/test/fixtures'
import { renderApp } from '@/test/render'

function message(id: number, sender: Message['sender'], text: string): Message {
  return { id, sender, text, sent_at: `2026-11-27T1${id}:00:00`, read_at: null }
}

function approved() {
  vi.spyOn(api, 'candidate').mockResolvedValue(
    candidate({ has_profile: true, approved: true, history: ['extracted', 'approved'] }),
  )
  vi.spyOn(api, 'fits').mockResolvedValue([])
  vi.spyOn(api, 'fit').mockResolvedValue(fit())
}

const LISTING = '/candidates/john-doe/jobs/board-fjord-grocery'

describe('messages in the candidate app', () => {
  it('shows the thread once revealed, marks it read and sends at the bottom', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    const connections = vi
      .spyOn(api, 'connections')
      .mockResolvedValue([progressed('revealed', { unread_messages: 1 })])
    const unread = [message(1, 'employer', 'Hi John, are you free on Tuesday?')]
    vi.spyOn(api, 'candidateThread').mockResolvedValue({ messages: unread, unread: 1 })
    const read = vi
      .spyOn(api, 'candidateRead')
      .mockResolvedValue({ messages: [{ ...unread[0], read_at: '2026-11-27T19:00:00' }], unread: 0 })
    const send = vi.spyOn(api, 'candidateSend').mockResolvedValue(message(2, 'candidate', 'Yes, Tuesday works.'))
    const { user } = renderApp(LISTING)

    const thread = await screen.findByRole('region', { name: 'Thread with Fjord Grocery ApS' })
    expect(within(thread).getByText('Hi John, are you free on Tuesday?')).toBeInTheDocument()
    await waitFor(() => expect(read).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery'))
    // Marked new this time, and the unread count is loaded again.
    expect(await within(thread).findByText('New')).toBeInTheDocument()
    await waitFor(() => expect(connections.mock.calls.length).toBeGreaterThan(1))

    const box = within(thread).getByLabelText('Message to Fjord Grocery ApS')
    const button = within(thread).getByRole('button', { name: 'Send' })
    expect(button).toBeDisabled()
    await user.type(box, 'Yes, Tuesday works.')
    await user.click(button)
    expect(send).toHaveBeenCalledWith('john-doe', 'board-fjord-grocery', 'Yes, Tuesday works.')
    const items = within(within(thread).getByRole('list', { name: 'Messages' })).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Fjord Grocery ApS wrote:Hi John')
    expect(items[1]).toHaveTextContent('You wrote:Yes, Tuesday works.')
    expect(box).toHaveValue('')
  })

  it('has no thread before a reveal', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([connection()])
    const thread = vi.spyOn(api, 'candidateThread')
    renderApp(LISTING)
    await screen.findByRole('region', { name: 'Your connection' })
    expect(screen.queryByRole('region', { name: /Messages with/ })).toBeNull()
    expect(thread).not.toHaveBeenCalled()
  })

  it('says when a message could not be sent, and keeps it', async () => {
    approved()
    vi.spyOn(api, 'listing').mockResolvedValue(listing())
    vi.spyOn(api, 'connections').mockResolvedValue([progressed('revealed')])
    vi.spyOn(api, 'candidateThread').mockResolvedValue({ messages: [], unread: 0 })
    vi.spyOn(api, 'candidateSend').mockRejectedValue(new ApiError(409, 'no thread yet'))
    const { user } = renderApp(LISTING)
    const thread = await screen.findByRole('region', { name: 'Thread with Fjord Grocery ApS' })
    expect(thread).toHaveTextContent('No messages yet. Write the first to Fjord Grocery ApS.')
    const box = within(thread).getByLabelText('Message to Fjord Grocery ApS')
    await user.type(box, 'Hello')
    await user.click(within(thread).getByRole('button', { name: 'Send' }))
    expect(await within(thread).findByText('no thread yet')).toBeInTheDocument()
    expect(box).toHaveValue('Hello')
  })

  it('counts unread messages on the board card', async () => {
    approved()
    vi.spyOn(api, 'board').mockResolvedValue(board())
    vi.spyOn(api, 'connections').mockResolvedValue([progressed('revealed', { unread_messages: 2 })])
    renderApp('/candidates/john-doe/jobs')
    const jobs = await screen.findByRole('list', { name: 'Jobs' })
    const [first, second] = within(jobs).getAllByRole('listitem')
    expect(await within(first).findByText('2 new messages')).toBeInTheDocument()
    expect(within(second).queryByText(/new message/)).toBeNull()
  })
})

describe('messages in the employer app', () => {
  function open(data: Shortlist) {
    vi.spyOn(api, 'job').mockResolvedValue(job({ approved: true, history: ['extracted', 'rubric'] }))
    const load = vi.spyOn(api, 'shortlist').mockResolvedValue(data)
    return { load, ...renderApp('/jobs/fjord-grocery/shortlist') }
  }

  it('writes to a revealed candidate from their card, and only to them', async () => {
    const data = shortlist()
    data.candidates[0] = revealed(data.candidates[0])
    data.candidates[0].progress.unread_messages = 1
    const id = data.candidates[0].profile_id
    const unread = [message(1, 'candidate', 'Thank you for revealing me.')]
    const thread = vi.spyOn(api, 'employerThread').mockResolvedValue({ messages: unread, unread: 1 })
    const read = vi.spyOn(api, 'employerRead').mockResolvedValue({ messages: unread, unread: 0 })
    const send = vi.spyOn(api, 'employerSend').mockResolvedValue(message(2, 'employer', 'Can we talk on Tuesday?'))
    const { load, user } = open(data)

    const kim = (await screen.findByRole('heading', { name: /Kim Berg/ })).closest('li') as HTMLElement
    expect(within(kim).getByText('1 new message')).toBeInTheDocument()
    // Only revealed candidates have a thread.
    expect(screen.getAllByRole('button', { name: /^Messages with/ })).toHaveLength(1)

    await user.click(within(kim).getByRole('button', { name: 'Messages with Kim Berg' }))
    const region = await within(kim).findByRole('region', { name: 'Thread with Kim Berg' })
    expect(thread).toHaveBeenCalledWith('fjord-grocery', id)
    expect(within(region).getByText('Thank you for revealing me.')).toBeInTheDocument()
    await waitFor(() => expect(read).toHaveBeenCalledWith('fjord-grocery', id))
    await waitFor(() => expect(load.mock.calls.length).toBeGreaterThan(1))

    // Ctrl+Enter sends, as the button does.
    await user.type(within(region).getByLabelText('Message to Kim Berg'), 'Can we talk on Tuesday?')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(send).toHaveBeenCalledWith('fjord-grocery', id, 'Can we talk on Tuesday?')
    expect(await within(region).findByText('Can we talk on Tuesday?')).toBeInTheDocument()
  })
})
