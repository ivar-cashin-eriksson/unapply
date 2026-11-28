import path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

// Both demos end to end in a real browser, against the real API, for free: the
// demos replay recorded answers. Screenshots of each step go to e2e/screenshots/.

const SHOTS = path.join(import.meta.dirname, 'screenshots')
// Words for the assessment, which a candidate never sees.
const ASSESSMENT = /estimat|confidence|claim support|overclaim/i
// The assessment and the rubric: neither is ever shown on a candidate page.
const HIDDEN_FROM_CANDIDATES = /estimat|confidence|claim support|overclaim|rubric|criteri|weight|min.?level/i

/** A screenshot of the whole page; of the window only where a bar is fixed at the bottom. */
async function shot(page: Page, name: string, { fullPage = true } = {}) {
  // Let toasts and transitions settle so the pictures are stable.
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage })
}

test('the John Doe demo: material, review, questions, profile and dashboard', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Upload your material once')
  await shot(page, '01-home')

  await page.getByRole('button', { name: 'Try the John Doe demo' }).click()
  await expect(page).toHaveURL(/\/candidates\/john-doe-demo[-\d]*\/material$/)
  await expect(page.getByText('This is the John Doe demo')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload files' })).toHaveCount(0)
  await shot(page, '02-candidate-material')
  // John's own files can be downloaded as uploaded, even in the demo.
  const cv = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download cv.md' }).click()
  expect((await cv).suggestedFilename()).toBe('cv.md')

  // Step 1: build the draft profile from John's material.
  await page.getByRole('button', { name: 'Build my profile' }).click()
  await expect(page.getByRole('heading', { name: 'Review your profile' })).toBeVisible()
  await expect(page).toHaveURL(/\/review$/)
  const steps = page.getByRole('navigation', { name: 'Your steps' })
  await expect(steps.getByRole('link', { name: /Material/ })).toContainText('(done)')

  // Step 2: rate a skill by hand, then fill in John's whole review and approve it.
  const python = page.getByRole('radiogroup', { name: 'Your level in python' })
  await python.getByRole('radio', { name: '4 Advanced' }).click()
  await expect(python.getByRole('radio', { name: '4 Advanced' })).toHaveAttribute('aria-checked', 'true')
  await shot(page, '03-candidate-review', { fullPage: false })
  await page.getByRole('tab', { name: /Experience/ }).click()
  await expect(page.getByLabel('Title').first()).not.toHaveValue('')
  await shot(page, '04-candidate-review-experience', { fullPage: false })
  await page.getByRole('tab', { name: /Skills/ }).click()
  await page.getByRole('button', { name: "Fill in John's review" }).click()
  await expect(page.getByLabel(/I approve this profile/)).toBeChecked()
  // A skill the material misses is added in the Skills tab, with a level and why:
  // John's Looker, taken out of his filled-in review and added again by hand.
  const missing = page.getByRole('region', { name: 'Missing a skill?' })
  await missing.getByRole('button', { name: 'Remove looker' }).click()
  await expect(missing.getByRole('button', { name: 'Remove looker' })).toHaveCount(0)
  await missing.getByRole('button', { name: 'Add a skill' }).click()
  await missing.getByLabel('Skill', { exact: true }).last().fill('looker')
  await missing.getByRole('radiogroup', { name: 'Your level in looker' }).getByRole('radio', { name: /^3 / }).click()
  await missing
    .getByLabel('Where you used it')
    .last()
    .fill('Used Looker daily for two years before Nordlys Retail moved to Tableau.')
  await shot(page, '04b-candidate-review-add-skill')
  expect(await page.locator('main').textContent()).not.toMatch(ASSESSMENT)
  await page.getByRole('button', { name: 'Save and approve' }).click()

  // Step 3: questions about skills the material says little about.
  await expect(page.getByRole('heading', { name: 'A few questions' })).toBeVisible()
  await expect(page).toHaveURL(/\/questions$/)
  await page.getByRole('button', { name: 'Prepare my questions' }).click()
  const answers = page.getByPlaceholder('Your answer')
  await expect(answers.first()).toBeVisible()
  await page.getByRole('button', { name: "Fill in John's answers" }).click()
  await expect(answers.first()).not.toHaveValue('')
  expect(await page.locator('main').textContent()).not.toMatch(ASSESSMENT)
  await shot(page, '05-candidate-questions')
  await page.getByRole('button', { name: /^Send \d+ answers?$/ }).click()

  // Step 4: the profile, as employers will see it.
  await expect(page).toHaveURL(/\/profile$/)
  await expect(page.getByText(/Approved on/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Skills' })).toBeVisible()
  await expect(page.getByText('looker', { exact: true })).toBeVisible()
  await expect(steps.getByRole('link', { name: /Questions/ })).toContainText('(done)')
  expect(await page.locator('main').textContent()).not.toMatch(ASSESSMENT)
  await shot(page, '06-candidate-profile')

  // Step 5: the dashboard. With the demo jobs on the board, the synthetic pool is
  // who John is compared with, and the jobs' skills are what tips draw on.
  expect((await page.request.post('/api/demos/board')).ok()).toBe(true)
  await steps.getByRole('link', { name: /Dashboard/ }).click()
  await expect(page.getByRole('heading', { name: 'Your dashboard' })).toBeVisible()
  const numbers = page.getByLabel('Your profile in numbers')
  await expect(numbers).toContainText('12')
  await expect(numbers).toContainText('other candidates')
  const technology = page.getByRole('list', { name: 'Technology' })
  await expect(technology.getByText('python', { exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: /Other candidates' own levels in python/ })).toBeVisible()
  await expect(page.getByText(/^Fewer than 5 others rated it$/).first()).toBeVisible()
  await expect(page.getByRole('list', { name: 'Asked for on the job board' }).getByRole('listitem').first()).toBeVisible()
  await expect(page.getByRole('list', { name: 'Follow from your skills' })).toContainText('machine learning')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '25-candidate-dashboard')

  // The questions page now shows the answers given.
  await steps.getByRole('link', { name: /Questions/ }).click()
  await expect(page.getByRole('heading', { name: 'Your answers' })).toBeVisible()
})

test('the Fjord Grocery demo: job ad and rubric', async ({ page }) => {
  await page.goto('/jobs')
  await page.getByRole('button', { name: 'Try the Fjord Grocery demo' }).click()
  await expect(page).toHaveURL(/\/jobs\/fjord-grocery-demo[-\d]*\/ad$/)
  await expect(page.getByText('This is the Fjord Grocery demo')).toBeVisible()
  await expect(page.getByLabel('Ad')).not.toHaveValue('')
  await shot(page, '07-job-ad')

  // Step 1: draft the rubric from the ad.
  await page.getByRole('button', { name: 'Draft the rubric' }).click()
  await expect(page.getByRole('heading', { name: 'Rubric', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/rubric$/)
  await expect(page.getByText('Version 1')).toBeVisible()
  const must = page.getByRole('region', { name: 'Must-haves' })
  await expect(must.getByPlaceholder('What is asked for').first()).not.toHaveValue('')
  await shot(page, '08-job-rubric', { fullPage: false })

  // Step 2: change a weight, add a criterion, and approve. A change is a new version.
  const first = must.getByRole('radiogroup', { name: /^Weight of / }).first()
  await first.getByRole('radio', { name: '2 small' }).click()
  await page.getByRole('button', { name: 'Add a nice-to-have' }).click()
  const nice = page.getByRole('region', { name: 'Nice-to-haves' })
  await nice.getByPlaceholder('What is asked for').last().fill('Speaks a Scandinavian language')
  await page.getByLabel(/I approve this rubric/).check()
  await page.getByRole('button', { name: 'Save and approve' }).click()
  await expect(page.getByText('Version 2', { exact: true })).toBeVisible()
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  await expect(nice.getByPlaceholder('What is asked for').last()).toHaveValue('Speaks a Scandinavian language')
  await expect(nice.getByText('Added by you: no quote from the ad.').last()).toBeVisible()
  await shot(page, '09-job-rubric-approved', { fullPage: false })
  const steps = page.getByRole('navigation', { name: 'Job steps' })
  await expect(steps.getByRole('link', { name: /Shortlist/ })).toBeVisible()
})

// The pool's candidates by first name: none may appear on the employer's shortlist.
const POOL_NAMES = /astrid|clara|emil|freja|henrik|ida |jonas|lars|mikkel|nadia|priya|sofie|john doe/i

test('the shortlist demo: ranked, explained, compared, revealed', async ({ page }) => {
  await page.goto('/jobs')
  await page.getByRole('button', { name: 'Try the shortlist demo' }).click()
  await expect(page).toHaveURL(/\/jobs\/fjord-grocery-shortlist[-\d]*\/shortlist$/)
  await expect(page.getByText('No one is ranked yet')).toBeVisible()

  // Match the synthetic pool with the free baseline.
  await page.getByRole('button', { name: 'Match candidates' }).click()
  const ranked = page.getByRole('heading', { name: /^\d+ ranked$/ })
  await expect(ranked).toBeVisible()
  // The 12 of the pool, connected to every demo job. The John Doe demo approved by
  // an earlier test isn't: only candidates who connect to a job are ranked.
  await expect(ranked).toHaveText('12 ranked')
  await expect(page.getByRole('meter', { name: /^Total for [A-Z][a-z]+ [A-Z][a-z]+$/ }).first()).toBeVisible()
  // Each card: the scorer's total, and the baseline on own and on estimated levels.
  await expect(page.getByRole('meter', { name: /^Own rating for [A-Z][a-z]+ [A-Z][a-z]+$/ }).first()).toBeVisible()
  await expect(page.getByRole('meter', { name: /^Estimated from evidence for [A-Z][a-z]+ [A-Z][a-z]+$/ }).first()).toBeVisible()
  // Each candidate has a two-word alias and an avatar, none shared.
  const aliases = await page.getByRole('heading', { level: 3 }).allTextContents()
  expect(aliases.every((a) => /^[A-Z][a-z]+ [A-Z][a-z]+$/.test(a))).toBe(true)
  expect(new Set(aliases).size).toBe(aliases.length)
  const avatars = await page.locator('svg[data-avatar]').evaluateAll((all) => all.map((a) => a.getAttribute('data-avatar')))
  expect(avatars).toHaveLength(aliases.length)
  expect(new Set(avatars).size).toBe(aliases.length)
  await shot(page, '11-shortlist', { fullPage: false })

  // The three who fail a hard filter: below a divider, scored, with the filter named.
  const divider = page.getByRole('separator', { name: /Don't meet the requirements/ })
  await expect(divider).toContainText('3')
  const failing = page.getByRole('list', { name: "Don't meet the requirements" })
  await expect(failing.getByRole('listitem')).toHaveCount(3)
  await expect(failing.getByText(/^Doesn't meet/)).toHaveCount(4) // One fails two filters.
  await expect(failing.getByRole('meter', { name: /^Total for [A-Z][a-z]+ [A-Z][a-z]+$/ })).toHaveCount(3)
  await divider.scrollIntoViewIfNeeded()
  await shot(page, '15-shortlist-failed', { fullPage: false })
  await page.getByRole('heading', { name: 'Shortlist', exact: true }).scrollIntoViewIfNeeded()

  // Why the first is first: a score per criterion, and how many quotes support it.
  // The quotes themselves stay hidden until the candidate is revealed.
  const first = page.getByRole('listitem').filter({ has: page.getByLabel('Rank 1') }).first()
  await first.getByRole('button', { name: /^Why for/ }).click()
  const reasons = page.getByRole('region', { name: /^Reasons for/ })
  await expect(reasons.getByRole('meter').first()).toBeVisible()
  await expect(reasons.getByText(/quotes? supports? this, shown once you reveal the candidate/).first()).toBeVisible()
  await expect(reasons.locator('blockquote')).toHaveCount(0)
  await reasons.scrollIntoViewIfNeeded()
  await shot(page, '12-shortlist-reasons', { fullPage: false })
  await first.getByRole('button', { name: /^Hide for/ }).click()

  // Compare the top three on the rubric's skills, own and estimated levels.
  const boxes = page.getByRole('checkbox', { name: /^Compare [A-Z][a-z]+ [A-Z][a-z]+$/ })
  for (const i of [0, 1, 2]) await boxes.nth(i).click()
  await expect(boxes.nth(3)).toBeDisabled()
  const chart = page.getByRole('img', { name: /^Levels in \d+ skills/ })
  await expect(chart).toBeVisible()
  await expect(page.getByRole('table')).toContainText('estimated / own')
  await page.getByRole('heading', { name: 'Shortlist', exact: true }).scrollIntoViewIfNeeded()
  await shot(page, '13-shortlist-compare', { fullPage: false })
  await page.getByRole('radio', { name: 'Estimated' }).click()
  await expect(page.getByTestId('shape-own-0')).toHaveCount(0)
  await expect(page.getByTestId('shape-estimated-0')).toBeVisible()

  // No one is named before a reveal, and asking to apply comes only after one.
  expect(await page.locator('main').textContent()).not.toMatch(POOL_NAMES)
  const second = page.getByRole('listitem').filter({ has: page.getByLabel('Rank 2') }).first()
  await expect(second.getByRole('button', { name: /^Request application/ })).toHaveCount(0)

  // Reveal the first: their name, contact details and quotes; no payment is taken.
  await first.getByRole('button', { name: /^Reveal: [A-Z][a-z]+ [A-Z][a-z]+$/ }).click()
  await expect(page.getByText(/is revealed\. No payment is taken/)).toBeVisible()
  await expect(page.getByText('Reveals used: 1 of 10')).toBeVisible()
  await expect(first.getByRole('heading', { level: 3 })).toHaveText(POOL_NAMES)
  await expect(first.getByRole('link', { name: /@example\.com$/ })).toBeVisible()
  await first.getByRole('button', { name: /^Why for/ }).click()
  await expect(first.locator('blockquote').first()).toBeVisible()
  await expect(first.getByText(/shown once you reveal/)).toHaveCount(0)
  // Only the one revealed is named.
  const named = (await page.locator('main').textContent())!.match(new RegExp(POOL_NAMES.source, 'g')) ?? []
  expect(new Set(named.map((n) => n.toLowerCase())).size).toBe(1)
  // The card's top below the fixed header, so the name shows with the quotes.
  await first.evaluate((el) => el.scrollIntoView({ block: 'start' }))
  await page.mouse.wheel(0, -72)
  await shot(page, '21-shortlist-revealed', { fullPage: false })
  await first.getByRole('button', { name: /^Hide for/ }).click()

  // The same button now asks them to apply, then waits for their answer.
  await first.getByRole('button', { name: /^Request application: / }).click()
  await expect(first.getByRole('button', { name: /^Waiting for application: / })).toBeDisabled()
  await expect(page.getByRole('group', { name: 'How far candidates got' })).toContainText('1 asked to apply')

  // The LLM scorer replays recorded answers in the demo, so it is free too.
  await page.getByRole('radio', { name: 'LLM' }).click()
  await expect(page.getByText(/replays recorded answers/)).toBeVisible()
  await page.getByRole('button', { name: 'Match candidates' }).click()
  await expect(ranked).toBeVisible()
  await expect(page.getByRole('meter', { name: /^Total for [A-Z][a-z]+ [A-Z][a-z]+$/ }).first()).toBeVisible()
  // The comparison stays: the same people, scored another way.
  await expect(chart).toBeVisible()
  // Reveals are the job's, whichever scorer ranks.
  await expect(page.getByText('Reveals used: 1 of 10')).toBeVisible()
  await shot(page, '14-shortlist-llm', { fullPage: false })

  // The overview: the same pool in aggregate, with no one named or aliased.
  await page.getByRole('navigation', { name: 'Job steps' }).getByRole('link', { name: /Overview/ }).click()
  await expect(page).toHaveURL(/\/overview$/)
  const stats = page.getByLabel('Candidates', { exact: true })
  await expect(stats).toContainText('Connected12')
  await expect(stats).toContainText('Matched12')
  await expect(stats).toContainText('Meet every requirement9')
  const funnel = page.getByRole('list', { name: 'How far candidates got' })
  await expect(funnel.getByRole('meter', { name: 'Revealed' })).toHaveAttribute('aria-valuenow', '1')
  await expect(funnel.getByRole('meter', { name: 'Asked to apply' })).toHaveAttribute('aria-valuenow', '1')
  await expect(page.getByRole('img', { name: /^Baseline total: .* median \d\.\d\d/ })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Requirements not met' }).getByRole('meter').first()).toBeVisible()
  await expect(page.getByRole('list', { name: "The rubric's skills" }).getByRole('meter').first()).toBeVisible()
  const main = (await page.locator('main').textContent())!
  expect(main).not.toMatch(POOL_NAMES)
  for (const alias of aliases) expect(main).not.toContain(alias)
  await shot(page, '25-overview')
  // The LLM scorer's totals, from the matches just replayed.
  await page.getByRole('radio', { name: 'LLM' }).click()
  await expect(page.getByRole('img', { name: /^LLM total: .* median \d\.\d\d/ })).toBeVisible()
  await expect(stats).toContainText('Matched12')
})

test('the job board in John Doe\'s demo: search, read, connect and withdraw', async ({ page }) => {
  // John approves his profile first: only approved profiles connect.
  await page.goto('/candidates')
  await page.getByRole('button', { name: 'Try the John Doe demo' }).click()
  await expect(page).toHaveURL(/\/material$/)
  const candidate = page.url().match(/\/candidates\/([^/]+)\//)![1]
  await page.getByRole('button', { name: 'Build my profile' }).click()
  await page.getByRole('button', { name: "Fill in John's review" }).click()
  await page.getByRole('button', { name: 'Save and approve' }).click()
  await expect(page).toHaveURL(/\/questions$/)

  const steps = page.getByRole('navigation', { name: 'Your steps' })
  await steps.getByRole('link', { name: /Jobs/ }).click()
  await expect(page.getByRole('heading', { name: 'Find jobs' })).toBeVisible()
  // Demo candidates can add the demo jobs. The board may already list the Fjord
  // Grocery demo jobs that earlier tests approved; adding twice changes nothing.
  await page.getByRole('button', { name: 'Add the demo jobs' }).click()
  await expect(page.getByText('11 demo jobs are on the board.')).toBeVisible()
  const jobs = page.getByRole('list', { name: 'Jobs' })
  await expect(jobs.getByRole('link', { name: 'Senior Machine Learning Engineer' })).toBeVisible()
  const total = await jobs.getByRole('listitem').count()
  expect(total).toBeGreaterThanOrEqual(11)
  await expect(page.getByText(`${total} jobs`, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add the demo jobs' }).click()
  await expect(jobs.getByRole('listitem')).toHaveCount(total)
  // How well John fits each job, from his own levels, and requirements he misses.
  const lynfjord = jobs.getByRole('listitem').filter({ hasText: 'Lynfjord Power' })
  await expect(lynfjord.getByRole('group', { name: 'Your fit' })).toContainText('Strong fit')
  const kaveri = jobs.getByRole('listitem').filter({ hasText: 'Bengaluru' })
  const missed = kaveri.getByRole('group', { name: "Requirements you don't meet" })
  await expect(missed).toContainText('Location: Bengaluru')
  await expect(missed).toContainText('Work permit: IN required')
  await expect(
    jobs.getByRole('listitem').filter({ hasText: 'Kløvermark' }).getByRole('group', { name: 'Your fit' }),
  ).toContainText('Low fit')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '16-job-board')

  // By fit: a band, the requirements he doesn't meet, and best fit first.
  const fitOf = async () =>
    (await jobs.getByRole('group', { name: 'Your fit' }).allTextContents()).map(
      (t) => ['Strong fit', 'Good fit', 'Partial fit', 'Low fit'].findIndex((b) => t.includes(b)),
    )
  await page.getByLabel('Fit', { exact: true }).selectOption('strong')
  await expect(page.getByText(/· searching…/)).toHaveCount(0)
  await expect(page.getByText(new RegExp(`^[0-9]+ of ${total} jobs$`))).toBeVisible()
  await expect(lynfjord).toBeVisible()
  await expect(jobs.getByRole('listitem').filter({ hasText: 'Kløvermark' })).toHaveCount(0)
  expect(new Set(await fitOf())).toEqual(new Set([0]))
  await page.getByLabel('Fit', { exact: true }).selectOption('not_met')
  await expect(kaveri).toBeVisible()
  await expect(lynfjord).toHaveCount(0)
  for (const card of await jobs.getByRole('listitem').all()) {
    await expect(card.getByRole('group', { name: "Requirements you don't meet" })).toBeVisible()
  }
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await page.getByLabel('Sort', { exact: true }).selectOption('fit')
  await expect(page.getByText(/· searching…/)).toHaveCount(0)
  await expect(jobs.getByRole('listitem').first().getByRole('group', { name: 'Your fit' })).toContainText('Strong fit')
  await expect(jobs.getByRole('listitem')).toHaveCount(total)
  const ordered = await fitOf()
  expect(ordered).toEqual([...ordered].sort((a, b) => a - b))
  expect(ordered.at(-1)).toBe(3) // Kløvermark is a low fit.
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '16b-job-board-best-fit-first')
  await page.getByLabel('Sort', { exact: true }).selectOption('newest')
  await expect(jobs.getByRole('listitem').first().getByRole('group', { name: 'Your fit' })).toBeVisible()

  // Advanced filters: skills the ads name (through the taxonomy), work permit, vacancies.
  await page.getByRole('button', { name: 'Advanced' }).click()
  await page.getByLabel('Skills in the ad').selectOption('pytorch')
  await expect(jobs.getByRole('listitem')).toHaveCount(1)
  await expect(jobs.getByRole('link', { name: 'Senior Machine Learning Engineer' })).toBeVisible()
  const chips = page.getByRole('list', { name: 'Active filters' })
  await expect(chips).toHaveText('Skill: pytorch')
  await chips.getByRole('button', { name: 'Remove Skill: pytorch' }).click()
  await expect(chips).toHaveCount(0)
  await page.getByLabel('Vacancies').selectOption('3')
  await expect(page.getByText(/· searching…/)).toHaveCount(0)
  await expect(jobs.getByRole('listitem').filter({ hasText: 'Havnelys' })).toBeVisible()
  for (const card of await jobs.getByRole('listitem').all()) await expect(card).toContainText(/[3-9] vacancies/)
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await expect(jobs.getByRole('listitem')).toHaveCount(total)

  // Every pill on a card adds its filter, shown as a chip that can be removed.
  await kaveri.getByRole('link', { name: 'IN work permit' }).click()
  await expect(chips).toHaveText('Work permit: IN')
  await expect(page.getByLabel('Work permit', { exact: true })).toHaveValue('IN')
  await expect(kaveri).toBeVisible()
  await expect(lynfjord).toHaveCount(0)
  await kaveri.getByRole('link', { name: 'Hybrid' }).click()
  await expect(chips.getByRole('listitem')).toHaveText(['Work mode: Hybrid', 'Work permit: IN'])
  await expect(kaveri).toBeVisible()
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '17b-job-board-advanced-filters')
  await chips.getByRole('button', { name: 'Remove Work permit: IN' }).click()
  await chips.getByRole('button', { name: 'Remove Work mode: Hybrid' }).click()
  await expect(chips).toHaveCount(0)
  await expect(jobs.getByRole('listitem')).toHaveCount(total)

  // Search: words, then filters.
  await page.getByLabel('Search').fill('forecasting')
  await expect(page.getByText(new RegExp(`^[0-9]+ of ${total} jobs$`))).toBeVisible()
  await page.getByLabel('Seniority').selectOption('junior')
  await expect(jobs.getByRole('listitem')).toHaveCount(1)
  await expect(jobs.getByRole('link', { name: 'Junior Data Scientist' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await page.getByLabel('Work mode').selectOption('remote')
  await expect(jobs.getByRole('listitem')).toHaveCount(2)
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await page.getByLabel('Search').fill('energy')
  await expect(jobs.getByRole('listitem')).toHaveCount(1)
  await shot(page, '17-job-board-search')

  // Read a listing in full: the ad and the vacancies, not the rubric.
  await jobs.getByRole('link', { name: 'Data Scientist, Energy Demand Forecasting' }).click()
  await expect(page).toHaveURL(/\/jobs\/board-lynfjord-power$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Data Scientist, Energy Demand Forecasting')
  await expect(page.getByText('2 vacancies')).toBeVisible()
  await expect(page.getByText('Strong experience with time series forecasting.')).toBeVisible()
  const fit = page.getByRole('region', { name: 'How well you fit' })
  await expect(fit).toContainText('Strong fit')
  await expect(fit).toContainText('Connect to see your place among the connected candidates.')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)

  // Connect: John is now matched and ranked by the job, anonymously.
  await page.getByRole('button', { name: 'Connect my profile' }).click()
  await expect(page.getByRole('region', { name: 'Your connection' })).toContainText('Connected on')
  await expect(fit).toContainText('Not ranked yet')
  await shot(page, '18-job-listing-connected')
  const profile = await (await page.request.get(`/api/candidates/${candidate}/profile`)).json()
  type Ranked = { profile_id: string; rank: number }
  const ranked = async () => {
    const response = await page.request.post('/api/jobs/board-lynfjord-power/match')
    expect(response.ok()).toBe(true)
    const body = await response.json()
    return body.candidates as Ranked[]
  }
  const withJohn = await ranked()
  expect(withJohn).toHaveLength(13)
  const john = withJohn.find((c) => c.profile_id === profile.id)
  expect(john).toBeDefined()

  // Ranked: John sees his place among the connected candidates.
  await page.reload()
  await expect(fit).toContainText(`You're #${john!.rank} of 13 connected candidates`)
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '20-job-listing-place')

  // Back on the board, the job is marked as connected.
  await page.getByRole('link', { name: 'All jobs' }).click()
  const card = jobs.getByRole('listitem').filter({ hasText: 'Lynfjord Power' })
  await expect(card.getByText('Connected', { exact: true })).toBeVisible()

  // Withdraw: out of the job's next ranking.
  await expect(card.getByRole('group', { name: 'Your fit' })).toContainText(`You're #${john!.rank} of 13`)
  await card.getByRole('link').first().click()
  await page.getByRole('button', { name: 'Withdraw' }).click()
  await expect(page.getByRole('button', { name: 'Connect my profile' })).toBeEnabled()
  await expect(fit).toContainText('Connect to see your place among the connected candidates.')
  await shot(page, '19-job-listing-withdrawn')
  const without = (await ranked()).map((c) => c.profile_id)
  expect(without).toHaveLength(12)
  expect(without).not.toContain(profile.id)

  // Connect and withdraw from the card on the board, the same action as on the listing.
  await page.getByRole('link', { name: 'All jobs' }).click()
  const title = 'Data Scientist, Energy Demand Forecasting'
  await card.getByRole('button', { name: `Connect my profile: ${title}` }).click()
  await expect(page.getByText('Your profile is connected to Lynfjord Power A/S.')).toBeVisible()
  await expect(card.getByText('Connected', { exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: `Withdraw: ${title}` })).toBeEnabled()
  await expect(card.getByRole('group', { name: 'Your fit' })).toBeVisible()
  expect((await ranked()).map((c) => c.profile_id)).toContain(profile.id)
  await card.scrollIntoViewIfNeeded()
  await shot(page, '20b-job-board-card-connected', { fullPage: false })
  await card.getByRole('button', { name: `Withdraw: ${title}` }).click()
  await expect(card.getByRole('button', { name: `Connect my profile: ${title}` })).toBeEnabled()
  await expect(card.getByText('Connected', { exact: true })).toHaveCount(0)
  expect((await ranked()).map((c) => c.profile_id)).not.toContain(profile.id)
})

test('reveal, request and apply: John Doe applies to one job and declines another', async ({ page }) => {
  // John approves his profile and connects to two demo jobs.
  await page.goto('/candidates')
  await page.getByRole('button', { name: 'Try the John Doe demo' }).click()
  await expect(page).toHaveURL(/\/material$/)
  const candidate = page.url().match(/\/candidates\/([^/]+)\//)![1]
  await page.getByRole('button', { name: 'Build my profile' }).click()
  await page.getByRole('button', { name: "Fill in John's review" }).click()
  await page.getByRole('button', { name: 'Save and approve' }).click()
  await expect(page).toHaveURL(/\/questions$/)
  expect((await page.request.post('/api/demos/board')).ok()).toBe(true)
  const jobs = ['board-fjord-grocery', 'board-lynfjord-power']
  for (const job of jobs) {
    await page.goto(`/candidates/${candidate}/jobs/${job}`)
    await page.getByRole('button', { name: 'Connect my profile' }).click()
    await expect(page.getByRole('region', { name: 'Your connection' })).toContainText('Connected on')
  }
  const glance = page.getByRole('group', { name: 'How far candidates got' })
  const profile = await (await page.request.get(`/api/candidates/${candidate}/profile`)).json()

  // The employer matches each job, and finds John only by his alias.
  const aliasOn = async (job: string) => {
    const shortlist = await (await page.request.get(`/api/jobs/${job}/shortlist`)).json()
    const card = shortlist.candidates.find((c: { profile_id: string }) => c.profile_id === profile.id)
    expect(card.contact).toBeNull()
    expect(card.evidence).toEqual([])
    expect(JSON.stringify(shortlist)).not.toMatch(/John Doe|john\.doe@example\.com/)
    return card.alias as string
  }
  const employer = async (job: string) => {
    await page.goto(`/jobs/${job}/shortlist`)
    await page.getByRole('button', { name: /^(Match candidates|Match again)$/ }).click()
    await expect(page.getByText(/^Ranked \d+ candidates\.$/)).toBeVisible()
    const alias = await aliasOn(job)
    const card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { level: 3, name: alias }) })
    await expect(card).toBeVisible()
    expect(await page.locator('main').textContent()).not.toMatch(/John Doe|john\.doe@example\.com/)
    return card
  }

  // Fjord Grocery: reveal John, then ask him to apply.
  let card = await employer(jobs[0])
  const counts = page.getByRole('group', { name: 'How far candidates got' })
  await expect(counts).toContainText('13 connected')
  await expect(counts).toContainText('0 revealed')
  await card.getByRole('button', { name: /^Reveal: / }).click()
  await expect(card.getByRole('heading', { level: 3 })).toContainText('John Doe')
  await expect(card.getByRole('link', { name: 'john.doe@example.com' })).toBeVisible()
  await expect(counts).toContainText('1 revealed')
  await card.getByRole('button', { name: 'Request application: John Doe' }).click()
  await expect(card.getByRole('button', { name: 'Waiting for application: John Doe' })).toBeDisabled()
  await expect(counts).toContainText('1 asked to apply')
  await expect(counts).toContainText('0 applications')

  // John sees the request on the board and on the listing, and can't withdraw now.
  await page.goto(`/candidates/${candidate}/jobs`)
  const requests = page.getByRole('region', { name: 'Asked to apply' })
  await expect(requests).toContainText('Fjord Grocery ApS asked you to apply for Senior Data Scientist')
  const board = page.getByRole('list', { name: 'Jobs' })
  await expect(board.getByText('Asked to apply', { exact: true })).toHaveCount(1)
  await shot(page, '22-job-board-asked-to-apply', { fullPage: false })
  await requests.getByRole('link', { name: 'Answer' }).click()
  await expect(page).toHaveURL(new RegExp(`/jobs/${jobs[0]}$`))
  await expect(page.getByRole('region', { name: 'Your connection' })).toContainText('Revealed on')
  await expect(page.getByRole('button', { name: 'Withdraw' })).toHaveCount(0)
  await expect(glance).toContainText('1 revealed')
  await expect(glance).toContainText('1 asked to apply')
  const asked = page.getByRole('region', { name: 'Asked to apply' })
  await expect(asked).toContainText('Fjord Grocery ApS asks you to apply')
  await expect(asked.getByRole('button', { name: 'Apply' })).toBeDisabled()
  await asked.getByLabel('Cover letter').fill('Dear Fjord Grocery, I would love to build your demand forecasts.')
  await asked.getByLabel('Files').setInputFiles({
    name: 'john-doe-cv.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# John Doe\n\nData scientist in Copenhagen.\n'),
  })
  await asked.scrollIntoViewIfNeeded()
  await shot(page, '23-job-listing-apply', { fullPage: false })
  await asked.getByRole('button', { name: 'Apply' }).click()
  const sent = page.getByRole('region', { name: 'Your application' })
  await expect(sent).toContainText('You applied')
  await expect(sent.getByRole('link', { name: 'john-doe-cv.md' })).toBeVisible()
  await expect(glance).toContainText('1 application')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)

  // The employer sees the application, and can download its file.
  card = page.getByRole('listitem').filter({ hasText: 'John Doe' })
  await page.goto(`/jobs/${jobs[0]}/shortlist`)
  await expect(card.getByRole('button', { name: 'Applied: John Doe' })).toBeDisabled()
  const application = page.getByRole('region', { name: 'Application from John Doe' })
  await expect(application).toContainText('I would love to build your demand forecasts.')
  const download = page.waitForEvent('download')
  await application.getByRole('link', { name: 'john-doe-cv.md' }).click()
  expect((await download).suggestedFilename()).toBe('john-doe-cv.md')
  await expect(counts).toContainText('1 application')
  await application.scrollIntoViewIfNeeded()
  await shot(page, '24-shortlist-application', { fullPage: false })

  // Lynfjord Power: revealed and asked, John declines.
  card = await employer(jobs[1])
  await card.getByRole('button', { name: /^Reveal: / }).click()
  await card.getByRole('button', { name: 'Request application: John Doe' }).click()
  await expect(card.getByRole('button', { name: 'Waiting for application: John Doe' })).toBeDisabled()
  await page.goto(`/candidates/${candidate}/jobs/${jobs[1]}`)
  await page.getByRole('region', { name: 'Asked to apply' }).getByRole('button', { name: 'Decline' }).click()
  await expect(page.getByRole('region', { name: 'Your application' })).toContainText('You declined')
  await expect(glance).toContainText('1 asked to apply')
  await expect(glance).toContainText('0 applications')
  await page.goto(`/jobs/${jobs[1]}/shortlist`)
  await expect(page.getByRole('button', { name: 'Declined: John Doe' })).toBeDisabled()
  await expect(page.getByRole('region', { name: 'Application from John Doe' })).toHaveCount(0)

  // Smørblomst Mejeri: John connects, and the employer reveals five others, so his
  // dashboard compares him with those revealed.
  const dairy = 'board-smoerblomst-dairy'
  await page.goto(`/candidates/${candidate}/jobs/${dairy}`)
  await page.getByRole('button', { name: 'Connect my profile' }).click()
  await expect(page.getByRole('region', { name: 'Your connection' })).toContainText('Connected on')
  expect((await page.request.post(`/api/jobs/${dairy}/match`)).ok()).toBe(true)
  const shortlist = await (await page.request.get(`/api/jobs/${dairy}/shortlist`)).json()
  const others = shortlist.candidates
    .map((c: { profile_id: string }) => c.profile_id)
    .filter((id: string) => id !== profile.id)
    .slice(0, 5)
  for (const id of others) {
    expect((await page.request.post(`/api/jobs/${dairy}/candidates/${id}/reveal`)).ok()).toBe(true)
  }

  // His dashboard: three jobs, revealed on two, asked to apply on two.
  await page.goto(`/candidates/${candidate}/dashboard`)
  await page.getByRole('tab', { name: 'Your jobs' }).click()
  await expect(page).toHaveURL(/\?sheet=jobs$/)
  const yours = page.getByRole('list', { name: 'Jobs you connected to' })
  await expect(yours.locator(':scope > li')).toHaveCount(3)
  const rate = page.getByLabel('Your success rate')
  await expect(rate).toContainText('Revealed67%2 of 3')
  await expect(rate).toContainText('Asked to apply67%2 of 3')
  const dairyRow = yours.locator(':scope > li').filter({ hasText: 'Smørblomst Mejeri' })
  await expect(dairyRow).toContainText('Connected')
  await expect(dairyRow.getByRole('button', { name: /Compare with others/ })).toBeVisible()
  await expect(yours.locator(':scope > li').filter({ hasText: 'Fjord Grocery' })).toContainText('Applied')
  await expect(yours.locator(':scope > li').filter({ hasText: 'Lynfjord' })).toContainText('Declined')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '26-candidate-jobs', { fullPage: false })

  // Compared with the five revealed on Smørblomst Mejeri, though he wasn't: where
  // he stands out, where they're ahead, and a spider chart of own levels.
  await dairyRow.getByRole('button', { name: /Compare with others/ }).click()
  await expect(page).toHaveURL(new RegExp(`sheet=compare&job=${dairy}$`))
  const compared = page.getByRole('group', { name: 'Compared with: Revealed' })
  await expect(compared).toBeVisible()
  await expect(compared.getByText('Where you stand out')).toBeVisible()
  await expect(compared.getByText("Where they're ahead")).toBeVisible()
  await expect(compared.getByRole('img', { name: /Your own levels and the median of revealed/ })).toBeVisible()
  await expect(page.getByLabel('Compare with').getByRole('radio', { name: 'Applied' })).toBeDisabled()
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await shot(page, '29-candidate-compared')
})

test('messages after a reveal: the employer and John Doe write to each other', async ({ page }) => {
  // John approves his profile and connects to a demo job no other test reveals him on.
  await page.goto('/candidates')
  await page.getByRole('button', { name: 'Try the John Doe demo' }).click()
  await expect(page).toHaveURL(/\/material$/)
  const candidate = page.url().match(/\/candidates\/([^/]+)\//)![1]
  await page.getByRole('button', { name: 'Build my profile' }).click()
  await page.getByRole('button', { name: "Fill in John's review" }).click()
  await page.getByRole('button', { name: 'Save and approve' }).click()
  await expect(page).toHaveURL(/\/questions$/)
  const created = await (await page.request.post('/api/demos/board')).json()
  const job = (created.jobs as string[]).find((j) => j.includes('havnelys'))!
  const company = (await (await page.request.get(`/api/board/${job}`)).json()).company as string
  await page.goto(`/candidates/${candidate}/jobs/${job}`)
  await page.getByRole('button', { name: 'Connect my profile' }).click()
  await expect(page.getByRole('region', { name: 'Your connection' })).toContainText('Connected on')
  const profile = await (await page.request.get(`/api/candidates/${candidate}/profile`)).json()

  // Before a reveal there is no thread, in the app or the API.
  await expect(page.getByRole('region', { name: `Messages with ${company}` })).toHaveCount(0)
  const early = await page.request.post(`/api/candidates/${candidate}/messages/${job}`, { data: { text: 'Hi' } })
  expect(early.status()).toBe(409)
  expect((await page.request.post(`/api/jobs/${job}/match`)).ok()).toBe(true)
  const thread = `/api/jobs/${job}/candidates/${profile.id}/messages`
  expect((await page.request.get(thread)).status()).toBe(404)
  expect((await page.request.post(thread, { data: { text: 'Hi' } })).status()).toBe(409)

  // The employer reveals John and writes to him from his card.
  await page.goto(`/jobs/${job}/shortlist`)
  const shortlist = await (await page.request.get(`/api/jobs/${job}/shortlist`)).json()
  const alias = shortlist.candidates.find((c: { profile_id: string }) => c.profile_id === profile.id).alias
  let card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { level: 3, name: alias }) })
  await expect(card.getByRole('button', { name: /^Messages with/ })).toHaveCount(0)
  await card.getByRole('button', { name: /^Reveal: / }).click()
  await expect(card.getByRole('heading', { level: 3 })).toContainText('John Doe')
  card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { level: 3, name: /John Doe/ }) })
  await card.getByRole('button', { name: 'Messages with John Doe' }).click()
  let messages = card.getByRole('region', { name: 'Thread with John Doe' })
  await expect(messages).toContainText('No messages yet. Write the first to John Doe.')
  await messages.getByLabel('Message to John Doe').fill('Hi John, thanks for connecting. Could we talk on Tuesday?')
  await messages.getByRole('button', { name: 'Send' }).click()
  await expect(messages.getByRole('list', { name: 'Messages' })).toContainText('Could we talk on Tuesday?')
  await expect(messages.getByLabel('Message to John Doe')).toHaveValue('')
  await messages.scrollIntoViewIfNeeded()
  await shot(page, '27-shortlist-messages', { fullPage: false })

  // John sees one new message on the board, reads it on the listing, and answers.
  await page.goto(`/candidates/${candidate}/jobs`)
  const board = page.getByRole('list', { name: 'Jobs' })
  const listing = board.getByRole('listitem').filter({ hasText: company })
  await expect(listing.getByText('1 new message')).toBeVisible()
  await listing.getByRole('link').first().click()
  await expect(page).toHaveURL(new RegExp(`/jobs/${job}$`))
  messages = page.getByRole('region', { name: `Thread with ${company}` })
  await expect(messages).toContainText('Could we talk on Tuesday?')
  await expect(messages.getByText('New', { exact: true })).toBeVisible()
  await messages.getByLabel(`Message to ${company}`).fill('Yes, Tuesday works. Any time after ten.')
  await messages.getByRole('button', { name: 'Send' }).click()
  const items = messages.getByRole('list', { name: 'Messages' }).getByRole('listitem')
  await expect(items).toHaveCount(2)
  await expect(items.last()).toContainText('Any time after ten.')
  expect(await page.locator('main').textContent()).not.toMatch(HIDDEN_FROM_CANDIDATES)
  await messages.scrollIntoViewIfNeeded()
  await shot(page, '28-job-listing-messages', { fullPage: false })
  // Read now: the board no longer counts it.
  await page.goto(`/candidates/${candidate}/jobs`)
  await expect(page.getByRole('list', { name: 'Jobs' })).toBeVisible()
  await expect(page.getByText(/new message/)).toHaveCount(0)

  // The employer sees the answer as new, newest at the bottom.
  await page.goto(`/jobs/${job}/shortlist`)
  await expect(card.getByText('1 new message')).toBeVisible()
  await card.getByRole('button', { name: 'Messages with John Doe' }).click()
  messages = card.getByRole('region', { name: 'Thread with John Doe' })
  const thread2 = messages.getByRole('list', { name: 'Messages' }).getByRole('listitem')
  await expect(thread2).toHaveCount(2)
  await expect(thread2.first()).toContainText('Could we talk on Tuesday?')
  await expect(thread2.last()).toContainText('Any time after ten.')
  await expect(card.getByText('1 new message')).toHaveCount(0)

  // The messages are John's data: his export has both.
  const exported = await (await page.request.get(`/api/candidates/${candidate}/messages`)).json()
  const mine = exported.find((t: { job: string }) => t.job === job)
  expect(mine.messages.map((m: { sender: string }) => m.sender)).toEqual(['employer', 'candidate'])
})

test('a real candidate is refused paid calls, and told about the demo', async ({ page }) => {
  await page.goto('/candidates')
  await page.getByLabel('Name').fill('jane-example')
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page).toHaveURL(/\/candidates\/jane-example\/material$/)
  await expect(page.getByText('No files yet. Your CV is a good start.')).toBeVisible()

  await page.getByTestId('file-input').setInputFiles({
    name: 'cv.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# Jane Example\n\nAnalyst at Example Ltd, 2020 to now. SQL and Python.\n'),
  })
  await expect(page.getByRole('button', { name: 'Remove cv.md' })).toBeVisible()
  await shot(page, '10-candidate-upload')

  await page.getByRole('button', { name: 'Build my profile' }).click()
  await expect(page.getByText(/paid calls are off on this server/)).toBeVisible()
  await expect(page).toHaveURL(/\/material$/)

  // Nothing was extracted, so the review stays locked.
  const steps = page.getByRole('navigation', { name: 'Your steps' })
  await expect(steps.getByRole('link', { name: /Review/ })).toHaveCount(0)

  await page.getByRole('button', { name: 'Remove cv.md' }).click()
  await expect(page.getByText('No files yet. Your CV is a good start.')).toBeVisible()
})

test('the keyboard reaches the main actions', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /^Start/ })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/candidates$/)
})
