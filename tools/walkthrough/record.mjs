// Records a silent walkthrough of the running app for voiceover.
//
//   make rehearse && make serve      (in one terminal; the app must be on :8000)
//   make video                       (in another)
//
// Nothing here is staged. The script clicks through the real app, and the analyst,
// clarification and co-pilot steps make live model calls while the camera runs.
// Output: tools/walkthrough/out/walkthrough.webm and timeline.json (scene start times).

import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(HERE, 'out')
const BASE = process.env.QUOTELINE_URL ?? 'http://localhost:8000'
const SIZE = { width: 1440, height: 900 }
const RFX = 'RFX-0147'

fs.rmSync(OUT, { recursive: true, force: true })
fs.mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: SIZE,
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: SIZE },
  acceptDownloads: true,
  colorScheme: 'light',
})

// A visible cursor, drawn by the page so it is in the video. Scene captions are added by render.mjs.
await context.addInitScript(() => {
  localStorage.setItem('quoteline-theme', 'light')
  localStorage.setItem('quoteline-persona', 'buyer')
  window.addEventListener('DOMContentLoaded', () => {
    const cursor = document.createElement('div')
    cursor.id = 'qc-cursor'
    cursor.style.cssText =
      'position:fixed;z-index:99999;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'border:2px solid #BF4A1F;background:rgba(191,74,31,.18);pointer-events:none;transition:transform .12s,background .12s'
    document.body.append(cursor)
    document.addEventListener('mousemove', (e) => {
      cursor.style.left = `${e.clientX}px`
      cursor.style.top = `${e.clientY}px`
    }, true)
    document.addEventListener('mousedown', () => {
      cursor.style.transform = 'scale(.6)'
      cursor.style.background = 'rgba(191,74,31,.55)'
    }, true)
    document.addEventListener('mouseup', () => {
      cursor.style.transform = 'scale(1)'
      cursor.style.background = 'rgba(191,74,31,.18)'
    }, true)
  })
})

const page = await context.newPage()
page.setDefaultTimeout(20_000)
const started = Date.now()
const timeline = []
const problems = []
let mouse = { x: 720, y: 450 }

const stamp = () => {
  const s = Math.round((Date.now() - started) / 1000)
  return `${String(Math.floor(s / 60)).padStart(1, '0')}:${String(s % 60).padStart(2, '0')}`
}
const PACE = Number(process.env.PACE ?? 1.35) // stretch every pause to leave room for narration
const dwell = (ms) => page.waitForTimeout(ms * PACE)

async function scene(title) {
  timeline.push({ at: stamp(), seconds: Math.round((Date.now() - started) / 1000), scene: title })
  console.log(`${stamp()}  ${title}`)
}

async function glide(x, y) {
  const steps = Math.max(12, Math.round(Math.hypot(x - mouse.x, y - mouse.y) / 22))
  await page.mouse.move(x, y, { steps })
  mouse = { x, y }
}

async function point(locator, pause = 700) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  if (!box) throw new Error('element has no box')
  await glide(box.x + box.width / 2, box.y + box.height / 2)
  await dwell(pause)
}

async function click(locator, { before = 450, after = 900 } = {}) {
  await locator.first().waitFor({ state: 'visible' })
  await point(locator.first(), before)
  await page.mouse.down()
  await dwell(90)
  await page.mouse.up()
  await dwell(after)
}

async function scroll(dy, steps = 14) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, dy / steps)
    await dwell(45)
  }
  await dwell(350)
}

async function attempt(name, fn) {
  try {
    await fn()
  } catch (error) {
    problems.push(`${stamp()} ${name}: ${String(error.message).split('\n')[0]}`)
    console.log(`   ! ${name} skipped: ${String(error.message).split('\n')[0]}`)
    await page.keyboard.press('Escape').catch(() => {})
  }
}

const stage = (name) => page.getByRole('navigation', { name: 'Stages' }).getByRole('link', { name: new RegExp(`^\\d?\\s*${name}`) })
const cell = (vendor, line) => page.getByRole('button', { name: new RegExp(`^${vendor} ${line}:`) })
const card = (vendor, title) => page.locator('div.grid.rounded-card', { hasText: title }).filter({ hasText: vendor })
const button = (name, exact = false) => page.getByRole('button', { name, exact })

