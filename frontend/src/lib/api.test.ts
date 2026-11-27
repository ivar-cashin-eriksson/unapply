import { api, ApiError, describeError, errorDetail } from '@/lib/api'

function respond(status: number, body: unknown, statusText = '') {
  // A new Response each call: a body can only be read once.
  return vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(body === null ? null : JSON.stringify(body), {
        status,
        statusText,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
}

describe('errorDetail', () => {
  it('reads a plain message', () => {
    expect(errorDetail({ detail: 'No candidate called x' }, 'fallback')).toBe('No candidate called x')
  })

  it('reads validation errors with where they are, without "body"', () => {
    const body = {
      detail: [
        { loc: ['body', 'skills', 0, 'level'], msg: 'Input should be less than 6' },
        { loc: ['body', 'headline'], msg: 'Field required' },
      ],
    }
    expect(errorDetail(body, 'fallback')).toBe(
      'skills › 0 › level: Input should be less than 6; headline: Field required',
    )
  })

  it('falls back for anything else', () => {
    expect(errorDetail('oops', 'fallback')).toBe('fallback')
  })
})

describe('requests', () => {
  it('goes to /api and never asks for paid calls', async () => {
    const fetch = respond(200, { name: 'john-doe' })
    await api.extract('john-doe')
    await api.extractRubric('fjord grocery')
    const urls = fetch.mock.calls.map(([url]) => String(url))
    expect(urls).toEqual(['/api/candidates/john-doe/extract', '/api/jobs/fjord%20grocery/extract'])
    expect(urls.some((u) => u.includes('allow_api'))).toBe(false)
  })

  it('turns a refused paid call into advice to try the demo', async () => {
    respond(403, { detail: 'Paid API calls are disabled.' })
    const error = await api.extract('jane').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).paidCallRefused).toBe(true)
    expect(describeError(error)).toMatch(/paid calls are off on this server/)
    expect(describeError(error)).toMatch(/demo/)
  })

  it('shows the API message for other errors', async () => {
    respond(409, { detail: 'The rubric was matched against and is locked.' })
    const error = await api.saveRubric('job', {} as never).catch((e: unknown) => e)
    expect(describeError(error)).toBe('The rubric was matched against and is locked.')
  })

  it('says the server is down when it can\'t be reached', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await api.candidates().catch((e: unknown) => e)
    expect((error as ApiError).status).toBe(0)
    expect(describeError(error)).toMatch(/Can't reach the server/)
  })

  it('treats a 5xx without a JSON body as the API being down (the dev proxy)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('proxy error', { status: 502 }))
    const error = await api.candidates().catch((e: unknown) => e)
    expect(describeError(error)).toMatch(/Can't reach the server/)
  })

  it('returns nothing for 204', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.discardQuestions('john-doe')).resolves.toBeUndefined()
  })

  it('uploads files as form data', async () => {
    const fetch = respond(201, [{ name: 'cv.md', size: 1 }])
    await api.upload('jane', [new File(['# CV'], 'cv.md')])
    const init = fetch.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect((init.body as FormData).getAll('files')).toHaveLength(1)
  })
})
