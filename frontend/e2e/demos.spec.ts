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
