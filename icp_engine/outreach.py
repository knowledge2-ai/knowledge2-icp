from __future__ import annotations

import csv
import io
from typing import Any

from .prospects import build_lead_prospects


OUTREACH_STATUSES = ("Draft", "Approved", "Rejected", "Exported")
OUTREACH_CSV_FIELDS = [
    "id",
    "run_id",
    "lead_id",
    "prospect_id",
    "company",
    "domain",
    "prospect_name",
    "title",
    "persona",
    "source",
    "status",
    "subject",
    "body",
    "cta",
    "evidence_titles",
    "evidence_urls",
    "outreach_angle",
    "first_step",
    "approval_note",
    "updated_at",
]


def build_lead_outreach_drafts(
    run: dict[str, Any],
    lead: dict[str, Any],
    statuses: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    statuses = statuses or {}
    evidence = [item for item in lead.get("evidence", []) if isinstance(item, dict)]
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
    prospects = build_lead_prospects(run, lead)
    return [
        _draft_for_prospect(run, lead, company, strategy, evidence, prospect, statuses.get(str(prospect.get("id") or "")))
        for prospect in prospects
    ]


def summarize_outreach_drafts(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in OUTREACH_STATUSES}
    for draft in drafts:
        status = normalize_outreach_status(str(draft.get("status") or "Draft"))
        counts[status] += 1
    return {
        "total": len(drafts),
        "status_counts": counts,
        "ready_count": counts["Approved"] + counts["Exported"],
    }


def outreach_drafts_to_csv(drafts: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTREACH_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for draft in drafts:
        writer.writerow({field: _csv_value(draft.get(field)) for field in OUTREACH_CSV_FIELDS})
    return output.getvalue()


def normalize_outreach_status(status: str) -> str:
    normalized = " ".join(status.strip().split()).title() or "Draft"
    if normalized not in OUTREACH_STATUSES:
        raise ValueError(f"Invalid outreach status: {status}. Expected one of {', '.join(OUTREACH_STATUSES)}.")
    return normalized


def _draft_for_prospect(
    run: dict[str, Any],
    lead: dict[str, Any],
    company: dict[str, Any],
    strategy: dict[str, Any],
    evidence: list[dict[str, Any]],
    prospect: dict[str, Any],
    status_record: dict[str, Any] | None,
) -> dict[str, Any]:
    prospect_id = str(prospect.get("id") or "")
    evidence_refs = _evidence_refs(evidence)
    contact_label = str(prospect.get("name") or prospect.get("persona") or prospect.get("title") or "there")
    first_name = contact_label.split()[0] if contact_label and " " in contact_label else contact_label
    company_name = str(company.get("company") or prospect.get("company") or "your team")
    angle = str(strategy.get("outreach_angle") or prospect.get("outreach_angle") or "Your workflow data may support a sharper AI product narrative.")
    offer = str(strategy.get("offer") or "Propose a 2-week AI opportunity map grounded in existing product data and evidence.")
    first_step = str(strategy.get("first_step") or prospect.get("first_step") or "Share a short account-specific brief.")
    evidence_line = _evidence_line(evidence_refs)
    subject = f"{company_name} AI workflow opportunity map"
    body = "\n\n".join(
        [
            f"Hi {first_name or 'there'},",
            f"I was reviewing {company_name} and noticed {evidence_line}.",
            angle,
            f"A practical next step would be: {offer}",
            f"Would it be useful to compare this against one workflow where {company_name} already has proprietary operational data?",
        ]
    )
    cta = first_step
    status_record = status_record if isinstance(status_record, dict) else {}
    return {
        "id": f"draft-{prospect_id}",
        "run_id": run.get("id"),
        "lead_id": lead.get("id"),
        "prospect_id": prospect_id,
        "company": company_name,
        "domain": str(company.get("domain") or prospect.get("domain") or ""),
        "prospect_name": str(prospect.get("name") or ""),
        "title": str(prospect.get("title") or ""),
        "persona": str(prospect.get("persona") or prospect.get("title") or ""),
        "source": str(prospect.get("source") or ""),
        "status": normalize_outreach_status(str(status_record.get("status") or "Draft")),
        "subject": subject,
        "body": body,
        "cta": cta,
        "evidence": evidence_refs,
        "evidence_titles": [item["title"] for item in evidence_refs],
        "evidence_urls": [item["url"] for item in evidence_refs],
        "outreach_angle": angle,
        "first_step": first_step,
        "approval_note": str(status_record.get("note") or ""),
        "updated_at": str(status_record.get("updated_at") or ""),
    }


def _evidence_refs(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs = []
    for item in evidence[:2]:
        refs.append(
            {
                "title": str(item.get("title") or item.get("url") or "Evidence"),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("text") or "")[:220],
            }
        )
    return refs


def _evidence_line(refs: list[dict[str, str]]) -> str:
    if not refs:
        return "public evidence that suggests an operational workflow/data asset"
    first = refs[0]
    title = first.get("title") or "public evidence"
    snippet = first.get("snippet") or ""
    if snippet:
        return f"{title}: {snippet}"
    return title


def _csv_value(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}={item}" for key, item in sorted(value.items()))
    return str(value or "")
