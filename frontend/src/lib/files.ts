// What the API accepts as material (`UPLOAD_SUFFIXES` and `MAX_UPLOAD_BYTES` in
// src/unapply/api/candidates.py), checked before uploading so a refused file says why.

export const ACCEPTED = ['.pdf', '.md', '.txt', '.tex', '.yaml', '.yml', '.json', '.zip']
export const MAX_BYTES = 20 * 1024 * 1024

/** Split files into those the API takes and why the others are refused. */
export function checkFiles(files: File[]): { ok: File[]; refused: string[] } {
  const ok: File[] = []
  const refused: string[] = []
  for (const f of files) {
    const dot = f.name.lastIndexOf('.')
    const suffix = dot >= 0 ? f.name.slice(dot).toLowerCase() : ''
    if (!ACCEPTED.includes(suffix)) refused.push(`${f.name}: not a file type we read`)
    else if (f.size > MAX_BYTES) refused.push(`${f.name}: over 20 MB`)
    else ok.push(f)
  }
  return { ok, refused }
}
