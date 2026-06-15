# K2 vs local bake-off

- Run: `run-seeded-icp` · 424 persisted lead records
- **K2 not configured** — K2 columns read `n/a`; only the local half is measured.
- Filtering measured at top_k=500 (correctness); product default is 20 (truncates large result sets).
- Local miner evaluates 7 of 48 §14.3 filter keys offline: `ai_posture`, `company`, `domain`, `outreach_status`, `tier`, `total_score`, `vertical`.

## Filtering (precision/recall/F1 vs exact match set)

| Case | Source | Gold | Local P | Local R | Local F1 | Local ms | Coverage gap |
|---|---|---:|---:|---:|---:|---:|---|
| profile:portfolio-expansion | seeded_profile | 402 | 1.0 | 1.0 | 1.0 | 135.54 | — |
| profile:ai-gap-audit | seeded_profile | 0 | 1.0 | 1.0 | 1.0 | 127.428 | — |
| profile:workflow-moat | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 136.513 | — |
| profile:budget-access | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 127.792 | `has_contact_path` |
| profile:prospect-role-tree | seeded_profile | 424 | 1.0 | 1.0 | 1.0 | 132.68 | — |
| adv:tier-a-high-score | adversarial | 7 | 1.0 | 1.0 | 1.0 | 139.947 | — |
| adv:ab-tier-midscore | adversarial | 367 | 1.0 | 1.0 | 1.0 | 130.384 | — |
| adv:posture-level-1 | adversarial | 382 | 1.0 | 1.0 | 1.0 | 135.262 | — |
| adv:company-contains | adversarial | 6 | 1.0 | 1.0 | 1.0 | 127.311 | — |
| adv:unevaluable-contact-path | adversarial | 424 | 1.0 | 1.0 | 1.0 | 137.371 | `has_contact_path` |

## Lookalikes (precision@k / MAP@k vs independent `category` label)

| Seed | Category | Peers | Local P@k | Local R@k | Local MAP | Local ms |
|---|---|---:|---:|---:|---:|---:|
| abilis-solutions.com | mission-critical vertical market software | 96 | 0.3 | 0.0312 | 0.0726 | 125.364 |
| aep-italia.it | People Transportation | 20 | 0.0 | 0.0 | 0.0 | 142.263 |
| advantage360.com | vertical market software | 20 | 0.0 | 0.0 | 0.0 | 129.075 |
| airsquirrels.com | Education | 17 | 0.0 | 0.0 | 0.0 | 136.86 |
| bbtsoftware.ch | Financial Services | 15 | 0.0 | 0.0 | 0.0 | 130.788 |

## Grounding (known-fact coverage − contradictions)

| Account | Tier | Facts | Local coverage | Local score | Local ms |
|---|---|---:|---:|---:|---:|
| servicetitan.com | A | 6/6 | 1.0 | 1.0 | 128.897 |
| limblecmms.com | A | 6/6 | 1.0 | 1.0 | 116.747 |
| brandwatch.com | B | 6/6 | 1.0 | 1.0 | 118.508 |
| dealersocket.com | B | 6/6 | 1.0 | 1.0 | 113.956 |
| pulsarplatform.com | C | 6/6 | 1.0 | 1.0 | 124.49 |
| opengov.com | C | 6/6 | 1.0 | 1.0 | 116.305 |
| example.com | Reject | 6/6 | 1.0 | 1.0 | 113.528 |

## Summary

- Filtering: local mean F1 **1.0** over 10 cases; 2 case(s) hit the offline key-coverage gap.
- Lookalikes: local mean precision@k **0.06**, MAP@k 0.0145.
- Grounding: local mean coverage **1.0**, grounding score 1.0.

_To populate the K2 columns: `python -m icp_engine.k2_sync --apply` to provision + upload the corpus, export the returned `K2_*_CORPUS_ID` values + `K2_API_KEY`, then re-run this command._
