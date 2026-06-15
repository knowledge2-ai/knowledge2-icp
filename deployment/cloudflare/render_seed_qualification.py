#!/usr/bin/env python3
"""Embed canonical per-account qualification into the Worker's seed asset.

The Cloudflare Worker (`worker.js`) is a separate JS reimplementation that reads
each account's pre-computed `qualification` block from
`icp_engine/web_assets/seed-companies.json`. When that block is absent it falls
back to hardcoded JS defaults (flat `ai_gap=30`, a constant `total_score`) that
diverge from the Python scoring pipeline — so accounts without an embedded block
render the old, inconsistent demo scores at the edge.

This script rebuilds the embedded `qualification` for *every* account from the
canonical `seed_defaults.seeded_run()` output, so the edge serves exactly what
the Python server computes (total == sum of components, graded `ai_gap`, real
buying-committee-grade gates). Run it whenever the scoring pipeline or the
account universe changes:

    python3 deployment/cloudflare/render_seed_qualification.py

It is idempotent and preserves the file's formatting (2-space indent, sorted
keys), so a no-op run produces an empty diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from icp_engine.seed_defaults import seeded_run  # noqa: E402

SEED_ASSET = _REPO_ROOT / "icp_engine" / "web_assets" / "seed-companies.json"

# The exact key set worker.js reads from each account's `qualification` block.
_QUALIFICATION_KEYS = (
    "ai_gap_score",
    "ai_posture",
    "budget_access_score",
    "classification_source",
    "commercial_urgency_score",
    "data_workflow_score",
    "feasibility_score",
    "hard_gate_failed",
    "hard_gate_unknown",
    "next_action",
    "tier",
    "total_score",
    "warnings",
)


def _norm(domain: str | None) -> str:
    return (domain or "").strip().lower()


def _project(score: dict) -> dict:
    """Project a canonical lead `score` dict into the worker's qualification shape."""
    classification = score["classification"]
    projected = {
        "ai_gap_score": score["ai_gap_score"],
        "ai_posture": classification["ai_posture"],
        "budget_access_score": score["budget_access_score"],
        "classification_source": classification.get("source", "rules"),
        "commercial_urgency_score": score["commercial_urgency_score"],
        "data_workflow_score": score["data_workflow_score"],
        "feasibility_score": score["feasibility_score"],
        "hard_gate_failed": score["hard_gate_failed"],
        "hard_gate_unknown": score["hard_gate_unknown"],
        "next_action": score["next_action"],
        "tier": score["tier"],
        "total_score": score["total_score"],
        "warnings": list(score.get("warnings", [])),
    }
    assert set(projected) == set(_QUALIFICATION_KEYS), "qualification shape drifted from worker.js contract"
    return projected


def main() -> int:
    data = json.loads(SEED_ASSET.read_text(encoding="utf-8"))
    accounts = data.get("account_universe", [])

    by_domain = {
        _norm(lead["score"]["company"].get("domain")): _project(lead["score"])
        for lead in seeded_run()["leads"]
    }

    missing = []
    for account in accounts:
        qualification = by_domain.get(_norm(account.get("domain")))
        if qualification is None:
            missing.append(account.get("domain"))
            continue
        account["qualification"] = qualification

    if missing:
        raise SystemExit(f"No canonical score for {len(missing)} account domain(s): {missing[:10]}")

    SEED_ASSET.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Self-check: every embedded block is internally consistent.
    violations = 0
    for account in accounts:
        q = account["qualification"]
        components = (
            q["ai_gap_score"]
            + q["data_workflow_score"]
            + q["commercial_urgency_score"]
            + q["budget_access_score"]
            + q["feasibility_score"]
        )
        if components != q["total_score"]:
            violations += 1
    print(f"Embedded qualification for {len(accounts)} accounts; total!=sum violations: {violations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
