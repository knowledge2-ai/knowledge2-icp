# Rich per-account dossiers for K2 grounding

**Status:** design (task #43) · **Date:** 2026-06-19 · **Author:** Anton + Claude

## Why

The bake-off ([`bakeoff-report.md`](../../bakeoff-report.md)) found grounding **tied** — K2 0.976
= local 0.976 — across all 7 sampled accounts. A tie means K2 isn't losing; it's **underfed**.
The corpus is ~3,326 documents averaging 100–600 chars: flattened structured records, not
account briefs. The grounding answer can only be as good as the most substantive document it can
retrieve per account, and today that document is a label dump.

This matters because the chosen product design's **defensible wedge is the corpus-grounded research
layer** (see `2026-06-17-oss-gtm-go-no-go.md`) — ICP classification + outreach personalization
grounded in a private corpus, the one thing a bare LLM wrapper can't clone. If the grounding only
has 300-char label lists to stand on, the moat is thin. Rich dossiers are the lever that makes
"grounded" mean something. This is the single highest-alignment K2 investment.

## Current shape (what exists today)

`K2Backend.build_documents` (`icp_engine/k2_backend.py:44`) emits, per account:

1. **One account-summary doc** (`_account_summary_document`, `:482`) → candidate corpus. Its `text`
   is a ~10-line flattened key:value blob:
   ```
   Company: Mojio (moj.io)
   Tier: A score 82
   Criteria: Tier A >= 75, Tier B >= 60, employee range 25-2000
   Qualifier: claude via llm
   AI narrative: …
   Strategy: <outreach_angle>
   Offer: <offer>
   Personas: VP Eng, Head of Data
   Signals: telematics, workflow-data, …
   Source counts: {...}
   Public profiles and resources: <urls>
   ```
   Rich **metadata** (40+ keys: tier, posture, signal_tags, criteria_*, github/linkedin/docs/pricing
   URLs, ai_narrative), but the **text** a generator retrieves is a label list.

2. **N evidence docs** (`:56`) → evidence corpus. `text` = raw scraped per-page content (the real
   substance), but each is a **disconnected single-page snippet** with no account-level synthesis.

3. Prospect docs → prospect corpus.

**Grounding** (`answer_question`, `:186`) reads the **research corpus**
(`_research_corpus_id` → `run.k2.corpus_id` or `K2_RESEARCH_CORPUS_ID`). So the question of *where a
dossier lands* is the research corpus — see Wiring below.

The key insight: **the substance for a real dossier already exists** — raw evidence text, the AI
narrative, the strategy rationale, signals, criteria fit. It's just never composed into one
coherent account-level document.

## The dossier document

One self-contained per-account markdown document (~1.5–4 KB, vs ~400 chars today) composed from
data already in the run — **no new fetching**. Proposed structure:

```markdown
# {Company} — {domain}

## Classification
{Tier} (score {total_score}). AI posture: {ai_posture}. Vertical: {vertical}.
{ai_narrative — the LLM qualification reasoning, full prose, not truncated}

## Why they fit the ICP
Criteria: Tier A ≥ {…}, employee range {…}. Matched signals: {signal_tags as a sentence}.
{2–4 sentence synthesis of how the signals map to the criteria}

## Evidence
{For each top evidence page: a titled 1–2 sentence excerpt from item.text +
 source_url — the actual scraped content, woven in, not dumped}

## Outreach posture
Angle: {outreach_angle}. Offer: {offer}.
Personas: {persona.title — why each persona matters, from strategy}

## Public footprint
GitHub / docs / pricing / LinkedIn: {source_refs, as context not just URLs}
```

This is prose a generator can quote and reason over, surfacing the known facts the bake-off checks
(vertical, ai_posture, tier, top signal) **in context** rather than as isolated key:values.

### Generation

- New builder `_account_dossier_document(run, lead, score, company, strategy, lead_metadata)`
  alongside `_account_summary_document`, composing the sections above from existing fields:
  `score`, `score.classification`, `lead.metadata` (signal_tags, criteria_profile, qualification,
  source_refs), `lead.evidence[].text/title/url`, `strategy` (outreach_angle, offer, personas).
- Deterministic string assembly — **no LLM call** to build it (the `ai_narrative` is already
  generated upstream during qualification; we're reformatting, not re-inferring). Keeps the sync
  offline-reproducible and the bake-off deterministic.
- Carry the same rich metadata block as the account-summary (so metadata filtering is unaffected),
  plus `evidence_id: "account-dossier"` to distinguish it.
- Evidence excerpting: take the top-K evidence pages by existing signal weighting; truncate each to
  ~280 chars at a sentence boundary to keep the dossier focused, not a raw-text dump.

## Wiring (RESOLVED by live probe — 2026-06-18)

A live probe of the dev workspace (`Knowledge2 ICP GTM Dev`) inspected the corpus-id alias map and
each corpus's contents. Finding:

- **The research corpus IS the evidence corpus** — `K2_RESEARCH_CORPUS_ID` and
  `K2_EVIDENCE_CORPUS_ID` resolve to the same corpus id (alias group `evidence+research`, 1,776
  chunks of per-page evidence ~400 chars). So `answer_question` → `_research_corpus_id` grounds on
  the **evidence corpus**.
- The sync's `apply_uploads` loop routes via `build_seeded_workspace_documents` (`:239`), where the
  `evidence_docs` bucket receives **every** document (line 250 is unconditional). So the evidence/
  research corpus already holds account-summary label dumps + per-page snippets — grounding just
  retrieves whichever chunk ranks highest, today a ~400-char snippet or a label list.
- K2 holds large docs fine: the criteria corpus carries 5,898–6,775-char docs (it chunks on
  ingest). A ~2–4 KB dossier chunks into a few coherent sections, each carrying account-level
  framing — strictly better grounding fodder than disconnected page snippets.

**Decision: route the dossier into the evidence corpus** (the grounding corpus) — option (A)
collapses to "emit the dossier and let the existing unconditional `evidence_docs.append` carry it."
No new corpus, no `K2_RESEARCH_CORPUS_ID` change, no provisioning. Exclude it from the `source`
bucket (same as account-summary) so it doesn't dilute the source corpus, and keep it out of
`candidate` so the mining/filtering corpus keeps one account doc, not two.

## Measuring lift

The bake-off already scores grounding deterministically (`bakeoff.py:score_grounding` — fraction of
known facts surfaced in the answer text, minus contradictions). Plan:

1. Baseline is recorded: K2 grounding 0.976 (tied with local).
2. Build dossiers, sync to the grounding corpus, re-run `python -m icp_engine.bakeoff`.
3. **Success = K2 grounding pulls measurably ahead of local** (e.g. ≥ 0.99 and/or fewer
   contradictions), since local has no equivalent rich-document path. A *persistent* tie after rich
   dossiers would be evidence the grounding ceiling is the question set, not the corpus — a
   different conclusion worth knowing.
4. Optionally extend the grounding fact set (the current 6 facts/account are easy to surface even
   from labels; richer facts — specific evidence claims — would better discriminate dossier lift).

## Scope / risks

- **In scope:** the dossier builder, its wiring into the sync/corpus model, the bake-off re-measure.
- **Out of scope:** changing what gets *scraped* (evidence collection is unchanged); the dossier
  only recomposes existing data. No new provider calls.
- **Risk — fact set too easy:** if 6 facts/account saturate from labels alone, lift won't show even
  if dossiers are better for real outreach. Mitigation: extend the grounding eval with
  evidence-derived facts (step 4) so the metric can actually move.
- **Risk — corpus bloat:** dossiers are ~4–10× larger than summaries, but it's one doc/account
  (~430 docs), trivial vs the 3,326 evidence snippets. No cost concern.
- **Cost:** generation is deterministic/offline; sync is the existing upload path. No new spend.

## Sequence

1. ~~Confirm research-corpus population~~ — DONE: research corpus == evidence corpus (see Wiring).
2. `_account_dossier_document` builder + unit test (deterministic text from a seeded lead).
3. Wire into `build_documents` (emit per lead) + route into the `evidence` bucket in
   `build_seeded_workspace_documents`, excluded from `source`/`candidate`.
4. Re-run bake-off grounding; compare to the 0.976 baseline; extend fact set if saturated.
5. Decision: does rich grounding pull K2 ahead → the "keep K2, feed it rich docs" call lands.
