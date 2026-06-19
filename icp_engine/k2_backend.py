from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .enrichment import normalize_domain
from .k2_client import K2RestClient
from .mining import (
    MINING_FILTER_KEYS,
    MINING_FILTER_OPS,
    build_facets,
    lookalikes_local,
    mine_local,
    normalize_clauses,
    shape_live_results,
)
from .prospects import build_run_prospects
from .tenant import K2Settings


class K2Backend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        k2_settings: K2Settings | None = None,
    ) -> None:
        self.k2 = k2_settings or K2Settings()
        self.api_key = api_key if api_key is not None else os.environ.get("K2_API_KEY")
        self.base_url = base_url or os.environ.get("K2_BASE_URL") or self.k2.base_url
        self.research_corpus_id = os.environ.get("K2_RESEARCH_CORPUS_ID", "").strip()
        self.corpus_ids = {
            key: os.environ.get(f"K2_{key.upper()}_CORPUS_ID", "").strip()
            for key in ("candidate", "evidence", "prospect", "source", "criteria")
        }

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def build_documents(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for lead in run.get("leads", []):
            score = lead.get("score", {})
            company = score.get("company", {})
            strategy = lead.get("strategy", {})
            lead_metadata = lead.get("metadata", {})
            documents.append(_account_summary_document(run, lead, score, company, strategy, lead_metadata))
            documents.append(_account_dossier_document(run, lead, score, company, strategy, lead_metadata))
            for item in lead.get("evidence", []):
                item_metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
                source_type = item.get("source_type") or item_metadata.get("source_type") or _source_type(item.get("url", ""))
                page_category = item_metadata.get("page_category") or _page_category(item.get("url", ""))
                documents.append(
                    {
                        "id": f"{run.get('id')}:{company.get('domain')}:{item.get('evidence_id')}",
                        "text": item.get("text", ""),
                        "metadata": {
                            "run_id": run.get("id"),
                            "query": run.get("query"),
                            "criteria_hash": run.get("criteria", {}).get("hash"),
                            "company": company.get("company"),
                            "domain": company.get("domain"),
                            "tier": score.get("tier"),
                            "total_score": score.get("total_score"),
                            "ai_posture": score.get("classification", {}).get("ai_posture"),
                            "source_type": source_type,
                            "page_category": page_category,
                            "source_url": item.get("url"),
                            "source_title": item.get("title"),
                            "evidence_id": item.get("evidence_id"),
                            "signal_tags": _evidence_signal_tags(lead_metadata, item.get("evidence_id")),
                            "persona_titles": [persona.get("title") for persona in strategy.get("personas", [])],
                            "outreach_angle": strategy.get("outreach_angle"),
                        },
                    }
                )
        for prospect in build_run_prospects(run).get("prospects", []):
            if isinstance(prospect, dict):
                documents.append(_prospect_document(run, prospect))
        return documents

    def build_manifest(self, run: dict[str, Any]) -> dict[str, Any]:
        documents = self.build_documents(run)
        metadata_keys = sorted({key for document in documents for key in document.get("metadata", {})})
        return {
            "status": "ready",
            "k2_configured": self.configured,
            "base_url": self.base_url,
            "run_id": run.get("id"),
            "query": run.get("query"),
            "document_count": len(documents),
            "metadata_keys": metadata_keys,
            "documents": documents,
        }

    def export_manifest(self, run: dict[str, Any], out_path: Path) -> dict[str, Any]:
        manifest = {
            **self.build_manifest(run),
            "export_path": str(out_path),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest

    def sync_run(self, run: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "skipped",
                "reason": "K2_API_KEY is not configured.",
                "document_count": len(self.build_documents(run)),
            }
        return {
            "status": "ready_for_sdk_sync",
            "reason": "Python sync is intentionally metadata-first in this slice. Use exported documents with the K2 SDK ingestion job.",
            "base_url": self.base_url,
            "document_count": len(self.build_documents(run)),
        }

    def build_upload_documents(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        upload_documents: list[dict[str, Any]] = []
        for document in self.build_documents(run):
            metadata = document.get("metadata", {}) if isinstance(document.get("metadata"), dict) else {}
            source_uri = str(metadata.get("source_url") or f"{self.k2.source_uri_prefix}/{document.get('id')}")
            if not source_uri.startswith(("http://", "https://", "inline://")):
                source_uri = f"{self.k2.source_uri_prefix}/{source_uri}"
            upload_documents.append(
                {
                    "sourceUri": f"{source_uri}#k2-icp-{metadata.get('evidence_id', document.get('id'))}",
                    "rawText": str(document.get("text", "")),
                    "metadata": metadata,
                }
            )
        return [document for document in upload_documents if document["rawText"].strip()]

    def sync_manifest(
        self,
        run: dict[str, Any],
        *,
        project_name: str | None = None,
        corpus_name: str | None = None,
        description: str = "Agentic GTM lead research evidence and metadata.",
        apply: bool = False,
        client: K2RestClient | None = None,
    ) -> dict[str, Any]:
        documents = self.build_upload_documents(run)
        project_name = project_name or self.k2.project_name
        corpus_name = corpus_name or f"ICP Run {run.get('id')}"
        if not apply:
            return {
                "status": "dry_run",
                "project_name": project_name,
                "corpus_name": corpus_name,
                "document_count": len(documents),
                "k2_configured": self.configured,
            }
        if not self.configured and client is None:
            return {
                "status": "error",
                "reason": "K2_API_KEY is required when apply=true.",
                "document_count": len(documents),
            }
        live_client = client or K2RestClient(api_key=self.api_key or "", base_url=self.base_url)
        project = live_client.ensure_project(project_name)
        project_id = str(project.get("id") or project.get("projectId") or "")
        corpus = live_client.ensure_corpus(project_id, corpus_name, description)
        corpus_id = str(corpus.get("id") or corpus.get("corpusId") or "")
        upload = live_client.upload_documents(
            corpus_id,
            documents,
            idempotency_key=f"{self.k2.workspace_namespace}-{run.get('id')}",
            auto_index=False,
        )
        return {
            "status": "uploaded",
            "project_id": project_id,
            "project_name": project.get("name", project_name),
            "corpus_id": corpus_id,
            "corpus_name": corpus.get("name", corpus_name),
            "document_count": len(documents),
            "upload": upload,
        }

    def answer_question(
        self,
        run: dict[str, Any],
        question: str,
        *,
        client: K2RestClient | None = None,
    ) -> dict[str, Any]:
        corpus_id = self._research_corpus_id(run)
        if not corpus_id:
            return {
                "status": "skipped",
                "reason": "No K2 research corpus is configured for this run.",
            }
        if not self.configured and client is None:
            return {
                "status": "skipped",
                "reason": "K2_API_KEY is not configured.",
                "corpus_id": corpus_id,
            }
        live_client = client or K2RestClient(api_key=self.api_key or "", base_url=self.base_url)
        payload = live_client.generate_answer(
            corpus_id,
            question,
            top_k=8,
            filters=_run_metadata_filter(str(run.get("id") or "")),
        )
        return {
            "status": "ok",
            "provider": "k2",
            "corpus_id": corpus_id,
            "answer": str(payload.get("answer") or ""),
            "model": payload.get("model"),
            "citations": _k2_citations(payload.get("results", [])),
            "raw_result_count": len(payload.get("results", [])) if isinstance(payload.get("results"), list) else 0,
        }

    def known_domains(
        self,
        domains: list[str],
        *,
        run: dict[str, Any] | None = None,
        client: K2RestClient | None = None,
    ) -> set[str]:
        """Return the subset of candidate domains already ingested in the K2 research corpus.

        This is the cost lever: companies already in the corpus don't need to be
        researched again. Best-effort and never fatal — an unconfigured K2, a missing
        research corpus, or any upstream error yields an empty set so discovery keeps
        running. Returned domains are normalized to match ``DiscoveryCandidate.domain``.
        """
        wanted = {normalize_domain(domain) for domain in domains if normalize_domain(domain)}
        if not wanted:
            return set()
        corpus_id = self._research_corpus_id(run or {})
        if not corpus_id:
            return set()
        if not self.configured and client is None:
            return set()
        live_client = client or K2RestClient(api_key=self.api_key or "", base_url=self.base_url)
        try:
            payload = live_client.search_batch(corpus_id, sorted(wanted), top_k=1)
        except Exception:  # noqa: BLE001 - never fail discovery because K2 is unreachable
            return set()
        present = {normalize_domain(domain) for domain in _domains_in_payload(payload)}
        return wanted & present

    def mine_corpus(
        self,
        *,
        query: str = "",
        filters: Any = None,
        corpus_key: str = "candidate",
        top_k: int = 20,
        run: dict[str, Any] | None = None,
        client: K2RestClient | None = None,
        store: Any | None = None,
    ) -> dict[str, Any]:
        """Advanced metadata-filtered search over an ICP corpus, hybrid with a local fallback.

        Live K2 path when a corpus is configured; degrades to an in-memory mine over
        persisted runs (``store``) when K2 is unconfigured or the call fails. A bad
        filter key/op raises ``ValueError`` (a 400 at the surface), never a silent local
        fallthrough.
        """
        clauses = normalize_clauses(filters)
        metadata_filter = build_metadata_filter(clauses)
        corpus_id = self._mining_corpus_id(corpus_key, run)
        warnings: list[str] = []
        if corpus_id and (self.configured or client is not None):
            live_client = client or K2RestClient(api_key=self.api_key or "", base_url=self.base_url)
            # A free-text query rides K2's semantic ranker, which reranks and narrows
            # the result away from the exact metadata match set — the bake-off measured
            # filtering F1 collapsing 1.0 -> 0.05 when a query accompanied a
            # `tier in [A,B]`-style filter, while the same filter with an empty query
            # stayed exact. So when the caller supplies metadata clauses, treat it as an
            # exact filter and drop the semantic query (K2's empty-query metadata
            # filtering is exact). Keep the query only for filter-free semantic mining.
            search_query = "" if clauses else (query or "")
            try:
                payload = live_client.search_batch(corpus_id, [search_query], top_k=top_k, filters=metadata_filter)
            except Exception as exc:  # noqa: BLE001 - never fail mining because K2 is unreachable
                warnings.append(f"K2 mining failed ({exc}); using local fallback.")
            else:
                results = shape_live_results(payload, top_k=top_k)
                return {
                    "provider": "k2",
                    "corpus": corpus_key,
                    "corpus_id": corpus_id,
                    "results": results,
                    "facets": build_facets(results),
                    "warnings": warnings,
                }
        if store is not None:
            local = mine_local(store, query=query, clauses=clauses, corpus_key=corpus_key, top_k=top_k)
            local["warnings"] = warnings + local.get("warnings", [])
            return local
        warnings.append("K2 not configured and no local store available for mining.")
        return {"provider": "local", "corpus": corpus_key, "results": [], "facets": {}, "warnings": warnings}

    def find_lookalikes(
        self,
        *,
        seed_domains: list[str],
        corpus_key: str = "candidate",
        top_k: int = 20,
        run: dict[str, Any] | None = None,
        client: K2RestClient | None = None,
        store: Any | None = None,
    ) -> dict[str, Any]:
        """Find companies like the seed accounts over the corpus, hybrid with a local fallback.

        Seeds are always excluded from their own results. The live path searches the
        corpus with a profile query built from the seeds' own metadata (not hardcoded);
        the local path ranks persisted non-seed leads by shared ICP features.
        """
        seeds = {normalize_domain(domain) for domain in seed_domains if normalize_domain(domain)}
        if not seeds:
            return {"provider": "local", "corpus": corpus_key, "results": [], "facets": {}, "warnings": ["No seed domains supplied."]}

        corpus_id = self._mining_corpus_id(corpus_key, run)
        warnings: list[str] = []
        if corpus_id and (self.configured or client is not None):
            live_client = client or K2RestClient(api_key=self.api_key or "", base_url=self.base_url)
            profile_query = self._lookalike_query(seeds, store)
            try:
                payload = live_client.search_batch(corpus_id, [profile_query], top_k=top_k + len(seeds))
            except Exception as exc:  # noqa: BLE001 - never fail because K2 is unreachable
                warnings.append(f"K2 lookalike search failed ({exc}); using local fallback.")
            else:
                results = [r for r in shape_live_results(payload, top_k=top_k + len(seeds)) if r["domain"] not in seeds][:top_k]
                return {
                    "provider": "k2",
                    "corpus": corpus_key,
                    "corpus_id": corpus_id,
                    "seed_domains": sorted(seeds),
                    "results": results,
                    "facets": build_facets(results),
                    "warnings": warnings,
                }
        if store is not None:
            local = lookalikes_local(store, seed_domains=sorted(seeds), corpus_key=corpus_key, top_k=top_k)
            local["seed_domains"] = sorted(seeds)
            local["warnings"] = warnings + local.get("warnings", [])
            return local
        warnings.append("K2 not configured and no local store available for lookalikes.")
        return {"provider": "local", "corpus": corpus_key, "seed_domains": sorted(seeds), "results": [], "facets": {}, "warnings": warnings}

    def _lookalike_query(self, seeds: set[str], store: Any | None) -> str:
        """Build a similarity query from the seeds' own ICP signals (vertical/posture)."""
        terms: list[str] = []
        if store is not None:
            for record in mine_local(store, query="", clauses=[], corpus_key="candidate", top_k=500).get("results", []):
                if record.get("domain") in seeds:
                    terms.extend(str(record.get(field) or "") for field in ("vertical", "ai_posture", "company"))
        terms = [term for term in terms if term.strip()]
        return " ".join(dict.fromkeys(terms)) or "vertical market software workflow data weak AI posture"

    def _mining_corpus_id(self, corpus_key: str, run: dict[str, Any] | None) -> str:
        specific = self.corpus_ids.get(corpus_key) or ""
        if specific:
            return specific
        return self._research_corpus_id(run or {})

    def _research_corpus_id(self, run: dict[str, Any]) -> str:
        k2_status = run.get("k2", {}) if isinstance(run.get("k2"), dict) else {}
        return str(k2_status.get("corpus_id") or self.research_corpus_id or "").strip()


def _domains_in_payload(payload: object) -> set[str]:
    """Collect every ``domain`` value anywhere in a K2 search payload.

    Walks the response generically so it survives shape differences (batched
    results, nested metadata blocks) without hardcoding the result envelope.
    """
    found: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "domain" and isinstance(value, str) and value.strip():
                    found.add(value.strip())
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return found


def _source_type(url: str) -> str:
    host = url.lower()
    if "github.com" in host:
        return "github"
    if "linkedin.com" in host:
        return "linkedin"
    return "website"


def _page_category(url: str) -> str:
    path = url.lower()
    if any(term in path for term in ["/docs", "/developers", "/api"]):
        return "docs"
    if "pricing" in path:
        return "pricing"
    if "case" in path or "customers" in path:
        return "customers"
    if "careers" in path or "jobs" in path:
        return "careers"
    if "contact" in path or "demo" in path:
        return "contact"
    if any(term in path for term in ["ai", "copilot", "assistant", "gpt"]):
        return "ai"
    if any(term in path for term in ["product", "platform", "solutions"]):
        return "product"
    return "homepage" if path.rstrip("/").count("/") <= 2 else "other"


def build_metadata_filter(clauses: list[tuple[str, str, Any]]) -> dict[str, Any]:
    """Build a K2 metadata-filter dict from ``(key, op, value)`` clauses.

    Returns the same ``{"condition": "and", "filters": [...]}`` envelope K2 search and
    ``generate_answer`` already expect. Keys are constrained to ``MINING_FILTER_KEYS`` and
    ops to a small supported set so the shared filter seam can't be fed unknown fields.
    """
    filters: list[dict[str, Any]] = []
    for key, op, value in clauses:
        if key not in MINING_FILTER_KEYS:
            raise ValueError(f"Unsupported metadata filter key: {key!r}")
        if op not in MINING_FILTER_OPS:
            raise ValueError(f"Unsupported metadata filter op: {op!r}")
        filters.append({"key": key, "op": op, "value": value})
    return {"condition": "and", "filters": filters}


def _run_metadata_filter(run_id: str) -> dict[str, Any]:
    return build_metadata_filter([("run_id", "==", run_id)] if run_id else [])


def _k2_citations(results: object) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    citations = []
    for item in results[:8]:
        if not isinstance(item, dict):
            continue
        metadata = _merged_result_metadata(item)
        citations.append(
            {
                "company": metadata.get("company"),
                "domain": metadata.get("domain"),
                "url": metadata.get("source_url") or metadata.get("sourceUri") or metadata.get("url"),
                "evidence_id": metadata.get("evidence_id") or item.get("documentId") or item.get("document_id"),
                "snippet": str(item.get("text") or "")[:420],
                "score": item.get("score"),
                "source_type": metadata.get("source_type"),
                "page_category": metadata.get("page_category"),
            }
        )
    return citations


def _merged_result_metadata(item: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("metadata", "customMetadata", "custom_metadata", "systemMetadata", "system_metadata"):
        value = item.get(key)
        if isinstance(value, dict):
            merged.update(value)
    system = item.get("systemMetadata") or item.get("system_metadata")
    provenance = system.get("provenance") if isinstance(system, dict) and isinstance(system.get("provenance"), dict) else {}
    if provenance:
        merged.update({key: value for key, value in provenance.items() if key not in merged})
    return merged


def _account_summary_document(
    run: dict[str, Any],
    lead: dict[str, Any],
    score: dict[str, Any],
    company: dict[str, Any],
    strategy: dict[str, Any],
    lead_metadata: dict[str, Any],
) -> dict[str, Any]:
    source_refs = lead_metadata.get("source_refs", {}) if isinstance(lead_metadata.get("source_refs"), dict) else {}
    criteria_profile = lead_metadata.get("criteria_profile", {}) if isinstance(lead_metadata.get("criteria_profile"), dict) else {}
    qualification = lead_metadata.get("qualification", {}) if isinstance(lead_metadata.get("qualification"), dict) else {}
    ai_narrative = str(qualification.get("ai_narrative", "") or score.get("ai_narrative", ""))
    text = "\n".join(
        [
            f"Company: {company.get('company')} ({company.get('domain')})",
            f"Tier: {score.get('tier')} score {score.get('total_score')}",
            f"Criteria: Tier A >= {criteria_profile.get('tier_a_threshold', 75)}, Tier B >= {criteria_profile.get('tier_b_threshold', 60)}, employee range {criteria_profile.get('min_employee_count', 25)}-{criteria_profile.get('max_employee_count', 2000)}",
            f"Qualifier: {qualification.get('qualifier', 'rules')} via {qualification.get('source', 'rules')}",
            f"AI narrative: {ai_narrative or 'n/a'}",
            f"Strategy: {strategy.get('outreach_angle')}",
            f"Offer: {strategy.get('offer')}",
            f"Personas: {', '.join(persona.get('title', '') for persona in strategy.get('personas', []))}",
            f"Signals: {', '.join(lead_metadata.get('signal_tags', []))}",
            f"Source counts: {lead_metadata.get('source_counts', {})}",
            f"Public profiles and resources: {_source_ref_summary(source_refs)}",
        ]
    )
    return {
        "id": f"{run.get('id')}:{company.get('domain')}:account-summary",
        "text": text,
        "metadata": {
            "run_id": run.get("id"),
            "query": run.get("query"),
            "criteria_hash": run.get("criteria", {}).get("hash"),
            "company": company.get("company"),
            "domain": company.get("domain"),
            "tier": score.get("tier"),
            "total_score": score.get("total_score"),
            "ai_posture": score.get("classification", {}).get("ai_posture"),
            "source_type": "account_summary",
            "page_category": "summary",
            "source_url": company.get("domain"),
            "evidence_id": "account-summary",
            "qualifier": qualification.get("qualifier", "rules"),
            "qualifier_source": qualification.get("source", "rules"),
            "qualifier_confidence": qualification.get("confidence", 0.0),
            "ai_narrative": ai_narrative,
            "signal_tags": lead_metadata.get("signal_tags", []),
            "criteria_tier_a_threshold": criteria_profile.get("tier_a_threshold"),
            "criteria_tier_b_threshold": criteria_profile.get("tier_b_threshold"),
            "criteria_min_employee_count": criteria_profile.get("min_employee_count"),
            "criteria_max_employee_count": criteria_profile.get("max_employee_count"),
            "criteria_priority_terms": criteria_profile.get("priority_terms", []),
            "github_urls": _source_ref_values(source_refs, "github_urls"),
            "linkedin_urls": _source_ref_values(source_refs, "linkedin_urls"),
            "social_urls": _source_ref_values(source_refs, "social_urls"),
            "marketplace_urls": _source_ref_values(source_refs, "marketplace_urls"),
            "docs_urls": _source_ref_values(source_refs, "docs_urls"),
            "pricing_urls": _source_ref_values(source_refs, "pricing_urls"),
            "contact_urls": _source_ref_values(source_refs, "contact_urls"),
            "public_profile_count": lead_metadata.get("public_profile_count", 0),
            "public_resource_count": lead_metadata.get("public_resource_count", 0),
            "persona_titles": [persona.get("title") for persona in strategy.get("personas", [])],
            "outreach_angle": strategy.get("outreach_angle"),
        },
    }


def _excerpt(text: object, limit: int = 280) -> str:
    """Collapse whitespace and truncate to ``limit`` chars at a sentence boundary."""
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if boundary >= limit // 2:
        return cut[: boundary + 1]
    return cut.rstrip(" ,;:") + "…"


def _account_dossier_document(
    run: dict[str, Any],
    lead: dict[str, Any],
    score: dict[str, Any],
    company: dict[str, Any],
    strategy: dict[str, Any],
    lead_metadata: dict[str, Any],
) -> dict[str, Any]:
    """One self-contained per-account markdown brief for grounding retrieval.

    Recomposes data already in the run (qualification narrative, criteria fit,
    scraped evidence, outreach strategy, public footprint) into a single coherent
    document. Deterministic — no LLM call; the ``ai_narrative`` is generated
    upstream during qualification, here it is only reformatted.
    """
    source_refs = lead_metadata.get("source_refs", {}) if isinstance(lead_metadata.get("source_refs"), dict) else {}
    criteria_profile = lead_metadata.get("criteria_profile", {}) if isinstance(lead_metadata.get("criteria_profile"), dict) else {}
    qualification = lead_metadata.get("qualification", {}) if isinstance(lead_metadata.get("qualification"), dict) else {}
    ai_narrative = str(qualification.get("ai_narrative", "") or score.get("ai_narrative", "") or "")
    ai_posture = score.get("classification", {}).get("ai_posture")
    vertical = lead_metadata.get("vertical") or score.get("classification", {}).get("vertical")
    signal_tags = [str(tag) for tag in lead_metadata.get("signal_tags", []) if tag]
    personas = [persona for persona in strategy.get("personas", []) if isinstance(persona, dict)]

    sections: list[str] = [f"# {company.get('company')} — {company.get('domain')}"]

    classification = [
        "## Classification",
        f"{score.get('tier')} (score {score.get('total_score')}). "
        f"AI posture: {ai_posture or 'unknown'}. Vertical: {vertical or 'unspecified'}.",
    ]
    if ai_narrative:
        classification.append(ai_narrative)
    sections.append("\n".join(classification))

    fit = [
        "## Why they fit the ICP",
        f"Criteria: Tier A ≥ {criteria_profile.get('tier_a_threshold', 75)}, "
        f"Tier B ≥ {criteria_profile.get('tier_b_threshold', 60)}, "
        f"employee range {criteria_profile.get('min_employee_count', 25)}-{criteria_profile.get('max_employee_count', 2000)}.",
    ]
    if signal_tags:
        fit.append(f"Matched signals: {', '.join(signal_tags)}.")
    sections.append("\n".join(fit))

    evidence_lines = ["## Evidence"]
    evidence_pages = [item for item in lead.get("evidence", []) if isinstance(item, dict) and str(item.get("text", "")).strip()]
    for item in evidence_pages[:4]:
        title = item.get("title") or item.get("url") or "page"
        evidence_lines.append(f"### {title}")
        evidence_lines.append(_excerpt(item.get("text")))
        if item.get("url"):
            evidence_lines.append(f"Source: {item.get('url')}")
    if len(evidence_lines) == 1:
        evidence_lines.append("No scraped page content captured for this account.")
    sections.append("\n".join(evidence_lines))

    outreach = [
        "## Outreach posture",
        f"Angle: {strategy.get('outreach_angle') or 'n/a'}. Offer: {strategy.get('offer') or 'n/a'}.",
    ]
    for persona in personas:
        rationale = persona.get("why") or persona.get("rationale") or persona.get("priority")
        line = f"- {persona.get('title')}"
        if rationale:
            line += f" — {rationale}"
        outreach.append(line)
    sections.append("\n".join(outreach))

    footprint = ["## Public footprint", _source_ref_summary(source_refs)]
    sections.append("\n".join(footprint))

    text = "\n\n".join(sections)
    return {
        "id": f"{run.get('id')}:{company.get('domain')}:account-dossier",
        "text": text,
        "metadata": {
            "run_id": run.get("id"),
            "query": run.get("query"),
            "criteria_hash": run.get("criteria", {}).get("hash"),
            "company": company.get("company"),
            "domain": company.get("domain"),
            "tier": score.get("tier"),
            "total_score": score.get("total_score"),
            "ai_posture": ai_posture,
            "vertical": vertical,
            "source_type": "account_dossier",
            "page_category": "dossier",
            "source_url": company.get("domain"),
            "evidence_id": "account-dossier",
            "qualifier": qualification.get("qualifier", "rules"),
            "qualifier_source": qualification.get("source", "rules"),
            "ai_narrative": ai_narrative,
            "signal_tags": signal_tags,
            "criteria_tier_a_threshold": criteria_profile.get("tier_a_threshold"),
            "criteria_tier_b_threshold": criteria_profile.get("tier_b_threshold"),
            "criteria_min_employee_count": criteria_profile.get("min_employee_count"),
            "criteria_max_employee_count": criteria_profile.get("max_employee_count"),
            "persona_titles": [persona.get("title") for persona in personas],
            "outreach_angle": strategy.get("outreach_angle"),
        },
    }


def _prospect_document(run: dict[str, Any], prospect: dict[str, Any]) -> dict[str, Any]:
    name = prospect.get("name") or prospect.get("persona")
    text = "\n".join(
        [
            f"Company: {prospect.get('company')} ({prospect.get('domain')})",
            f"Prospect: {name}",
            f"Title: {prospect.get('title')}",
            f"Persona: {prospect.get('persona')} ({prospect.get('persona_priority')})",
            f"Source: {prospect.get('source')} status {prospect.get('status')}",
            f"LinkedIn: {prospect.get('linkedin_url')}",
            f"Outreach angle: {prospect.get('outreach_angle')}",
            f"First step: {prospect.get('first_step')}",
        ]
    )
    return {
        "id": f"{prospect.get('id')}:prospect",
        "text": text,
        "metadata": {
            "run_id": run.get("id"),
            "query": run.get("query"),
            "criteria_hash": run.get("criteria", {}).get("hash"),
            "company": prospect.get("company"),
            "domain": prospect.get("domain"),
            "tier": prospect.get("tier"),
            "total_score": prospect.get("company_score"),
            "source_type": "prospect",
            "page_category": "apollo" if prospect.get("source") == "apollo" else "persona",
            "source_url": prospect.get("linkedin_url") or prospect.get("domain"),
            "evidence_id": prospect.get("id"),
            "prospect_name": prospect.get("name"),
            "prospect_title": prospect.get("title"),
            "persona_title": prospect.get("persona"),
            "persona_priority": prospect.get("persona_priority"),
            "prospect_source": prospect.get("source"),
            "prospect_status": prospect.get("status"),
            "priority_score": prospect.get("priority_score"),
            "outreach_angle": prospect.get("outreach_angle"),
        },
    }


def _evidence_signal_tags(lead_metadata: dict[str, Any], evidence_id: object) -> list[str]:
    for item in lead_metadata.get("evidence_metadata", []):
        if isinstance(item, dict) and item.get("evidence_id") == evidence_id:
            tags = item.get("signal_tags", [])
            return [str(tag) for tag in tags] if isinstance(tags, list) else []
    return []


def _source_ref_values(source_refs: dict[str, Any], key: str) -> list[str]:
    values = source_refs.get(key, [])
    return [str(value) for value in values] if isinstance(values, list) else []


def _source_ref_summary(source_refs: dict[str, Any]) -> str:
    parts = []
    for key in ["linkedin_urls", "github_urls", "social_urls", "marketplace_urls", "docs_urls", "pricing_urls", "contact_urls"]:
        values = _source_ref_values(source_refs, key)
        if values:
            parts.append(f"{key}={values[:3]}")
    return "; ".join(parts) if parts else "none captured"
