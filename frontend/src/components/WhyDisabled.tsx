import { cloneElement, useId, useState, type ReactElement } from 'react'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface Props {
  /** Why the control is greyed out; nothing (or false) when it isn't. */
  reason?: string | false | null
  /** The one control, such as a disabled button. */
  children: ReactElement<{ 'aria-describedby'?: string }>
  /** For the wrapper, such as `w-full` around a full-width button. */
  className?: string
}

/**
 * Say why a control is greyed out, in a tooltip on hover and keyboard focus.
 *
 * A disabled button takes no pointer events and no focus, so a `title` on it never
 * shows. The tooltip sits on a wrapper instead, which takes focus only while there is
 * a reason, and the reason is also the control's accessible description, for screen
 * readers. The wrapper stays when the reason goes, so the control isn't remounted.
 */
export function WhyDisabled({ reason, children, className }: Props) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <TooltipProvider>
      <Tooltip open={Boolean(reason) && open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <span
            tabIndex={reason ? 0 : undefined}
            className={cn('inline-flex rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50', className)}
          >
            {cloneElement(children, { 'aria-describedby': reason ? id : undefined })}
          </span>
        </TooltipTrigger>
        {reason && <TooltipContent>{reason}</TooltipContent>}
      </Tooltip>
      {reason && (
        <span id={id} hidden>
          {reason}
        </span>
      )}
    </TooltipProvider>
  )
}
