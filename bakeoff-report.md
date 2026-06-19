# K2 vs local bake-off

- Run: `run-seeded-icp` · 424 persisted lead records
- K2 columns are live.
- Filtering measured at top_k=500 (correctness); product default is 20 (truncates large result sets).
- Local miner evaluates 7 of 48 §14.3 filter keys offline: `ai_posture`, `company`, `domain`, `outreach_status`, `tier`, `total_score`, `vertical`.

## Filtering (precision/recall/F1 vs exact match set)

| Case | Source | Gold | Local F1 | K2 F1 | Local ms | K2 ms | Coverage gap |
|---|---|---:|---:|---:|---:|---:|---|
| profile:portfolio-expansion | seeded_profile | 402 | 1.0 | 0.0485 | 129.284 | 897.072 | — |
| profile:ai-gap-audit | seeded_profile | 382 | 1.0 | 0.0459 | 162.03 | 903.101 | — |
| profile:workflow-moat | seeded_profile | 424 | 1.0 | 1.0 | 170.334 | 829.42 | — |
| profile:budget-access | seeded_profile | 424 | 1.0 | 0.0 | 134.533 | 745.597 | `has_contact_path` |
| profile:prospect-role-tree | seeded_profile | 424 | 1.0 | 1.0 | 171.849 | 672.156 | — |
| adv:tier-a-high-score | adversarial | 7 | 1.0 | 1.0 | 132.946 | 619.986 | — |
| adv:ab-tier-midscore | adversarial | 367 | 1.0 | 1.0 | 128.162 | 591.175 | — |
| adv:posture-level-1 | adversarial | 382 | 1.0 | 1.0 | 127.006 | 582.933 | — |
| adv:company-contains | adversarial | 6 | 1.0 | 1.0 | 126.368 | 671.292 | — |
| adv:unevaluable-contact-path | adversarial | 424 | 1.0 | 1.0 | 127.973 | 635.111 | `has_contact_path` |

## Lookalikes (precision@k / MAP@k vs independent `category` label)

| Seed | Category | Peers | Local P@k | K2 P@k | Local MAP | K2 MAP |
|---|---|---:|---:|---:|---:|---:|
| abilis-solutions.com | mission-critical vertical market software | 96 | 1.0 | 1.0 | 1.0 | 1.0 |
| aep-italia.it | People Transportation | 20 | 0.6 | 0.0 | 0.3564 | 0.0 |
| advantage360.com | vertical market software | 20 | 1.0 | 1.0 | 1.0 | 1.0 |
| airsquirrels.com | Education | 17 | 1.0 | 0.7778 | 1.0 | 0.5565 |
| bbtsoftware.ch | Financial Services | 15 | 0.0 | 0.0 | 0.0 | 0.0 |

## Grounding (known-fact coverage − contradictions)

| Account | Tier | Local cov | K2 cov | Local score | K2 score |
|---|---|---:|---:|---:|---:|
| servicetitan.com | A | 1.0 | 1.0 | 1.0 | 1.0 |
| limblecmms.com | A | 1.0 | 0.8333 | 1.0 | 0.8333 |
| brandwatch.com | B | 1.0 | 1.0 | 1.0 | 1.0 |
| dealersocket.com | B | 1.0 | 1.0 | 1.0 | 1.0 |
| pulsarplatform.com | C | 1.0 | 1.0 | 1.0 | 1.0 |
| opengov.com | C | 1.0 | 1.0 | 1.0 | 1.0 |
| example.com | Reject | 0.8333 | 0.8333 | 0.8333 | 0.8333 |

## Summary

- Filtering: local mean F1 **1.0** over 10 cases; 2 case(s) hit the offline key-coverage gap.
- Lookalikes: local mean precision@k **0.72**, MAP@k 0.6713.
- Grounding: local mean coverage **0.9762**, grounding score 0.9762.
