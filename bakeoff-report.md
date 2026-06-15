# K2 vs local bake-off

- Run: `run-seeded-icp` · 424 persisted lead records
- **K2 not configured** — K2 columns read `n/a`; only the local half is measured.
- Filtering measured at top_k=500 (correctness); product default is 20 (truncates large result sets).
- Local miner evaluates 7 of 48 §14.3 filter keys offline: `ai_posture`, `company`, `domain`, `outreach_status`, `tier`, `total_score`, `vertical`.

## Filtering (precision/recall/F1 vs exact match set)

| Case | Source | Gold | Local P | Local R | Local F1 | Local ms | Coverage gap |
|---|---|---:|---:|---:|---:|---:|---|
| profile:portfolio-expansion | seeded_profile | 402 | 1.0 | 1.0 | 1.0 | 133.217 | — |
| profile:ai-gap-audit | seeded_profile | 382 | 1.0 | 1.0 | 1.0 | 129.665 | — |
| profile:workflow-moat | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 130.317 | — |
| profile:budget-access | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 126.297 | `has_contact_path` |
| profile:prospect-role-tree | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 132.893 | — |
| adv:tier-a-high-score | adversarial | 7 | 1.0 | 1.0 | 1.0 | 133.482 | — |
| adv:ab-tier-midscore | adversarial | 367 | 1.0 | 1.0 | 1.0 | 124.54 | — |
| adv:posture-level-1 | adversarial | 382 | 1.0 | 1.0 | 1.0 | 131.265 | — |
| adv:company-contains | adversarial | 6 | 1.0 | 1.0 | 1.0 | 125.442 | — |
| adv:unevaluable-contact-path | adversarial | 424 | 1.0 | 1.0 | 1.0 | 131.486 | `has_contact_path` |

## Lookalikes (precision@k / MAP@k vs independent `category` label)

| Seed | Category | Peers | Local P@k | Local R@k | Local MAP | Local ms |
|---|---|---:|---:|---:|---:|---:|
| abilis-solutions.com | mission-critical vertical market software | 96 | 1.0 | 0.1042 | 1.0 | 122.213 |
| aep-italia.it | People Transportation | 20 | 0.6 | 0.3 | 0.3564 | 132.347 |
| advantage360.com | vertical market software | 20 | 1.0 | 0.5 | 1.0 | 126.945 |
| airsquirrels.com | Education | 17 | 1.0 | 0.5882 | 1.0 | 130.035 |
| bbtsoftware.ch | Financial Services | 15 | 0.0 | 0.0 | 0.0 | 123.581 |

## Grounding (known-fact coverage − contradictions)

| Account | Tier | Facts | Local coverage | Local score | Local ms |
|---|---|---:|---:|---:|---:|
| servicetitan.com | A | 6/6 | 1.0 | 1.0 | 118.484 |
| limblecmms.com | A | 6/6 | 1.0 | 1.0 | 112.745 |
| brandwatch.com | B | 6/6 | 1.0 | 1.0 | 110.447 |
| dealersocket.com | B | 6/6 | 1.0 | 1.0 | 108.507 |
| pulsarplatform.com | C | 6/6 | 1.0 | 1.0 | 117.016 |
| opengov.com | C | 6/6 | 1.0 | 1.0 | 111.831 |
| example.com | Reject | 6/6 | 1.0 | 1.0 | 111.168 |

## Summary

- Filtering: local mean F1 **1.0** over 10 cases; 2 case(s) hit the offline key-coverage gap.
- Lookalikes: local mean precision@k **0.72**, MAP@k 0.6713.
- Grounding: local mean coverage **1.0**, grounding score 1.0.

_To populate the K2 columns: `python -m icp_engine.k2_sync --apply` to provision + upload the corpus, export the returned `K2_*_CORPUS_ID` values + `K2_API_KEY`, then re-run this command._