// ── 1. Compare: five formats, one grid ────────────────────────────────────────────────
await page.goto(`${BASE}/rfx/${RFX}/compare`)
await cell('Kaveri Boards', 'L01').waitFor()
await dwell(1200)
await scene('Five replies, five formats, one grid')
await glide(300, 190)
await point(page.getByText('Assumptions in force'), 1500)
await point(page.getByText(/USD 1 = ₹/).first(), 2200)
for (const vendor of ['Meridian Packaging', 'Sri Balaji Corrugators', 'Kaveri Boards', 'NorthBox Ltd', 'Anand Papers']) {
  await point(page.locator('th', { hasText: vendor }), 1500)
}
await point(cell('Kaveri Boards', 'L01'), 1600)
await point(cell('Sri Balaji Corrugators', 'L04'), 1300)
await point(cell('NorthBox Ltd', 'L05'), 1300)
await point(cell('NorthBox Ltd', 'L08'), 1300)
await glide(700, 600)
await scroll(1500, 30)
await point(page.getByText('Extended total, 30 lines'), 2600)
await point(page.getByText('Freight, as stated by vendor'), 2000)
await point(page.getByText(/need a decision before this comparison/), 3200)
await scroll(-1600, 24)

await scene('The same grid, exactly as each vendor quoted')
await click(page.getByRole('radio', { name: 'Raw as quoted' }), { after: 1200 })
await point(cell('Meridian Packaging', 'L01'), 1200)
await point(cell('Kaveri Boards', 'L01'), 1200)
await point(cell('NorthBox Ltd', 'L01'), 1200)
await point(cell('Anand Papers', 'L01'), 1600)
await click(page.getByRole('radio', { name: 'Normalised' }), { after: 1000 })

// ── 3. Provenance: every figure is one click from its source ─────────────────────────
await scene('Any number, one click from its source')
await click(cell('Meridian Packaging', 'L01'), { after: 1400 })
await attempt('meridian popover', async () => {
  await point(page.getByText('found in file').first(), 2200)
  await point(page.getByText('Readings').first(), 2000)
  await point(page.getByText('Arithmetic').first(), 2600)
})
await page.keyboard.press('Escape')
await dwell(700)

await scene('"Per box, packed 100 per bundle": the system will not guess')
await click(cell('Kaveri Boards', 'L01'), { after: 1500 })
await attempt('kaveri popover', async () => {
  await point(page.locator('blockquote').first(), 3200)
  await point(page.getByText('Why flagged').first(), 3000)
  await point(page.getByText(/One box is the stated pack/).first(), 3600)
  await click(button(/^One box is one piece/), { before: 1600, after: 2200 })
})
await point(cell('Kaveri Boards', 'L01'), 1800)

// ── 5. Responses: raw beside extraction ───────────────────────────────────────────────
await scene('The photo, beside what two models read from it')
await click(stage('Responses'), { after: 1800 })
await attempt('responses', async () => {
  await point(page.getByText('NorthBox Ltd').first(), 1500)
  const northbox = page.locator('div.rounded-card', { hasText: 'NorthBox Ltd' }).filter({ hasText: 'Raw beside extraction' }).last()
  await click(northbox.getByRole('button', { name: 'Raw beside extraction' }), { after: 2600 })
  await point(page.locator('img[alt*="as received"]'), 3200)
  await point(page.locator('[role="dialog"]').getByText('needs review').first(), 3200)
  await click(page.getByRole('radio', { name: 'Questionnaire' }), { after: 1600 })
  await point(page.getByText(/single unit at Bhiwandi/).first(), 3800)
  await click(page.getByRole('button', { name: 'Close' }), { after: 900 })
})

