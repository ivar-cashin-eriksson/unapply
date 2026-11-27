import { fileSize, month, NAME_PATTERN, period, splitList, typedName } from '@/lib/format'

describe('dates', () => {
  it('shows a month and year', () => {
    expect(month('2022-03-01')).toBe('Mar 2022')
  })

  it('shows only the year for 1 January, as year-only dates are stored that way', () => {
    expect(month('2019-01-01')).toBe('2019')
  })

  it('shows nothing for an unknown date', () => {
    expect(month(null)).toBe('')
  })

  it('says "now" for a period without an end, and nothing when both are unknown', () => {
    expect(period('2020-03-01', null)).toBe('Mar 2020 – now')
    expect(period(null, '2021-06-01')).toBe('? – Jun 2021')
    expect(period(null, null)).toBe('')
  })
})

describe('typed text', () => {
  it('splits a comma-separated list and drops empty items', () => {
    expect(splitList(' Copenhagen, Aarhus ,, ')).toEqual(['Copenhagen', 'Aarhus'])
  })

  it('makes a typed name into one the API accepts', () => {
    expect(typedName('Jane Doe!')).toBe('jane-doe')
    expect(NAME_PATTERN.test(typedName('Jane Doe!'))).toBe(true)
    expect(NAME_PATTERN.test('-jane')).toBe(false)
    expect(typedName('x'.repeat(80))).toHaveLength(64)
  })

  it('shows file sizes in bytes, KB and MB', () => {
    expect(fileSize(512)).toBe('512 B')
    expect(fileSize(2048)).toBe('2 KB')
    expect(fileSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
