import path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

// Both demos end to end in a real browser, against the real API, for free: the
// demos replay recorded answers. Screenshots of each step go to e2e/screenshots/.

const SHOTS = path.join(import.meta.dirname, 'screenshots')
// Words for the assessment, which a candidate never sees.
const ASSESSMENT = /estimat|confidence|claim support|overclaim/i

/** A screenshot of the whole page; of the window only where a bar is fixed at the bottom. */
async function shot(page: Page, name: string, { fullPage = true } = {}) {
  // Let toasts and transitions settle so the pictures are stable.
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage })
}

test('the John Doe demo: material, review, questions and profile', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Upload your material once')
  await shot(page, '01-home')

  await page.getByRole('button', { name: 'Try the John Doe demo' }).click()
  await expect(page).toHaveURL(/\/candidates\/john-doe-demo[-\d]*\/material$/)
  await expect(page.getByText('This is the John Doe demo')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload files' })).toHaveCount(0)
  await shot(page, '02-candidate-material')

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
  await expect(steps.getByRole('link', { name: /Questions/ })).toContainText('(done)')
  expect(await page.locator('main').textContent()).not.toMatch(ASSESSMENT)
  await shot(page, '06-candidate-profile')

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
  await expect(page.getByText('Version 2')).toBeVisible()
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
  // The 12 of the pool, and the John Doe demo if an earlier test approved him.
  expect(Number((await ranked.textContent())?.split(' ')[0])).toBeGreaterThanOrEqual(12)
  await expect(page.getByRole('meter', { name: /^Total for Candidate/ }).first()).toBeVisible()
  // Each card: the scorer's total, and the baseline on own and on estimated levels.
  await expect(page.getByRole('meter', { name: /^Own rating for Candidate/ }).first()).toBeVisible()
  await expect(page.getByRole('meter', { name: /^Estimated from evidence for Candidate/ }).first()).toBeVisible()
  await shot(page, '11-shortlist', { fullPage: false })

  // The three who fail a hard filter: below a divider, scored, with the filter named.
  const divider = page.getByRole('separator', { name: /Don't meet the requirements/ })
  await expect(divider).toContainText('3')
  const failing = page.getByRole('list', { name: "Don't meet the requirements" })
  await expect(failing.getByRole('listitem')).toHaveCount(3)
  await expect(failing.getByText(/^Doesn't meet/)).toHaveCount(4) // One fails two filters.
  await expect(failing.getByRole('meter', { name: /^Total for Candidate/ })).toHaveCount(3)
  await divider.scrollIntoViewIfNeeded()
  await shot(page, '15-shortlist-failed', { fullPage: false })
  await page.getByRole('heading', { name: 'Shortlist', exact: true }).scrollIntoViewIfNeeded()

  // Why the first is first: a score per criterion, with the quotes it cites.
  const first = page.getByRole('listitem').filter({ has: page.getByLabel('Rank 1') }).first()
  await first.getByRole('button', { name: /^Why for/ }).click()
  const reasons = page.getByRole('region', { name: /^Reasons for/ })
  await expect(reasons.getByRole('meter').first()).toBeVisible()
  await expect(reasons.locator('blockquote').first()).toBeVisible()
  await reasons.scrollIntoViewIfNeeded()
  await shot(page, '12-shortlist-reasons', { fullPage: false })
  await first.getByRole('button', { name: /^Hide for/ }).click()

  // Compare the top three on the rubric's skills, own and estimated levels.
  const boxes = page.getByRole('checkbox', { name: /^Compare Candidate/ })
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

  // Reveal the first and ask the second to apply: recorded, no payment, no name.
  await first.getByRole('button', { name: /^Reveal Candidate/ }).click()
  await expect(page.getByText(/recorded\. No payment is taken yet/)).toBeVisible()
  await expect(page.getByText('Reveals: 1 of 10')).toBeVisible()
  await expect(first.getByRole('button', { name: /^Reveal requested/ })).toBeDisabled()
  const second = page.getByRole('listitem').filter({ has: page.getByLabel('Rank 2') }).first()
  await second.getByRole('button', { name: /^Request application/ }).click()
  await expect(second.getByRole('button', { name: /^Application requested/ })).toBeDisabled()
  expect(await page.locator('main').textContent()).not.toMatch(POOL_NAMES)

  // The LLM scorer replays recorded answers in the demo, so it is free too.
  await page.getByRole('radio', { name: 'LLM' }).click()
  await expect(page.getByText(/replays recorded answers/)).toBeVisible()
  await page.getByRole('button', { name: 'Match candidates' }).click()
  await expect(ranked).toBeVisible()
  await expect(page.getByRole('meter', { name: /^Total for Candidate/ }).first()).toBeVisible()
  // The comparison stays: the same people, scored another way.
  await expect(chart).toBeVisible()
  // The requests are the job's, whichever scorer ranks.
  await expect(page.getByText('Reveals: 1 of 10')).toBeVisible()
  expect(await page.locator('main').textContent()).not.toMatch(POOL_NAMES)
  await shot(page, '14-shortlist-llm', { fullPage: false })
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
