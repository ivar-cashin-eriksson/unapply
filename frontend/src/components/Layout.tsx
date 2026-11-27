import { Briefcase, UserRound } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router'

import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/candidates', label: 'Candidates', icon: UserRound },
  { to: '/jobs', label: 'Employers', icon: Briefcase },
]

/** The page frame: a header with the two sides, and the page below. */
export function Layout() {
  return (
    <div className="min-h-svh">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <Link
            to="/"
            className="flex items-center gap-2 rounded-md font-semibold tracking-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <span
              aria-hidden
              className="flex size-7 items-center justify-center rounded-lg bg-primary text-sm text-primary-foreground"
            >
              u
            </span>
            unapply
          </Link>
          <nav aria-label="Main" className="flex gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
                    isActive
                      ? 'bg-accent font-medium text-accent-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-5xl px-6 py-10">
        <Outlet />
      </main>
      <Toaster position="top-right" offset={{ top: '4.5rem' }} richColors closeButton />
    </div>
  )
}
