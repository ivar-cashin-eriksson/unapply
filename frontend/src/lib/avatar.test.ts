import { avatar, AVATAR_COLOURS, AVATARS, GRID } from '@/lib/avatar'

function key(n: number) {
  const { colour, cells } = avatar(n)
  return `${colour}:${cells.map(([r, c]) => `${r}.${c}`).sort().join(',')}`
}

describe('avatar', () => {
  it('is the same every time for the same number', () => {
    expect(avatar(42)).toEqual(avatar(42))
    expect(key(1234)).toBe(key(1234))
  })

  it('gives every alias number a different avatar', () => {
    const seen = new Set(Array.from({ length: AVATARS }, (_, n) => key(n)))
    expect(seen.size).toBe(AVATARS)
  })

  it('is mirrored, never empty and inside the grid', () => {
    for (let n = 0; n < AVATARS; n += 7) {
      const { cells } = avatar(n)
      const on = new Set(cells.map(([r, c]) => `${r}.${c}`))
      expect(on.has('2.2')).toBe(true)
      for (const [r, c] of cells) {
        expect(r).toBeGreaterThanOrEqual(0)
        expect(r).toBeLessThan(GRID)
        expect(on.has(`${r}.${GRID - 1 - c}`)).toBe(true)
      }
    }
  })

  it('uses only its own colours, with enough contrast on white', () => {
    const luminance = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const v = parseInt(hex.slice(i, i + 2), 16) / 255
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    for (const colour of AVATAR_COLOURS) expect(1.05 / (luminance(colour) + 0.05)).toBeGreaterThanOrEqual(4.5)
    expect(new Set(Array.from({ length: 64 }, (_, n) => avatar(n).colour))).toEqual(new Set(AVATAR_COLOURS))
  })
})
