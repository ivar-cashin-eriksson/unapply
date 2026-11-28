import { activeFilters, filterLabel, filterQuery, withFilter, withoutFilter } from '@/pages/candidate/boardFilters'

describe('the board filters in the address', () => {
  it('lists the active filters in chip order, every skill on its own', () => {
    const params = new URLSearchParams('skill=sql&seniority=junior&fit=strong&skill=python&q=ignored')
    expect(activeFilters(params)).toEqual([
      { key: 'fit', value: 'strong' },
      { key: 'seniority', value: 'junior' },
      { key: 'skill', value: 'sql' },
      { key: 'skill', value: 'python' },
    ])
  })

  it('adds skills alongside each other and replaces any other filter', () => {
    let params = withFilter(new URLSearchParams(), 'skill', 'python')
    params = withFilter(params, 'skill', 'sql')
    params = withFilter(params, 'skill', 'python')
    params = withFilter(params, 'seniority', 'junior')
    params = withFilter(params, 'seniority', 'senior')
    expect(params.toString()).toBe('skill=python&skill=sql&seniority=senior')
    expect(withoutFilter(params, 'skill', 'python').toString()).toBe('skill=sql&seniority=senior')
    expect(withFilter(params, 'seniority', '').toString()).toBe('skill=python&skill=sql')
  })

  it('makes the API query, dropping what it cannot use', () => {
    expect(
      filterQuery(new URLSearchParams('location=Aarhus&work_permit=EU&min_vacancies=2&skill=sql&skill=dbt')),
    ).toEqual({
      location: 'Aarhus',
      work_mode: undefined,
      seniority: undefined,
      work_permit: 'EU',
      min_vacancies: 2,
      skill: ['sql', 'dbt'],
    })
    expect(filterQuery(new URLSearchParams('min_vacancies=lots')).min_vacancies).toBeUndefined()
    expect(filterQuery(new URLSearchParams('min_vacancies=0')).min_vacancies).toBeUndefined()
    expect(filterQuery(new URLSearchParams()).skill).toBeUndefined()
  })

  it('names each chip', () => {
    expect(filterLabel({ key: 'fit', value: 'not_met' })).toBe('Fit: Requirements not met')
    expect(filterLabel({ key: 'work_mode', value: 'remote' })).toBe('Work mode: Remote')
    expect(filterLabel({ key: 'seniority', value: 'mid' })).toBe('Seniority: Mid-level')
    expect(filterLabel({ key: 'work_permit', value: 'EU' })).toBe('Work permit: EU')
    expect(filterLabel({ key: 'min_vacancies', value: '2' })).toBe('At least 2 vacancies')
    expect(filterLabel({ key: 'min_vacancies', value: '1' })).toBe('At least 1 vacancy')
    expect(filterLabel({ key: 'skill', value: 'python' })).toBe('Skill: python')
  })
})
