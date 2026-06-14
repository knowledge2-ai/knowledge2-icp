from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Callable

from .apollo import ApolloClient
from .app_store import AppStore, now_iso
from .claude import ClaudeUnavailable, classify_with_claude
from .criteria import build_criteria_profile
from .discovery import DiscoveryCandidate, discover_companies, discover_companies_from_url, parse_seed_companies
from .enrichment import fetch_company_evidence, normalize_domain
from .github import search_github_metadata
from .k2_backend import K2Backend
from .metadata import lead_metadata_summary, refs_from_candidate
from .models import Classification, CompanyInput, Evidence
from .scoring import score_company
from .serialization import evidence_to_dict, score_to_dict
from .strategy import build_strategy
from .text import compact_snippet, normalize_whitespace


EvidenceFetcher = Callable[[CompanyInput, Path], tuple[list[Evidence], list[str]]]
Classifier = Callable[[CompanyInput, list[Evidence], str], Classification]


class ResearchPipeline:
    def __init__(
        self,
        store: AppStore,
        *,
        evidence_fetcher: EvidenceFetcher | None = None,
        search_fetcher: Callable[[str], str] | None = None,
        apollo_client: ApolloClient | None = None,
        k2_backend: K2Backend | None = None,
        classifier: Classifier | None = None,
    ) -> None:
        self.store = store
        self.evidence_fetcher = evidence_fetcher
        self.search_fetcher = search_fetcher
        self.apollo = apollo_client or ApolloClient.from_env()
        self.k2 = k2_backend or K2Backend()
        self.classifier = classifier

    def discover(self, query: str, *, seed_text: str = "", max_companies: int = 10) -> tuple[list[DiscoveryCandidate], list[str]]:
        candidates = parse_seed_companies(seed_text)
        warnings: list[str] = []
        if query.strip():
            discovered, search_warnings = discover_companies(query, max_results=max_companies, fetcher=self.search_fetcher)
            candidates.extend(discovered)
            warnings.extend(_search_warnings_for_candidates(search_warnings, bool(candidates)))
        return _dedupe_candidates(candidates)[:max_companies], warnings

    def scan_source(self, source: dict[str, object], *, max_companies: int = 25) -> tuple[list[DiscoveryCandidate], list[str]]:
        source_type = str(source.get("type") or "serp_query")
        value = str(source.get("value") or "")
        if source_type == "portfolio_url":
            candidates, warnings = discover_companies_from_url(value, max_results=max_companies, fetcher=self.search_fetcher)
        elif source_type in {"manual_seed", "csv_upload"}:
            candidates = parse_seed_companies(value)
            source_label = "CSV source text" if source_type == "csv_upload" else "manual seed text"
            warnings = [] if candidates else [f"No company domains were discovered from {source_label}."]
        else:
            candidates, warnings = self.discover(value, max_companies=max_companies)
            if source_type == "apollo_query" and not self.apollo.configured:
                warnings = ["APOLLO_API_KEY is not configured; used search-provider discovery instead.", *warnings]
        return _dedupe_candidates(candidates)[:max_companies], warnings

    def create_run(
        self,
        *,
        query: str,
        seed_text: str = "",
        candidate_payloads: list[object] | None = None,
        max_companies: int = 8,
        fetch: bool = True,
        max_pages: int = 8,
        include_github: bool = True,
        use_apollo: bool = False,
    ) -> dict[str, object]:
        criteria = self.store.load_criteria()
        criteria_markdown = str(criteria.get("markdown", ""))
        criteria_profile = build_criteria_profile(
            criteria_markdown,
            source=str(criteria.get("source", "")),
            criteria_hash=str(criteria.get("hash", "")),
        )
        qualifier = _resolve_qualifier(self.store.load_settings())
        qualifier_warned = False
        qualified_count = 0
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        if candidate_payloads is None:
            candidates, warnings = self.discover(query, seed_text=seed_text, max_companies=max_companies)
        else:
            candidates = _dedupe_candidates(_candidates_from_payload(candidate_payloads))[:max_companies]
            warnings = []
            if not candidates:
                warnings.append("No selected candidates were provided for this run.")
        cache_dir = self.store.state_dir / "cache" / run_id
        leads = []

        for candidate in candidates:
            company = CompanyInput(
                company=candidate.company,
                domain=candidate.domain,
                notes=_candidate_notes(candidate),
            )
            evidence, fetch_warnings = self._collect_evidence(company, candidate, cache_dir, fetch=fetch, max_pages=max_pages)
            metadata = self._collect_metadata(company, candidate, include_github=include_github, use_apollo=use_apollo)
            metadata.update(lead_metadata_summary(company, evidence, refs_from_candidate(candidate)))
            metadata["criteria_profile"] = criteria_profile.to_dict()
            model_classification, qualify_warning = self._qualify(company, evidence, criteria_markdown, qualifier)
            if model_classification is not None:
                qualified_count += 1
            if qualify_warning and not qualifier_warned:
                warnings.append(qualify_warning)
                qualifier_warned = True
            score = score_company(
                company,
                evidence,
                model_classification=model_classification,
                fetch_warnings=fetch_warnings,
                criteria_profile=criteria_profile,
            )
            metadata["qualification"] = _qualification_metadata(qualifier, score)
            strategy = build_strategy(score, evidence, metadata)
            if use_apollo and self.apollo.configured:
                metadata["apollo_people"] = self.apollo.search_people(
                    domain=company.domain,
                    titles=strategy.get("apollo_titles", []),
                )

            leads.append(
                {
                    "id": f"{run_id}:{company.domain}",
                    "candidate": {
                        "source_url": candidate.source_url,
                        "source_title": candidate.source_title,
                        "github_urls": candidate.github_urls,
                        "linkedin_urls": candidate.linkedin_urls,
                        "other_urls": candidate.other_urls,
                    },
                    "score": score_to_dict(score),
                    "strategy": strategy,
                    "evidence": [evidence_to_dict(item) for item in evidence],
                    "metadata": metadata,
                }
            )

        leads.sort(key=lambda item: item["score"]["total_score"], reverse=True)
        run = {
            "id": run_id,
            "query": query,
            "created_at": now_iso(),
            "status": "completed",
            "qualifier": qualifier,
            "criteria": {
                "hash": criteria["hash"],
                "source": criteria["source"],
                "updated_at": criteria.get("updated_at"),
                "profile": criteria_profile.to_dict(),
                "qualifier": qualifier,
            },
            "warnings": warnings,
            "leads": leads,
        }
        if qualified_count:
            self.store.record_provider_usage(
                "qualify",
                status="allowed",
                amount=qualified_count,
                details={"qualifier": qualifier, "criteria_hash": criteria["hash"]},
            )
        run["k2"] = self.k2.sync_run(run)
        self.store.save_run(run)
        return run

    def _qualify(
        self,
        company: CompanyInput,
        evidence: list[Evidence],
        criteria_markdown: str,
        qualifier: str,
    ) -> tuple[Classification | None, str | None]:
        if qualifier != "claude":
            return None, None
        classifier = self.classifier or classify_with_claude
        try:
            classification = classifier(company, evidence, criteria_markdown=criteria_markdown)
            return classification, None
        except ClaudeUnavailable as exc:
            return None, f"Claude qualifier unavailable; scored with rules instead ({exc})."
        except Exception as exc:  # noqa: BLE001 - never fail a run because the judge is down
            return None, f"Claude qualifier failed; scored with rules instead ({exc})."

    def answer_question(self, *, run_id: str, question: str) -> dict[str, object]:
        run = self.store.load_run(run_id)
        if not run:
            return {"answer": "Run not found.", "citations": [], "matched_leads": []}
        if question.strip():
            k2_answer = self.k2.answer_question(run, question)
            if k2_answer.get("status") == "ok":
                return {
                    "answer": k2_answer.get("answer", ""),
                    "citations": k2_answer.get("citations", []),
                    "matched_leads": [],
                    "provider": "k2",
                    "corpus_id": k2_answer.get("corpus_id"),
                    "model": k2_answer.get("model"),
                    "k2": {
                        "status": "ok",
                        "raw_result_count": k2_answer.get("raw_result_count", 0),
                    },
                }
        terms = _query_terms(question)
        matches = []
        for lead in run.get("leads", []):
            score = lead.get("score", {})
            company = score.get("company", {})
            for item in lead.get("evidence", []):
                text = f"{item.get('title', '')} {item.get('url', '')} {item.get('text', '')} {item.get('metadata', {})}"
                rank = sum(1 for term in terms if term in text.lower())
                if rank:
                    matches.append((rank, lead, item))
            metadata_text = str(lead.get("metadata", {})).lower()
            metadata_rank = sum(1 for term in terms if term in metadata_text)
            if metadata_rank:
                metadata_rank = min(metadata_rank, 2)
                company = score.get("company", {})
                synthetic = {
                    "url": company.get("domain"),
                    "evidence_id": "metadata",
                    "text": _metadata_snippet(lead.get("metadata", {})),
                    "metadata": {
                        "source_type": "metadata",
                        "page_category": "summary",
                    },
                }
                matches.append((metadata_rank, lead, synthetic))
        matches.sort(key=lambda item: (item[0], _direct_evidence_rank(item), item[1].get("score", {}).get("total_score", 0)), reverse=True)
        citations = [_citation_from_match(match) for match in matches[:8]]
        if not citations:
            top = run.get("leads", [])[:3]
            return {
                "answer": "I did not find direct evidence for that question in the stored run. The strongest current leads are "
                + ", ".join(item.get("score", {}).get("company", {}).get("company", "") for item in top if item.get("score")),
                "citations": [],
                "matched_leads": [item.get("id") for item in top],
                "provider": "local",
                "metadata_used": _metadata_used_summary(top),
            }
        return {
            "answer": _local_research_brief(question, matches[:8], run),
            "citations": citations,
            "matched_leads": _matched_lead_ids(matches[:8]),
            "provider": "local",
            "metadata_used": _metadata_used_summary([match[1] for match in matches[:8]]),
        }

    def _collect_evidence(
        self,
        company: CompanyInput,
        candidate: DiscoveryCandidate,
        cache_dir: Path,
        *,
        fetch: bool,
        max_pages: int,
    ) -> tuple[list[Evidence], list[str]]:
        if not fetch:
            return [], ["Public fetching skipped by run configuration."]
        if self.evidence_fetcher:
            return self.evidence_fetcher(company, cache_dir)
        return fetch_company_evidence(
            company,
            cache_dir / _safe_name(company.company),
            max_pages=max_pages,
            extra_urls=_candidate_resource_urls(candidate),
        )

    def _collect_metadata(
        self,
        company: CompanyInput,
        candidate: DiscoveryCandidate,
        *,
        include_github: bool,
        use_apollo: bool,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "source_refs": {
                "github_urls": candidate.github_urls,
                "linkedin_urls": candidate.linkedin_urls,
                "other_urls": candidate.other_urls,
            },
        }
        if include_github:
            metadata["github"] = search_github_metadata(company.company, company.domain)
        if use_apollo:
            metadata["apollo_organizations"] = self.apollo.search_organizations(domains=[company.domain], query=company.company)
        else:
            metadata["apollo_organizations"] = {"status": "skipped", "reason": "Apollo enrichment disabled for this run.", "organizations": []}
        return metadata


