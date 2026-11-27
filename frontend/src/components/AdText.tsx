import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * A job ad written in simple Markdown: headings (#, ##, ###), bullet lists (- or *),
 * paragraphs and **bold**. Everything is rendered as text, never as HTML, so an ad
 * can't inject markup. A top heading equal to `title` is left out, as the page shows it.
 */
export function AdText({ text, title, className }: { text: string; title?: string; className?: string }) {
  return <div className={cn('space-y-3 text-sm leading-relaxed', className)}>{blocks(text, title)}</div>
}

function blocks(text: string, title?: string): ReactNode[] {
  const out: ReactNode[] = []
  let paragraph: string[] = []
  let bullets: string[] = []
  const flush = () => {
    if (paragraph.length) {
      out.push(<p key={out.length}>{inline(paragraph.join(' '))}</p>)
      paragraph = []
    }
    if (bullets.length) {
      out.push(
        <ul key={out.length} className="list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      )
      bullets = []
    }
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    const bullet = /^[-*]\s+(.*)$/.exec(line)
    if (!line) {
      flush()
    } else if (heading) {
      flush()
      if (heading[1] === '#' && title && heading[2].trim() === title.trim()) continue
      // The ad's own title is shown by the page, so its headings start one level down.
      const level = heading[1].length
      const Tag = level === 1 ? 'h3' : 'h4'
      out.push(
        <Tag key={out.length} className={cn('font-semibold', level === 1 ? 'pt-1 text-base' : 'pt-2 text-sm')}>
          {inline(heading[2])}
        </Tag>,
      )
    } else if (bullet) {
      if (paragraph.length) flush()
      bullets.push(bullet[1])
    } else if (bullets.length) {
      // A wrapped bullet continues on the next line.
      bullets[bullets.length - 1] += ` ${line}`
    } else {
      paragraph.push(line)
    }
  }
  flush()
  return out
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  )
}
