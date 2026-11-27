import { Check, Eye, Link2, Mail, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { Stage } from '@/lib/types'

/** What a candidate's stage on a job is called, and its badge's icon. */
const STAGES: Record<Stage, { label: string; icon: typeof Link2 }> = {
  connected: { label: 'Connected', icon: Link2 },
  revealed: { label: 'Revealed', icon: Eye },
  requested: { label: 'Asked to apply', icon: Mail },
  applied: { label: 'Applied', icon: Check },
  declined: { label: 'Declined', icon: X },
}

/** How far the candidate got on a job, as a badge. */
export function StageBadge({ stage }: { stage: Stage }) {
  const { label, icon: Icon } = STAGES[stage]
  return (
    <Badge variant={stage === 'declined' ? 'outline' : 'default'}>
      <Icon aria-hidden /> {label}
    </Badge>
  )
}
