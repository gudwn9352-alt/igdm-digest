export const meta = {
  name: 'classify-reel-candidates',
  description: 'Classify Instagram reel candidates (real people, not frontal talking-head) and adversarially verify the top picks per keyword',
  phases: [
    { title: 'Classify', detail: 'one agent per batch of ~20 contact sheets' },
    { title: 'Verify', detail: 'per keyword, independent skeptic re-checks the top picks' },
  ],
}

const W = args.dir
const REF = args.ref
const BATCHES = args.batches // [{idx, folder}]

const CRITERIA = `
GOAL: collect reference footage of REAL PEOPLE acting out everyday situations (couples, parents/family, daily life, grocery shopping, hospital, studying, personal finance) to later remake with an AI video model (Kling reference-to-video: it copies camera movement and body motion from a reference clip).

INCLUDE (eligible=true) only if ALL hold:
- Real, live-action humans are clearly visible for most of the video (not just hands, not tiny in the distance for a moment).
- People are DOING something / acting out a situation: skit, vlog footage, candid daily scenes, interactions between people, walking, shopping, cooking, studying etc.

EXCLUDE (eligible=false) if ANY:
- "talking_head": a person faces the camera frontally and explains/talks to the viewer for most of the video (like the reference contact sheet at ${REF}: woman with headband looking into camera, holding a lavalier mic, captions). Selfie-style monologues, lectures to camera, interview-style face-to-camera explanation, podcast to camera also count. A brief to-camera moment inside an otherwise action-driven video is OK.
- "no_people": products, food, scenery, objects, only hands, screen recordings, charts, text cards.
- "slideshow_stock": photo slideshow, stock images/memes, compilations of pictures, mostly static images or heavy graphics/text.
- "animation_ai": cartoons, 3D, obviously AI-generated characters.
- "other": anything else unusable (e.g. mostly black frames, ad graphics). Explain.

Also score remake_value 0-10: how useful as motion/camera reference for remaking with different people (clear full/medium body actions, interesting staging, multiple shots, people interacting = high; static, mostly close-up faces, low light, very cluttered text overlays = low).`

const CLASSIFY_SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          code: { type: 'string' },
          eligible: { type: 'boolean' },
          category: { type: 'string', enum: ['eligible', 'talking_head', 'no_people', 'slideshow_stock', 'animation_ai', 'other'] },
          people: { type: 'string', description: 'who appears, e.g. "married couple 30s", "elderly parents + adult daughter"' },
          scene: { type: 'string', description: 'one-line description of what happens and the setting, in Korean' },
          remake_value: { type: 'integer', minimum: 0, maximum: 10 },
          reason: { type: 'string' },
        },
        required: ['code', 'eligible', 'category', 'people', 'scene', 'remake_value', 'reason'],
      },
    },
  },
  required: ['results'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          code: { type: 'string' },
          keep: { type: 'boolean' },
          category: { type: 'string', enum: ['eligible', 'talking_head', 'no_people', 'slideshow_stock', 'animation_ai', 'other'] },
          remake_value: { type: 'integer', minimum: 0, maximum: 10 },
          reason: { type: 'string' },
        },
        required: ['code', 'keep', 'category', 'remake_value', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

phase('Classify')
const classified = await parallel(BATCHES.map(b => () =>
  agent(`You are classifying Instagram Reels candidates for the keyword folder "${b.folder}".
${CRITERIA}

First Read the reference contact sheet ${REF} (8 frames of the EXCLUDED talking-head style).
Then Read the batch file ${W}/batch_${String(b.idx).padStart(2, '0')}.json. For EVERY item in it, Read its "sheet" image (12 frames sampled across the whole video, timestamps in yellow, 2 rows x 6) and judge it. Use the caption only as a hint; the frames decide. Do not skip any item; return one result per item with the exact code.`,
    { label: `classify:${b.folder}#${b.idx}`, phase: 'Classify', schema: CLASSIFY_SCHEMA })
    .then(r => r ? r.results.map(x => ({ ...x, folder: b.folder, batch: b.idx })) : null)
))

const all = classified.filter(Boolean).flat()
const missingBatches = BATCHES.filter((b, i) => !classified[i]).map(b => b.idx)
if (missingBatches.length) log(`classification failed for batches: ${missingBatches.join(', ')}`)

const folders = [...new Set(BATCHES.map(b => b.folder))]
phase('Verify')
const verified = await parallel(folders.map(folder => () => {
  const picks = all.filter(x => x.folder === folder && x.eligible).sort((a, b) => b.remake_value - a.remake_value).slice(0, 16)
  if (!picks.length) { log(`${folder}: no eligible candidates`); return Promise.resolve({ folder, verdicts: [] }) }
  const list = picks.map(p => `- code=${p.code} sheet=${W}/sheets/${folder}/${p.code}.jpg (first-pass: ${p.scene}; value ${p.remake_value})`).join('\n')
  return agent(`You are an independent SKEPTIC re-checking candidates that another agent marked eligible for the keyword folder "${folder}".
${CRITERIA}

First Read the reference contact sheet ${REF} (the EXCLUDED talking-head style). Then Read EVERY sheet below yourself and try to REFUTE eligibility: look hard for frontal to-camera explaining, slideshows/stock, no real people, AI/animation. If uncertain whether it is a talking-head explainer, set keep=false. Give your own remake_value. Return one verdict per code.

${list}`, { label: `verify:${folder}`, phase: 'Verify', schema: VERIFY_SCHEMA })
    .then(r => ({ folder, verdicts: r ? r.verdicts : null }))
}))

return { all, verified, missingBatches }
