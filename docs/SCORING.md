# ICP Scoring

This engine implements the incumbent-software ICP from `icp.md`.

## Hard Gates

A company must pass or be manually reviewed on these gates before human research
time is justified:

- Founded before 2025
- Product company, not primarily services or consulting
- B2B or B2B2C
- Proprietary workflow or data assets
- Enough budget or customer scale
- Not AI-native

Unknown facts create manual-review flags. They do not silently pass.

## AI Posture

AI posture is scored separately from AI potential:

- `0`: no visible AI
- `1`: generic AI copy
- `2`: thin feature such as writer, summarizer, chatbot, search, or Q&A
- `3`: grounded assistant, mostly read-only or advisory
- `4`: embedded workflow AI
- `5`: AI-native or agentic

The ICP sweet spot is usually `0-2`. Score `3` can be useful when the wedge is
deeper workflow automation. Scores `4-5` are usually reject or nurture.

## 100-Point Lead Score

- AI gap: `30`
- Data/workflow moat: `25`
- Commercial urgency: `20`
- Budget/access: `15`
- Feasibility: `10`

Tiering:

- Tier A: `75-100`
- Tier B: `60-74`
- Reject/nurture: below `60`, or any failed hard gate

## Evidence Discipline

The engine stores evidence IDs and source URLs. Gemini may classify evidence, but
the local scorer validates model output and clamps scores to accepted ranges.
The model must not invent missing facts.
