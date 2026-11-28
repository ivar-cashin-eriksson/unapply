import { byKind, EXPERIENCE_KINDS, KIND_ORDER } from '@/lib/experienceKind'

describe('experience kinds', () => {
  it('gives every kind its own name, icon and colour', () => {
    const looks = KIND_ORDER.map((k) => EXPERIENCE_KINDS[k])
    for (const key of ['label', 'icon', 'dot', 'border'] as const) {
      expect(new Set(looks.map((l) => l[key])).size).toBe(KIND_ORDER.length)
    }
  })

  it('groups entries by kind in a fixed order, keeping their indices and order', () => {
    const entries = [
      { name: 'a', kind: 'project' as const },
      { name: 'b', kind: 'work' as const },
      { name: 'c', kind: 'project' as const },
    ]
    expect(byKind(entries).map((g) => [g.kind, g.entries.map((e) => [e.entry.name, e.index])])).toEqual([
      ['work', [['b', 1]]],
      [
        'project',
        [
          ['a', 0],
          ['c', 2],
        ],
      ],
    ])
    expect(byKind([])).toEqual([])
  })
})
