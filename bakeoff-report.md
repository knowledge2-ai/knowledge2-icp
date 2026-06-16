# K2 vs local bake-off

- Run: `run-seeded-icp` · 424 persisted lead records
- K2 columns are live.
- Filtering requested at top_k=500: the local mine is exhaustive (returns every WHERE match), but K2 is a top-k semantic retriever the API hard-caps at 100 — so on gold sets larger than 100, K2 recall is bounded by that cap, not the metadata filter.
- Local miner evaluates 7 of 48 §14.3 filter keys offline: `ai_posture`, `company`, `domain`, `outreach_status`, `tier`, `total_score`, `vertical`.

## Filtering (precision/recall/F1 vs exact match set)

| Case | Source | Gold | Local F1 | K2 F1 | Local ms | K2 ms | Coverage gap |
|---|---|---:|---:|---:|---:|---:|---|
| profile:portfolio-expansion | seeded_profile | 402 | 1.0 | 0.2212 | 139.17 | 1389.788 | — |
| profile:ai-gap-audit | seeded_profile | 382 | 1.0 | 0.2135 | 185.053 | 1227.556 | — |
| profile:workflow-moat | seeded_profile | 424 | 1.0 | 1.0 | 168.899 | 633.956 | — |
| profile:budget-access | seeded_profile | 424 | 1.0 | 0.0 | 125.601 | 694.082 | `has_contact_path` |
| profile:prospect-role-tree | seeded_profile | 424 | 1.0 | 1.0 | 186.278 | 720.844 | — |
| adv:tier-a-high-score | adversarial | 7 | 1.0 | 1.0 | 133.143 | 544.427 | — |
| adv:ab-tier-midscore | adversarial | 367 | 1.0 | 1.0 | 128.459 | 595.103 | — |
| adv:posture-level-1 | adversarial | 382 | 1.0 | 1.0 | 133.825 | 550.312 | — |
| adv:company-contains | adversarial | 6 | 1.0 | 1.0 | 147.729 | 581.734 | — |
| adv:unevaluable-contact-path | adversarial | 424 | 1.0 | 1.0 | 154.987 | 656.532 | `has_contact_path` |

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
| limblecmms.com | A | 1.0 | 1.0 | 1.0 | 1.0 |
| brandwatch.com | B | 1.0 | 1.0 | 1.0 | 1.0 |
| dealersocket.com | B | 1.0 | 1.0 | 1.0 | 1.0 |
| pulsarplatform.com | C | 1.0 | 1.0 | 1.0 | 1.0 |
| opengov.com | C | 1.0 | 1.0 | 1.0 | 1.0 |
| example.com | Reject | 0.8333 | 0.8333 | 0.8333 | 0.8333 |

## Summary

- Filtering: local mean F1 **1.0** over 10 cases; 2 case(s) hit the offline key-coverage gap.
- Lookalikes: local mean precision@k **0.72**, MAP@k 0.6713.
- Grounding: local mean coverage **0.9762**, grounding score 0.9762.
