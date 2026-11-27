import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router'

import { AppRoutes } from '@/App'

/** Records where the app is, for tests that check navigation. */
function LocationProbe({ onChange }: { onChange: (path: string) => void }) {
  const { pathname } = useLocation()
  useEffect(() => onChange(pathname), [onChange, pathname])
  return null
}

/** Render the whole app at `path`, with a user to act and where the app is now. */
export function renderApp(path: string) {
  const user = userEvent.setup()
  let current = path
  const onChange = (p: string) => {
    current = p
  }
  const result = render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
      <LocationProbe onChange={onChange} />
    </MemoryRouter>,
  )
  return { user, ...result, location: () => current }
}