// ── 6. Review queue ───────────────────────────────────────────────────────────────────
await scene('Review queue: every interpretation computed, the buyer decides')
await click(page.getByRole('link', { name: /Review queue/ }), { after: 1800 })
await attempt('discount', async () => {
  const item = card('Sri Balaji', 'Conditional discount not applied')
  await point(item.getByText(/4% discount on lines above/).first(), 2600)
  await point(item.getByRole('button', { name: /lines whose value exceeds/ }), 2400)
  await click(item.getByRole('button', { name: /lines with a rate above/ }), { before: 1800, after: 1800 })
})
await attempt('blotted digit', async () => {
  const item = card('NorthBox', 'Reading uncertain')
  await point(item.getByText(/the two models disagree|a character is unclear/).first(), 3000)
  const exact = item.getByRole('button', { name: /^Use 3,935/ })
  await click((await exact.count()) ? exact : item.getByRole('button', { name: /^Use / }).first(), { before: 1500, after: 1800 })
})
await attempt('carry forward', async () => {
  const item = card('Anand', 'cannot be resolved')
  await point(item.getByText(/no price from last year/).first(), 2800)
  await click(item.getByRole('button', { name: 'Treat these lines as not quoted' }), { after: 1600 })
})

await scene('Ask the vendor: a drafted clarification, never sent automatically')
await attempt('ask vendor', async () => {
  const item = card('Kaveri', 'Freight not priced')
  await point(item.getByText(/FOB Chennai/).first(), 1800)
  await click(item.getByRole('button', { name: /^Ask Kaveri/ }), { after: 600 })
  await page.getByText('Clarification drafted').waitFor({ timeout: 90_000 })
  await dwell(1200)
  await point(page.locator('pre').last(), 7000)
  await click(button('Done', true), { after: 900 })
})

await scene('Acknowledge the rest: currency, freight, lines not quoted')
for (const [vendor, title] of [
  ['Kaveri', 'Quoted in a foreign currency'], ['Kaveri', 'Freight not priced'], ['Kaveri', 'Lines not quoted'],
  ['NorthBox', 'Lines not quoted'], ['Anand', 'Freight not priced'],
]) {
  await attempt(`${vendor} ${title}`, async () => {
    const item = card(vendor, title)
    await click(item.getByRole('button').first(), { before: 900, after: 1300 })
  })
}
await dwell(1500)

await scene('Outbox: the RFx went to five vendors; the clarification is a draft')
await attempt('sent', async () => {
  await click(stage('Sent'), { after: 1800 })
  await point(page.getByText('draft, not sent').first(), 2600)
  await point(page.getByText('written to outbox').first(), 2200)
})

// ── 9. Compare again, then an override ────────────────────────────────────────────────
await scene('Every cell now counts. An override needs a reason')
await click(stage('Compare'), { after: 2200 })
await scroll(1500, 24)
await point(page.getByText('Extended total, 30 lines'), 3000)
await scroll(-1600, 20)
await attempt('override', async () => {
  await click(cell('Anand Papers', 'L01'), { after: 1500 })
  await click(button('Override…'), { after: 700 })
  await page.keyboard.type('54000', { delay: 110 })
  await click(page.getByLabel('Reason'), { after: 300 })
  await page.keyboard.type('Vendor confirmed a rounded rate by phone', { delay: 45 })
  await click(button('Save override'), { before: 900, after: 2200 })
  await point(cell('Anand Papers', 'L01'), 2200)
})

// ── 10. Analyse ───────────────────────────────────────────────────────────────────────
await scene('The VP asks: split it among vendors who cleared quality?')
await click(stage('Analyse'), { after: 2000 })
await attempt('vp question', async () => {
  await click(page.locator('button[title^="What if we split it"]'), { after: 1500 })
  await glide(820, 330)
  await page.getByText('Query I ran').first().waitFor({ timeout: 180_000 })
  await dwell(1500)
  await scene('The answer, the rows it came from, and the query')
  await point(page.locator('article p').first(), 9000)
  await point(page.locator('article table').first(), 4500)
  await point(page.locator('article [role="img"]').first(), 3000)
  await point(page.getByText(/excluded from every figure|Every cell in the grid is counted/).first(), 3000)
  await click(page.locator('summary', { hasText: 'Query I ran' }).first(), { after: 1500 })
  await scroll(520, 14)
  await dwell(4500)
  await click(button('Save as award scenario').first(), { after: 2400 })
  await attempt('export', async () => {
    const download = page.waitForEvent('download', { timeout: 15_000 })
    await click(button(/Export XLSX/).first(), { after: 600 })
    await (await download).saveAs(path.join(OUT, 'analysis.xlsx'))
    await dwell(900)
  })
})

