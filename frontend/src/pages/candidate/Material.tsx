import { Code2, Download, FileText, Lock, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { FileDrop } from '@/components/FileDrop'
import { ErrorAlert, PageHeader, Working } from '@/components/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, describeError } from '@/lib/api'
import { fileSize } from '@/lib/format'
import { useCandidate } from '@/pages/candidate/context'

/** Step 1: upload material, set GitHub, and extract a draft profile. */
export function Material() {
  const { name, summary, refresh } = useCandidate()
  const navigate = useNavigate()
  const [uploading, setUploading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [github, setGithub] = useState(summary.github ?? '')
  const fixed = summary.demo
  const hasMaterial = summary.material.length > 0 || Boolean(summary.github)

  async function upload(files: File[]) {
    setUploading(true)
    setError(null)
    try {
      await api.upload(name, files)
      toast.success(files.length === 1 ? `Added ${files[0].name}` : `Added ${files.length} files`)
      await refresh()
    } catch (e) {
      setError(e)
    } finally {
      setUploading(false)
    }
  }

  async function remove(file: string) {
    try {
      await api.removeFile(name, file)
      await refresh()
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  async function saveGithub() {
    try {
      await api.setGithub(name, github.trim() || null)
      toast.success(github.trim() ? `We'll read github.com/${github.trim()}` : 'GitHub removed')
      await refresh()
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  async function extract() {
    setExtracting(true)
    setError(null)
    try {
      const result = await api.extract(name)
      const p = result.profile
      toast.success(
        `Draft profile ready: ${p.experiences.length} experiences and ${p.skills.length} skills.`,
      )
      await refresh()
      navigate('../review')
    } catch (e) {
      setError(e)
      setExtracting(false)
    }
  }

  return (
    <>
      <PageHeader title="Your material">
        Your CV and anything else about your work. From a LinkedIn data export (the
        zip) only profile sections are read, never messages or connections.
      </PageHeader>

      {fixed && (
        <Alert className="mb-6" role="note">
          <Lock aria-hidden />
          <AlertTitle>This is the John Doe demo</AlertTitle>
          <AlertDescription>
            Its material is fixed, so the recorded answers fit it. Go straight to
            extracting the profile; it costs nothing.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <div className="space-y-6">
          {!fixed && <FileDrop onFiles={upload} onRefused={(r) => r.forEach((m) => toast.error(m))} disabled={uploading} />}
          {uploading && <Working>Uploading…</Working>}

          <section aria-labelledby="files-title">
            <h2 id="files-title" className="mb-3 text-sm font-medium text-muted-foreground">
              Your files
            </h2>
            {summary.material.length ? (
              <ul className="divide-y rounded-xl border bg-card">
                {summary.material.map((f) => (
                  <li key={f.name} className="flex items-center gap-3 px-4 py-3">
                    <FileText className="size-4 text-primary" aria-hidden />
                    <span className="flex-1 truncate font-medium">{f.name}</span>
                    <span className="text-sm text-muted-foreground">{fileSize(f.size)}</span>
                    <Button variant="ghost" size="icon-sm" asChild>
                      <a
                        href={api.materialFileUrl(name, f.name)}
                        download={f.name}
                        aria-label={`Download ${f.name}`}
                      >
                        <Download aria-hidden />
                      </a>
                    </Button>
                    {!fixed && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${f.name}`}
                        onClick={() => remove(f.name)}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                No files yet. Your CV is a good start.
              </p>
            )}
          </section>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Code2 className="size-4" aria-hidden /> GitHub
              </CardTitle>
              <CardDescription>We read your public repositories.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Label htmlFor="github" className="sr-only">
                GitHub username
              </Label>
              <Input
                id="github"
                placeholder="username"
                value={github}
                disabled={fixed}
                onChange={(e) => setGithub(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveGithub()}
              />
              {!fixed && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={github.trim() === (summary.github ?? '')}
                  onClick={saveGithub}
                >
                  Save
                </Button>
              )}
            </CardContent>
          </Card>

          <Card className="border-primary/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="size-4 text-primary" aria-hidden /> Build my profile
              </CardTitle>
              <CardDescription>
                We read your material and draft a profile. Every claim quotes your
                material; you check it next.
                {summary.has_profile &&
                  ' Building it again replaces your review and answers.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button className="w-full" disabled={!hasMaterial || extracting} onClick={extract}>
                {summary.has_profile ? 'Build it again' : 'Build my profile'}
              </Button>
              {extracting && <Working>Reading your material. This can take a minute.</Working>}
              {!hasMaterial && (
                <p className="text-xs text-muted-foreground">Add a file or your GitHub first.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <ErrorAlert error={error} />
      </div>
    </>
  )
}