def _resolve_qualifier(settings: dict[str, object]) -> str:
    value = str(settings.get("qualifier") or "rules").strip().lower()
    return value if value in {"rules", "claude"} else "rules"


def _qualification_metadata(qualifier: str, score: object) -> dict[str, object]:
    classification = getattr(score, "classification", None)
    return {
        "qualifier": qualifier,
        "source": getattr(classification, "source", "rules"),
        "confidence": getattr(classification, "confidence", 0.0),
        "ai_narrative": getattr(score, "ai_narrative", ""),
        "reasons": dict(getattr(classification, "reasons", {}) or {}),
        "evidence_ids": dict(getattr(classification, "evidence_ids", {}) or {}),
    }


def _dedupe_candidates(candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
    seen: set[str] = set()
    result: list[DiscoveryCandidate] = []
    for candidate in candidates:
        key = candidate.domain.lower().removeprefix("www.")
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _search_warnings_for_candidates(warnings: list[str], has_candidates: bool) -> list[str]:
    if not has_candidates:
        return warnings
    return [
        "No additional company domains were discovered from search results."
        if warning == "No company domains were discovered from search results."
        else warning
        for warning in warnings
    ]


def _candidates_from_payload(items: list[object]) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        domain = normalize_domain(str(item.get("domain", "")))
        if not domain:
            continue
        company = normalize_whitespace(str(item.get("company", ""))) or _company_from_domain(domain)
        candidates.append(
            DiscoveryCandidate(
                company=company,
                domain=domain,
                source_url=str(item.get("source_url") or f"https://{domain}"),
                source_title=str(item.get("source_title") or "Selected candidate"),
                notes=str(item.get("notes") or "Selected in dashboard preview."),
                github_urls=_string_list(item.get("github_urls")),
                linkedin_urls=_string_list(item.get("linkedin_urls")),
                other_urls=_string_list(item.get("other_urls")),
            )
        )
    return candidates


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        cleaned = str(item).strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _company_from_domain(domain: str) -> str:
    stem = domain.removeprefix("www.").split(".", 1)[0]
    return " ".join(part.capitalize() for part in re.split(r"[-_]", stem) if part)


def _candidate_notes(candidate: DiscoveryCandidate) -> str:
    parts = [candidate.notes]
    if candidate.source_title:
        parts.append(candidate.source_title)
    if candidate.source_url:
        parts.append(candidate.source_url)
    return normalize_whitespace(" ".join(part for part in parts if part))


def _candidate_resource_urls(candidate: DiscoveryCandidate) -> list[str]:
    urls: list[str] = []
    for values in [candidate.github_urls, candidate.linkedin_urls, candidate.other_urls]:
        for value in values:
            cleaned = str(value).strip()
            if cleaned and cleaned not in urls:
                urls.append(cleaned)
    return urls


def _query_terms(question: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]{3,}", question.lower()) if term not in {"the", "and", "for", "with", "that", "this"}]


def _citation_from_match(match: tuple[int, dict[str, object], dict[str, object]]) -> dict[str, object]:
    _, lead, evidence = match
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    evidence_metadata = evidence.get("metadata", {}) if isinstance(evidence.get("metadata"), dict) else {}
    lead_metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
    signal_tags = _evidence_signal_tags(lead_metadata, evidence.get("evidence_id")) or _string_values(evidence_metadata.get("signal_tags", []))
    return {
        "company": company.get("company"),
        "domain": company.get("domain"),
        "url": evidence.get("url"),
        "evidence_id": evidence.get("evidence_id"),
        "snippet": compact_snippet(str(evidence.get("text", "")), 420),
        "source_type": evidence.get("source_type") or evidence_metadata.get("source_type"),
        "page_category": evidence_metadata.get("page_category"),
        "signal_tags": signal_tags,
    }


def _direct_evidence_rank(match: tuple[int, dict[str, object], dict[str, object]]) -> int:
    evidence = match[2]
    return 0 if evidence.get("evidence_id") == "metadata" else 1


def _local_research_brief(question: str, matches: list[tuple[int, dict[str, object], dict[str, object]]], run: dict[str, object]) -> str:
    leads = _unique_leads(matches)
    lines = [
        f"Research brief: {question.strip() or run.get('query') or 'current run'}",
        "",
        "Best supported accounts:",
    ]
    for index, lead in enumerate(leads[:3], start=1):
        score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
        company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
        strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
        metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
        criteria = metadata.get("criteria_profile", {}) if isinstance(metadata.get("criteria_profile"), dict) else {}
        lines.extend(
            [
                f"{index}. {company.get('company')} ({company.get('domain')}) - Tier {score.get('tier')} / {score.get('total_score')}/100.",
                f"   Why it matters: {strategy.get('outreach_angle') or score.get('next_action') or 'Review stored evidence before outreach.'}",
                f"   Recommended GTM motion: {strategy.get('offer') or 'Use the primary workflow automation angle.'}",
                f"   First step: {strategy.get('first_step') or 'Run manual validation before outreach.'}",
                f"   Personas: {_persona_summary(strategy)}",
                f"   Metadata used: signals={_join_values(metadata.get('signal_tags', []))}; coverage={_coverage_summary(metadata)}; criteria={_criteria_summary(criteria)}.",
            ]
        )
    lines.extend(
        [
            "",
            f"Evidence base: {len(matches)} matching evidence/metadata hits across {len(leads)} account(s).",
            f"Source mix: {_source_mix_summary(leads)}.",
        ]
    )
    return "\n".join(lines)


def _unique_leads(matches: list[tuple[int, dict[str, object], dict[str, object]]]) -> list[dict[str, object]]:
    leads = []
    seen = set()
    for _, lead, _ in matches:
        score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
        company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
        key = str(company.get("domain") or lead.get("id") or "")
        if key and key not in seen:
            seen.add(key)
            leads.append(lead)
    return leads


def _matched_lead_ids(matches: list[tuple[int, dict[str, object], dict[str, object]]]) -> list[str]:
    ids = []
    for lead in _unique_leads(matches):
        score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
        company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
        value = str(company.get("domain") or lead.get("id") or "")
        if value:
            ids.append(value)
    return ids


def _metadata_used_summary(leads: list[object]) -> dict[str, object]:
    signal_tags: set[str] = set()
    source_types: set[str] = set()
    page_categories: set[str] = set()
    coverage: set[str] = set()
    persona_titles: set[str] = set()
    criteria_hashes: set[str] = set()
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
        strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
        signal_tags.update(_string_values(metadata.get("signal_tags", [])))
        criteria_profile = metadata.get("criteria_profile", {}) if isinstance(metadata.get("criteria_profile"), dict) else {}
        if criteria_profile.get("hash"):
            criteria_hashes.add(str(criteria_profile.get("hash")))
        coverage_map = metadata.get("intelligence_coverage", {}) if isinstance(metadata.get("intelligence_coverage"), dict) else {}
        coverage.update(key for key, value in coverage_map.items() if value)
        for item in metadata.get("evidence_metadata", []) if isinstance(metadata.get("evidence_metadata"), list) else []:
            if isinstance(item, dict):
                if item.get("source_type"):
                    source_types.add(str(item.get("source_type")))
                if item.get("page_category"):
                    page_categories.add(str(item.get("page_category")))
        for persona in strategy.get("personas", []) if isinstance(strategy.get("personas"), list) else []:
            if isinstance(persona, dict) and persona.get("title"):
                persona_titles.add(str(persona.get("title")))
    return {
        "signal_tags": sorted(signal_tags),
        "source_types": sorted(source_types),
        "page_categories": sorted(page_categories),
        "coverage": sorted(coverage),
        "persona_titles": sorted(persona_titles),
        "criteria_hashes": sorted(criteria_hashes),
    }


def _evidence_signal_tags(lead_metadata: dict[str, object], evidence_id: object) -> list[str]:
    for item in lead_metadata.get("evidence_metadata", []) if isinstance(lead_metadata.get("evidence_metadata"), list) else []:
        if isinstance(item, dict) and item.get("evidence_id") == evidence_id:
            return _string_values(item.get("signal_tags", []))
    return []


def _persona_summary(strategy: dict[str, object]) -> str:
    personas = strategy.get("personas", []) if isinstance(strategy.get("personas"), list) else []
    labels = []
    for persona in personas[:3]:
        if isinstance(persona, dict):
            title = str(persona.get("title") or "").strip()
            priority = str(persona.get("priority") or "").strip()
            if title:
                labels.append(f"{title} ({priority})" if priority else title)
    return ", ".join(labels) if labels else "No persona recommendation stored"


def _coverage_summary(metadata: dict[str, object]) -> str:
    coverage = metadata.get("intelligence_coverage", {}) if isinstance(metadata.get("intelligence_coverage"), dict) else {}
    labels = [key.replace("_", " ") for key, value in coverage.items() if value]
    return ", ".join(labels[:5]) if labels else "limited"


def _criteria_summary(criteria: dict[str, object]) -> str:
    if not criteria:
        return "default profile"
    return (
        f"A>={criteria.get('tier_a_threshold', 75)}, "
        f"B>={criteria.get('tier_b_threshold', 60)}, "
        f"employees {criteria.get('min_employee_count', 25)}-{criteria.get('max_employee_count', 2000)}"
    )


def _source_mix_summary(leads: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for lead in leads:
        metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
        for key, value in metadata.get("source_counts", {}).items() if isinstance(metadata.get("source_counts"), dict) else []:
            counts[str(key)] = counts.get(str(key), 0) + int(value)
    if not counts:
        return "metadata-only"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items())[:8])


def _join_values(value: object) -> str:
    values = _string_values(value)
    return ", ".join(values[:8]) if values else "none"


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "company"


def _metadata_snippet(metadata: object) -> str:
    text = normalize_whitespace(str(metadata))
    return compact_snippet(text, 900)
