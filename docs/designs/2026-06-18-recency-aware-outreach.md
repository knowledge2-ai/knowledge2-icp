# Recency-aware personalized outreach

**Status:** design (task #47) · **Date:** 2026-06-18 · **Author:** Anton + Claude

## Why

We've identified the ICP and collected rich per-account context. The next lever is turning that
context into a **personalized first-touch email per prospect** — using *relevant, recent* signals
("don't surface stuff from years ago"), not whatever keyword-matches.

The drafting already exists: `generate_outreach` (`claude_outreach.py`) writes a per-contact email
(subject/body/cta/angle) grounded **only** in scraped evidence + K2 account context, with a
deterministic template fallback, and explicitly forbids fabricated facts. What's missing is two
things, both confirmed by reading the pipeline:

1. **No date is captured anywhere.** `_fetch_or_read_cache` (`enrichment.py`) reads the HTTP
   response but keeps only `content-type` — it discards `Last-Modified` and never parses in-page
   publish dates. The `Evidence` model (`models.py`) has no date field. So there is no signal to
   filter "years ago" on.
2. **Selection ignores recency.** `select_prompt_evidence` → `_evidence_rank` (`evidence.py`) scores
   purely on signal *terms* (AI/data keywords, high-value paths). A 4-year-old blog post and last
   week's changelog rank identically when the keywords match.

## Decisions (Anton, 2026-06-18)

- **Template model: scaffold + LLM fill.** Named templates define structure + CTA; the LLM
  personalizes the opening/angle from recent evidence. Reps get a consistent shape with a
  personalized hook — not free-form every time, not rigid mail-merge.
- **Recency window: 12 months.** The cut between "current" and "stale".
- **Stale handling: soft downweight.** Recent evidence ranks above old, but a strong older signal
  still beats empty context — no account gets a content-free email. Recency is a ranking force, not
  a wall.

## Build

### 1. Capture a publish date per evidence page (foundation)

In `_fetch_or_read_cache`, derive a date with `extract_published_date(html, headers)` returning
`(iso_date | None, source)`:

- **Preferred — in-page published date** (the blog/news/changelog/press pages that actually go
  stale): `<meta property="article:published_time">`, `<meta name="date"|"pubdate"|"dc.date">`,
  JSON-LD `"datePublished"`, `<time datetime="…">`. First match wins.
- **Fallback — HTTP `Last-Modified`** header (parsed via `email.utils.parsedate_to_datetime`).
- **Undated → `None`, source `"none"`** — treated as neutral downstream, *not* stale (a stable
  "About" page has no date but isn't old news).

Store `published_at` (ISO date string) + `date_source` in the cached item and propagate them through
`_evidence_metadata` into `Evidence.metadata`. Pure stdlib (`email.utils`, `datetime`, regex) — no
new deps. Old cache files lacking the keys degrade to `None` (neutral), no migration needed.

### 2. Recency-aware selection (soft downweight)

`select_prompt_evidence(items, *, limit, snippet_chars, reference_date=None, recency_window_days=365)`
sorts by `_evidence_rank(item) + _recency_adjustment(item, reference_date, window)`:

```
published = parse(item.metadata["published_at"])      # None if absent/unparseable
if published is None:        adjustment = 0            # neutral
elif age_days <= window:     adjustment = +round(RECENCY_BONUS * (1 - age_days/window))   # +8 now → 0 at 12mo
else:                        adjustment = -round(RECENCY_PENALTY * min((age_days-window)/window, 2))  # 0 → −12 floor
```

`RECENCY_BONUS=8`, `RECENCY_PENALTY=6`. Soft by construction: a strong old page (term score ~30,
−12) still outranks a weak fresh page (term score ~5, +8) — recency reorders, never zeroes. The
adjustment lives in the **outreach-facing selector only**, not the shared `_evidence_rank`, so K2
mining/grounding ranking is untouched. `reference_date` is injected (defaults to today) to keep
tests deterministic.

### 3. Template scaffolds + LLM fill

New `icp_engine/outreach_templates.py`: a small registry of named scaffolds, each
`{name, applies_to, structure, cta}`:

- `applies_to` — persona priority and/or signal tags (e.g. exec → "exec-ai-urgency"; strong
  data signals → "data-advantage"; workflow signals → "workflow-efficiency"). `select_template`
  picks deterministically with a default fallback.
- `structure` — ordered section hints (opening hook from recent evidence → value tie-in → proof →
  CTA) the LLM must follow.
- `cta` — the concrete next step the template standardizes.

`generate_outreach` selects a template, injects its `structure`/`cta` into the prompt as the
required shape, and the LLM fills the personalized hook from the recency-filtered evidence; the
returned payload records `template`. The deterministic fallback renders the template literally,
filling merge fields from company/evidence. Subject and body stay grounded-only (no fabrication
rule unchanged).

## Out of scope (follow-ups)

- **Re-ranking the K2-retrieved `account_context` by date.** Bigger — needs `published_at` carried
  in corpus metadata (the dossier/evidence docs would propagate it) and date-filtered retrieval.
  Note in the doc; do after the scraped-evidence path proves out.
- Multi-touch sequences / A-B variants — single first-touch only for now.
- Changing what gets scraped — date capture is additive to the existing fetch.

## Verification

- `extract_published_date` unit tests: each source (meta/jsonld/time/Last-Modified/none), bad/ambiguous
  dates → `None`.
- `_recency_adjustment` / `select_prompt_evidence` tests: fresh boosts above stale; strong-old still
  beats weak-fresh (soft); undated neutral; deterministic via injected `reference_date`.
- `select_template` tests: persona/signal routing + default fallback.
- `generate_outreach` test (stub Claude client): template structure reaches the prompt; payload
  carries `template`; fallback renders the scaffold.
- Full suite stays green.

## Sequence

1. **Foundation** — date capture (`extract_published_date` + wiring) + recency selection, with tests.
2. **Template layer** — registry + `select_template` + `generate_outreach` wiring + fallback.
3. Re-measure: spot-check drafted emails on seeded accounts; confirm stale pages drop out of the hooks.
