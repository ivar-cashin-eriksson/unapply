import { useEffect, useState } from 'react'

export interface Resource<T> {
  /** The data for the current key, or undefined until it has loaded. */
  data: T | undefined
  error: unknown
  loading: boolean
  /** Load again, such as after a change. Keeps the old data while loading. */
  reload: () => Promise<void>
  /** Replace the data without loading, such as with a response that has it. */
  set: (data: T) => void
}

interface State<T> {
  /** The key the data or error belongs to. */
  key: string
  data?: T
  error: unknown
}

/**
 * Load something from the API when the component mounts and whenever `key`
 * changes. A small stand-in for a data-fetching library: the app has few pages
 * and loads little. Data for an earlier key is never returned.
 */
export function useResource<T>(load: () => Promise<T>, key: string): Resource<T> {
  const [state, setState] = useState<State<T> | null>(null)
  const [reloading, setReloading] = useState(false)

  useEffect(() => {
    let current = true
    load().then(
      (data) => current && setState({ key, data, error: null }),
      (error: unknown) => current && setState({ key, error }),
    )
    return () => {
      current = false
    }
    // `load` is a new function on every render; `key` says when it changes meaning.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const fresh = state?.key === key ? state : null
  return {
    data: fresh?.data,
    error: fresh?.error ?? null,
    loading: fresh === null || reloading,
    reload: async () => {
      setReloading(true)
      try {
        setState({ key, data: await load(), error: null })
      } catch (error) {
        setState((s) => ({ key, data: s?.key === key ? s.data : undefined, error }))
      } finally {
        setReloading(false)
      }
    },
    set: (data: T) => setState({ key, data, error: null }),
  }
}
