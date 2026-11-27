import { Compass } from 'lucide-react'
import { Link, Navigate, Route, Routes } from 'react-router'

import { Layout } from '@/components/Layout'
import { EmptyState } from '@/components/states'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CandidateFlow, CandidateList } from '@/pages/candidate/CandidateFlow'
import { JobBoard, JobListing } from '@/pages/candidate/Jobs'
import { Material } from '@/pages/candidate/Material'
import { Profile } from '@/pages/candidate/Profile'
import { Questions } from '@/pages/candidate/Questions'
import { Review } from '@/pages/candidate/Review'
import { Home } from '@/pages/Home'
import { JobAd } from '@/pages/employer/JobAd'
import { JobFlow, JobList } from '@/pages/employer/JobFlow'
import { Rubric } from '@/pages/employer/Rubric'
import { Shortlist } from '@/pages/employer/Shortlist'

/** The app's pages. A router around it (BrowserRouter, or MemoryRouter in tests) is needed. */
export function AppRoutes() {
  return (
    <TooltipProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="candidates" element={<CandidateList />} />
          <Route path="candidates/:name" element={<CandidateFlow />}>
            <Route index element={<Navigate to="material" replace />} />
            <Route path="material" element={<Material />} />
            <Route path="review" element={<Review />} />
            <Route path="questions" element={<Questions />} />
            <Route path="profile" element={<Profile />} />
            <Route path="jobs">
              <Route index element={<JobBoard />} />
              <Route path=":job" element={<JobListing />} />
            </Route>
          </Route>
          <Route path="jobs" element={<JobList />} />
          <Route path="jobs/:name" element={<JobFlow />}>
            <Route index element={<Navigate to="ad" replace />} />
            <Route path="ad" element={<JobAd />} />
            <Route path="rubric" element={<Rubric />} />
            <Route path="shortlist" element={<Shortlist />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </TooltipProvider>
  )
}

function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="There's nothing here"
      action={
        <Button asChild>
          <Link to="/">Go to the start</Link>
        </Button>
      }
    />
  )
}
