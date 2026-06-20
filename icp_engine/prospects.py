from __future__ import annotations

import csv
import io
import re
from typing import Any


PROSPECT_CSV_FIELDS = [
    "run_id",
    "lead_id",
    "company",
    "domain",
    "tier",
    "company_score",
    "priority_score",
    "source",
    "status",
    "name",
    "title",
    "persona",
    "persona_priority",
    "committee_role",
    "linkedin_url",
    "email",
    "email_status",
    "revealed",
    "location",
    "organization_name",
    "outreach_angle",
    "first_step",
]


def build_run_prospects(run: dict[str, Any]) -> dict[str, Any]:
    prospects: list[dict[str, Any]] = []
    for lead in run.get("leads", []):
        if isinstance(lead, dict):
            prospects.extend(build_lead_prospects(run, lead))
    prospects.sort(key=lambda item: (-int(item.get("priority_score") or 0), str(item.get("company") or ""), str(item.get("title") or "")))
    return {
        "run_id": run.get("id"),
        "prospect_count": len(prospects),
        "source_counts": _source_counts(prospects),
        "prospects": prospects,
    }


def build_lead_prospects(run: dict[str, Any], lead: dict[str, Any]) -> list[dict[str, Any]]:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
    metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
    personas = [item for item in strategy.get("personas", []) if isinstance(item, dict)]
    people_payload = metadata.get("apollo_people", {}) if isinstance(metadata.get("apollo_people"), dict) else {}
    people = [item for item in people_payload.get("people", []) if isinstance(item, dict)]

    committee_roles = _committee_role_by_title(strategy)
    if people:
        prospects = [
            _person_prospect(
                run,
                lead,
                company,
                score,
                strategy,
                personas,
                person,
                index,
            )
            for index, person in enumerate(people, start=1)
        ]
    else:
        prospects = [_persona_prospect(run, lead, company, score, strategy, persona, index) for index, persona in enumerate(personas, start=1)]
    for prospect in prospects:
        prospect["committee_role"] = _committee_role_for(prospect, committee_roles)
    return prospects


def prospects_to_csv(prospects_payload: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PROSPECT_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in prospects_payload.get("prospects", []):
        if not isinstance(item, dict):
            continue
        writer.writerow({field: _csv_value(item.get(field)) for field in PROSPECT_CSV_FIELDS})
    return output.getvalue()


def _person_prospect(
    run: dict[str, Any],
    lead: dict[str, Any],
    company: dict[str, Any],
    score: dict[str, Any],
    strategy: dict[str, Any],
    personas: list[dict[str, Any]],
    person: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    title = _string(person.get("title"))
    persona = _match_persona(title, personas)
    org = person.get("organization") if isinstance(person.get("organization"), dict) else {}
    location = ", ".join(part for part in [_string(person.get("city")), _string(person.get("state")), _string(person.get("country"))] if part)
    return {
        **_base_prospect(run, lead, company, score, strategy),
        "id": _prospect_id(run, company, person.get("id") or person.get("linkedin_url") or title or index),
        "source": "apollo",
        "status": "person_found",
        "name": _string(person.get("name")),
        "title": title,
        "persona": _string(persona.get("title")) or title,
        "persona_priority": _string(persona.get("priority")) or "unknown",
        "linkedin_url": _string(person.get("linkedin_url")),
        "email": _string(person.get("email")),
        "email_status": _string(person.get("email_status")),
        "revealed": bool(person.get("email")),
        "location": location,
        "organization_name": _string(org.get("name")) or _string(company.get("company")),
        "priority_score": _priority_score(score, persona, source="apollo"),
    }


def _persona_prospect(
    run: dict[str, Any],
    lead: dict[str, Any],
    company: dict[str, Any],
    score: dict[str, Any],
    strategy: dict[str, Any],
    persona: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    title = _string(persona.get("title"))
    return {
        **_base_prospect(run, lead, company, score, strategy),
        "id": _prospect_id(run, company, title or index),
        "source": "strategy",
        "status": "persona_target",
        "name": "",
        "title": title,
        "persona": title,
        "persona_priority": _string(persona.get("priority")) or "unknown",
        "linkedin_url": "",
        "email": "",
        "email_status": "",
        "revealed": False,
        "location": "",
        "organization_name": _string(company.get("company")),
        "priority_score": _priority_score(score, persona, source="strategy"),
    }


def _base_prospect(
    run: dict[str, Any],
    lead: dict[str, Any],
    company: dict[str, Any],
    score: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "lead_id": lead.get("id"),
        "company": _string(company.get("company")),
        "domain": _string(company.get("domain")),
        "tier": _string(score.get("tier")),
        "company_score": int(score.get("total_score") or 0),
        "outreach_angle": _string(strategy.get("outreach_angle")),
        "first_step": _string(strategy.get("first_step")),
        "offer": _string(strategy.get("offer")),
    }


def _committee_role_by_title(strategy: dict[str, Any]) -> dict[str, str]:
    committee = strategy.get("committee", []) if isinstance(strategy.get("committee"), list) else []
    mapping: dict[str, str] = {}
    for role in committee:
        if not isinstance(role, dict):
            continue
        title = _string(role.get("title")).lower()
        role_name = _string(role.get("role"))
        if title and role_name and title not in mapping:
            mapping[title] = role_name
    return mapping


def _committee_role_for(prospect: dict[str, Any], committee_roles: dict[str, str]) -> str:
    for key in (prospect.get("persona"), prospect.get("title")):
        role = committee_roles.get(_string(key).lower())
        if role:
            return role
    return ""


def _match_persona(title: str, personas: list[dict[str, Any]]) -> dict[str, Any]:
    title_terms = _terms(title)
    if not title_terms:
        return personas[0] if personas else {}
    best: tuple[int, dict[str, Any]] = (0, {})
    for persona in personas:
        haystack = " ".join(
            [
                _string(persona.get("title")),
                " ".join(_string(item) for item in persona.get("apollo_titles", []) if item),
            ]
        )
        overlap = len(title_terms & _terms(haystack))
        if overlap > best[0]:
            best = (overlap, persona)
    return best[1] or (personas[0] if personas else {})


def _priority_score(score: dict[str, Any], persona: dict[str, Any], *, source: str) -> int:
    tier_weight = {"A": 60, "B": 45, "C": 25, "Reject": 0}.get(_string(score.get("tier")), 15)
    company_score = min(100, max(0, int(score.get("total_score") or 0))) // 3
    persona_weight = 18 if persona.get("priority") == "primary" else 8
    source_weight = 10 if source == "apollo" else 0
    return tier_weight + company_score + persona_weight + source_weight


def _source_counts(prospects: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in prospects:
        source = _string(item.get("source")) or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def _prospect_id(run: dict[str, Any], company: dict[str, Any], value: object) -> str:
    parts = [str(run.get("id") or "run"), _string(company.get("domain")) or _string(company.get("company")), str(value)]
    return "prospect-" + "-".join(_slug(part) for part in parts if part)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 1 and term not in {"of", "and", "the"}}


def _string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _csv_value(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(_string(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}={_string(item)}" for key, item in sorted(value.items()))
    return _string(value)
