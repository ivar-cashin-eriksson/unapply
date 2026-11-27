import { Loader2 } from 'lucide-react'
import { useState, type ComponentProps } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { describeError } from '@/lib/api'

interface Props extends Omit<ComponentProps<typeof Button>, 'onClick'> {
  /** Creates the demo candidate or job, returning its name. */
  create: () => Promise<{ name: string }>
  /** Where to go once it exists. */
  to: (name: string) => string
}

/** Create a demo (which replays recorded answers, for free) and open it. */
export function DemoButton({ create, to, children, ...props }: Props) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  return (
    <Button
      {...props}
      disabled={busy || props.disabled}
      onClick={async () => {
        setBusy(true)
        try {
          const created = await create()
          navigate(to(created.name))
        } catch (e) {
          toast.error(describeError(e))
          setBusy(false)
        }
      }}
    >
      {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
      {children}
    </Button>
  )
}