await scene('A question the data cannot answer')
await attempt('refusal', async () => {
  await click(page.getByLabel('Question'), { after: 300 })
  await page.keyboard.type('Which vendor has the best on-time delivery record?', { delay: 42 })
  await click(button('Ask', true), { after: 800 })
  await page.getByText('This cannot be answered from the quote data.').waitFor({ timeout: 120_000 })
  await dwell(800)
  await point(page.getByText('This cannot be answered from the quote data.'), 6500)
})

// ── 13. Award ─────────────────────────────────────────────────────────────────────────
await scene('Award: computed by an engine, with the cost of every rule')
await click(stage('Award'), { after: 2000 })
await attempt('award', async () => {
  await click(button('Draft the award from this').last(), { before: 1500, after: 2600 })
  await point(page.getByText('Recommended total'), 2400)
  await point(page.getByText('vs best single vendor'), 2600)
  await point(page.getByText("vs last year's contract"), 2400)
  await point(page.getByText('Review queue', { exact: true }).last(), 1800)
  await point(page.locator('table').first(), 3200)
  await point(page.getByText('Rules applied'), 3200)
  await point(page.getByText('Excluded and why'), 4200)
  await point(page.getByText(/Cost of the eligibility rules/), 3600)
  await point(page.getByText('Audit log'), 3600)
  await scene('Buyer sends it; the VP signs off')
  await click(button(/Send for approval/), { after: 2200 })
  await point(page.locator('header label select'), 900)
  await page.locator('header label select').selectOption('vp')
  await dwell(2200)
  await point(page.getByText('Approver sign-off'), 1600)
  await click(button('Approve', true), { before: 1200, after: 2800 })
  await attempt('award pack', async () => {
    const download = page.waitForEvent('download', { timeout: 15_000 })
    await click(button(/Download award pack/), { after: 600 })
    await (await download).saveAs(path.join(OUT, 'award_pack.pdf'))
    await dwell(1200)
  })
})

// ── 15. Run inspector ─────────────────────────────────────────────────────────────────
await scene('Every model call traced; accuracy measured against known truth')
await attempt('inspector', async () => {
  await click(button(/Run inspector/), { after: 2400 })
  await point(page.getByText(/Eval against the golden set/i), 2500)
  await point(page.getByText('Missed problems'), 3500)
  await point(page.locator('[role="dialog"] table').first(), 2500)
  await glide(900, 600)
  await scroll(700, 18)
  await dwell(2500)
  await click(page.getByRole('button', { name: 'Close' }), { after: 900 })
})

// ── 16. Co-pilot ──────────────────────────────────────────────────────────────────────
await scene('Where it starts: the buyer describes, the co-pilot structures')
await attempt('co-pilot', async () => {
  await page.locator('header label select').selectOption('buyer')
  await dwell(1200)
  await click(stage('Draft'), { after: 2200 })
  await click(page.getByRole('radio', { name: 'New RFx with co-pilot' }), { after: 1500 })
  await click(button(/Paste sample buyer notes/), { after: 2500 })
  await click(button('Send', true), { after: 1000 })
  await glide(1000, 420)
  await page.getByText('Structuring the draft…').waitFor({ state: 'hidden', timeout: 180_000 })
  await dwell(1500)
  await point(page.getByText(/without quantity|30 lines/).first(), 2500)
  await glide(1000, 500)
  await scroll(900, 22)
  await point(page.getByText('Still missing').or(page.getByText('Assumed, please confirm')).first(), 5000)
})

await scene('Quoteline · make demo')
await dwell(2500)

const video = page.video()
await context.close()
await browser.close()
const saved = await video.path()
fs.renameSync(saved, path.join(OUT, 'walkthrough.webm'))
fs.writeFileSync(path.join(OUT, 'timeline.json'), JSON.stringify({ length: stamp(), timeline, problems }, null, 2))
console.log(`\nRecorded ${stamp()} to ${path.join(OUT, 'walkthrough.webm')}`)
if (problems.length) console.log(`Steps skipped:\n  ${problems.join('\n  ')}`)
