// Shared by the spider chart and the pages that use it.

/**
 * Colours for the candidates compared, in a fixed order: the first three slots of
 * the validated categorical palette, which stay apart for every pair, including
 * for colour-blind readers. Overlapping shapes are hard to read past three, so at
 * most three candidates are compared at once. Two of these are below 3:1 against
 * white, so the chart always comes with its table and a labelled legend.
 */
export const SERIES_COLOURS = ['#257de0', '#f47230', '#00b894']
export const MAX_COMPARED = SERIES_COLOURS.length

/** Which levels to draw: the candidate's own, the estimated, or both. */
export type LevelView = 'own' | 'estimated' | 'both'
