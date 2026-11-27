import { checkFiles, MAX_BYTES } from '@/lib/files'

function file(name: string, size = 10): File {
  const f = new File(['x'], name)
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('checkFiles', () => {
  it('takes the types the API reads, in any case', () => {
    const { ok, refused } = checkFiles([file('cv.PDF'), file('notes.md'), file('linkedin.zip')])
    expect(ok.map((f) => f.name)).toEqual(['cv.PDF', 'notes.md', 'linkedin.zip'])
    expect(refused).toEqual([])
  })

  it('says why a file is refused', () => {
    const { ok, refused } = checkFiles([
      file('photo.png'),
      file('README'),
      file('big.pdf', MAX_BYTES + 1),
      file('fine.txt', MAX_BYTES),
    ])
    expect(ok.map((f) => f.name)).toEqual(['fine.txt'])
    expect(refused).toEqual([
      'photo.png: not a file type we read',
      'README: not a file type we read',
      'big.pdf: over 20 MB',
    ])
  })
})
