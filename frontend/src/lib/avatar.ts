// Abstract avatars for anonymous candidates, drawn here from the number the API
// gives with each alias. Nothing is fetched from an avatar service.

/**
 * Colours for avatars: cool and saturated hues only, so no avatar reads as a skin,
 * hair or eye colour, or as "pink for girls, blue for boys" (no pinks or light
 * blues). Each is at least 4.5:1 against white.
 */
export const AVATAR_COLOURS = ['#4338ca', '#0f766e', '#0369a1', '#6d28d9', '#047857', '#0e7490', '#1d4ed8', '#7e22ce']

/** How many different alias numbers there are, as `ALIASES` in the API. */
export const AVATARS = 1920

/** The avatar is a 5 by 5 grid, mirrored left to right. */
export const GRID = 5

export interface Avatar {
  colour: string
  /** Filled cells as [row, column], over the whole grid. */
  cells: [number, number][]
}

/**
 * Draw an avatar from an alias number (0 to `AVATARS` - 1).
 *
 * Every number gives a different avatar: the colour comes from the number modulo
 * 8, and the pattern from the rest through a one-to-one scramble of 14 bits, one
 * per cell of the left half and the middle column; the centre is always filled, so
 * no avatar is empty. The grid is mirrored, as in a tile or textile pattern.
 */
export function avatar(n: number): Avatar {
  const index = ((Math.trunc(n) % AVATARS) + AVATARS) % AVATARS
  const colour = AVATAR_COLOURS[index % AVATAR_COLOURS.length]
  // 7919 is odd, so multiplying by it is one to one modulo 2^14.
  let bits = (Math.floor(index / AVATAR_COLOURS.length) * 7919 + 12345) % 16384
  const cells: [number, number][] = []
  const half = Math.ceil(GRID / 2)
  for (let row = 0; row < GRID; row++) {
    for (let col = 0; col < half; col++) {
      const centre = row === Math.floor(GRID / 2) && col === half - 1
      const on = centre || (bits & 1) === 1
      if (!centre) bits >>= 1
      if (!on) continue
      cells.push([row, col])
      if (col !== GRID - 1 - col) cells.push([row, GRID - 1 - col])
    }
  }
  return { colour, cells }
}
