import { UploadCloud } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'

import { ACCEPTED, checkFiles } from '@/lib/files'
import { cn } from '@/lib/utils'

interface Props {
  /** Called with the files dropped or chosen that can be uploaded. */
  onFiles: (files: File[]) => void
  /** Called with a reason for each file that can't be. */
  onRefused: (reasons: string[]) => void
  disabled?: boolean
}

/**
 * A drop zone for material: drag files onto it, or click it (or press Enter or
 * Space on it) to choose them.
 */
export function FileDrop({ onFiles, onRefused, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const hint = useId()

  function take(list: FileList | null) {
    if (!list || disabled) return
    const { ok, refused } = checkFiles(Array.from(list))
    if (refused.length) onRefused(refused)
    if (ok.length) onFiles(ok)
  }

  function drop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    take(e.dataTransfer.files)
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-describedby={hint}
      aria-label="Upload files"
      data-testid="file-drop"
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          input.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors outline-none',
        'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
        over ? 'border-primary bg-accent' : 'border-border bg-card hover:border-primary/50',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      )}
    >
      <div className="rounded-full bg-accent p-3 text-primary">
        <UploadCloud className="size-6" aria-hidden />
      </div>
      <div>
        <p className="font-medium">
          {over ? 'Drop to upload' : 'Drag files here, or click to choose'}
        </p>
        <p id={hint} className="mt-1 text-sm text-muted-foreground">
          PDF, Markdown, text, LaTeX, YAML, JSON, or a zipped LinkedIn export. Up to
          20 MB a file.
        </p>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPTED.join(',')}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        data-testid="file-input"
        onChange={(e) => {
          take(e.target.files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
