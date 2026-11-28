import { act, renderHook, waitFor } from '@testing-library/react'
import { useResource } from '@/lib/useResource'

/** A promise and the function that resolves it, to finish loads in a chosen order. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

describe('useResource', () => {
  it('keeps the newest reload when an earlier one finishes last', async () => {
    const loads = [deferred<string>(), deferred<string>(), deferred<string>()]
    let calls = 0
    const { result } = renderHook(() => useResource(() => loads[calls++].promise, 'key'))
    act(() => loads[0].resolve('first'))
    await waitFor(() => expect(result.current.data).toBe('first'))

    let older!: Promise<void>
    let newer!: Promise<void>
    act(() => {
      older = result.current.reload()
      newer = result.current.reload()
    })
    await act(async () => {
      loads[2].resolve('newer')
      await newer
    })
    expect(result.current.data).toBe('newer')
    expect(result.current.loading).toBe(false)
    await act(async () => {
      loads[1].resolve('older')
      await older
    })
    expect(result.current.data).toBe('newer')
  })
})
