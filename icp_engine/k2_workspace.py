from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .k2_backend import K2Backend
from .k2_client import K2ApiError, K2RestClient
from .seed_defaults import (
    SEEDED_CRITERIA_MARKDOWN,
    SEEDED_LISTS,
    SEEDED_PROMPTS,
    SEEDED_SETTINGS,
    seeded_run,
)
from .tenant import K2Settings


DEFAULT_PROJECT_NAME = K2Settings().project_name
DEFAULT_SUMMARY_PATH = Path("out/app_state/k2_workspace_bootstrap.json")


@dataclass(frozen=True)
class CorpusBlueprint:
    key: str
    name: str
    description: str


CORPORA: tuple[CorpusBlueprint, ...] = (
    CorpusBlueprint(
        "source",
        "ICP Source Corpus",
        "Portfolio pages, source lists, SERP results, company pages, and provider payload summaries.",
    ),
    CorpusBlueprint(
        "candidate",
        "ICP Candidate Corpus",
        "Normalized account records for K2-fit ICP candidates.",
    ),
    CorpusBlueprint(
        "evidence",
        "ICP Evidence Corpus",
        "Scoring evidence, score components, hard gates, rationale, and citations.",
    ),
    CorpusBlueprint(
        "prospect",
        "ICP Prospect Corpus",
        "Persona targets, Apollo people, contact confidence, and outreach readiness records.",
    ),
    CorpusBlueprint(
        "criteria",
        "ICP Criteria Corpus",
        "Criteria markdown, prompt versions, settings, lists, accepted/rejected examples, and query profile hints.",
    ),
)


AGENTS: tuple[dict[str, Any], ...] = (
    {
        "key": "source_discovery",
        "name": "ICP Source Discovery Agent",
        "corpus_key": "source",
        "task_type": "extract",
        "description": "Extract normalized company/domain candidates from source pages and list payloads.",
        "instructions": (
            "Extract vertical-market software companies from source records. Prefer pre-2025 "
            "incumbents with workflow/data assets. Return company, domain, source group, "
            "source URL, confidence, and why the candidate may fit the K2 ICP."
        ),
        "declared_schema": {
            "fields_schema": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "domain": {"type": "string"},
                    "category": {"type": "string"},
                    "source_group": {"type": "string"},
                    "source_url": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["company", "domain", "confidence", "reason"],
            }
        },
    },
    {
        "key": "qualification",
        "name": "ICP Company Qualification Agent",
        "corpus_key": "candidate",
        "task_type": "classify",
        "description": "Score candidate accounts against the K2 incumbent-software ICP.",
        "instructions": (
            "Classify each company against the K2 ICP: pre-2025 product company, proprietary "
            "workflow/data moat, weak or shallow public AI posture, budget/access, and feasibility. "
            "Preserve evidence IDs and criteria hash."
        ),
        "declared_schema": {
            "fields_schema": {
                "type": "object",
                "properties": {
                    "tier": {"type": "string"},
                    "total_score": {"type": "number"},
                    "ai_posture": {"type": "string"},
                    "ai_gap_score": {"type": "number"},
                    "data_workflow_score": {"type": "number"},
                    "commercial_urgency_score": {"type": "number"},
                    "budget_access_score": {"type": "number"},
                    "feasibility_score": {"type": "number"},
                    "hard_gate_failed": {"type": "array", "items": {"type": "string"}},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tier", "total_score", "ai_posture"],
            }
        },
    },
    {
        "key": "evidence_gap",
        "name": "ICP Evidence Gap Agent",
        "corpus_key": "evidence",
        "task_type": "review",
        "description": "Find missing source coverage and recommend the next scrape/search/enrichment action.",
        "instructions": (
            "Review evidence records for missing website, API/docs, pricing, contact, AI posture, "
            "and customer proof coverage. Recommend specific follow-up searches or provider calls."
        ),
    },
    {
        "key": "prospect_role",
        "name": "ICP Prospect Role Agent",
        "corpus_key": "evidence",
        "task_type": "extract",
        "description": "Normalize prospect/persona records into a role tree with outreach readiness.",
        "instructions": (
            "Extract product, engineering, data, and vertical GM contacts or fallback personas. "
            "Group by role, preserve legally sourced LinkedIn/email fields, and assign contact confidence."
        ),
        "declared_schema": {
            "fields_schema": {
                "type": "object",
                "properties": {
                    "prospect_name": {"type": "string"},
                    "prospect_title": {"type": "string"},
                    "role_group": {"type": "string"},
                    "persona_priority": {"type": "string"},
                    "linkedin_url": {"type": "string"},
                    "email": {"type": "string"},
                    "contact_confidence": {"type": "number"},
                    "outreach_status": {"type": "string"},
                },
                "required": ["prospect_title", "role_group", "persona_priority"],
            }
        },
    },
    {
        "key": "criteria_refinement",
        "name": "ICP Criteria Refinement Agent",
        "corpus_key": "criteria",
        "task_type": "review",
        "description": "Review accepted/rejected/exported outcomes and propose criteria/query-profile updates.",
        "instructions": (
            "Compare criteria versions, accepted/rejected examples, metadata distributions, and search "
            "feedback. Propose markdown changes and query-profile hints, with risk notes for human review."
        ),
    },
    {
        "key": "outreach",
        "name": "ICP Outreach Draft Agent",
        "corpus_key": "prospect",
        "task_type": "custom",
        "description": "Draft evidence-backed outreach variants for approved prospects.",
        "instructions": (
            "Draft concise outreach subject/body/CTA variants grounded in company evidence, role context, "
            "and the K2 AI opportunity-map offer. Do not fabricate contact details."
        ),
    },
)


FEEDS: tuple[dict[str, Any], ...] = (
    {
        "key": "source_to_candidate",
        "name": "ICP Source-to-Candidate Feed",
        "source_agent_key": "source_discovery",
        "target_corpus_key": "candidate",
        "description": "Reactive extraction of normalized candidate accounts when new source documents land.",
        "reactive": True,
        "execution_mode": "answer",
    },
    {
        "key": "daily_source_sweep",
        "name": "ICP Daily Source Sweep Feed",
        "source_agent_key": "source_discovery",
        "target_corpus_key": "candidate",
        "description": "Daily source-corpus sweep to keep the candidate corpus growing from existing source material.",
        "schedule_interval": "1d",
        "schedule_hour": 9,
        "execution_mode": "answer",
    },
    {
        "key": "candidate_to_evidence",
        "name": "ICP Candidate Qualification Feed",
        "source_agent_key": "qualification",
        "target_corpus_key": "evidence",
        "description": "Reactive qualification of candidate accounts into scored evidence records.",
        "reactive": True,
        "execution_mode": "answer",
    },
    {
        "key": "prospect_expansion",
        "name": "ICP Prospect Expansion Feed",
        "source_agent_key": "prospect_role",
        "target_corpus_key": "prospect",
        "description": "Reactive normalization of prospect records and fallback personas into a role tree.",
        "reactive": True,
        "execution_mode": "answer",
    },
)


def build_seeded_workspace_documents(
    run: dict[str, Any] | None = None,
    *,
    k2_settings: K2Settings | None = None,
) -> dict[str, list[dict[str, Any]]]:
    settings = k2_settings or K2Settings()
    run = run or seeded_run()
    documents = K2Backend(api_key="dry-run", k2_settings=settings).build_upload_documents(run)
    source_docs: list[dict[str, Any]] = []
    candidate_docs: list[dict[str, Any]] = []
    evidence_docs: list[dict[str, Any]] = []
    prospect_docs: list[dict[str, Any]] = []

    for document in documents:
        metadata = document.get("metadata", {}) if isinstance(document.get("metadata"), dict) else {}
        source_type = str(metadata.get("source_type") or "")
        evidence_id = str(metadata.get("evidence_id") or "")
        if source_type == "prospect":
            prospect_docs.append(_with_metadata(document, entity_type="prospect", k2_settings=settings))
            continue
        if evidence_id == "account-summary":
            candidate_docs.append(_with_metadata(document, entity_type="company", k2_settings=settings))
        if source_type != "account_summary":
            source_docs.append(_with_metadata(document, entity_type="source_page", k2_settings=settings))
        evidence_docs.append(_with_metadata(document, entity_type="evidence", k2_settings=settings))

    return {
        "source": _unique_source_uris(source_docs, "source", k2_settings=settings),
        "candidate": _unique_source_uris(candidate_docs, "candidate", k2_settings=settings),
        "evidence": _unique_source_uris(evidence_docs, "evidence", k2_settings=settings),
        "prospect": _unique_source_uris(prospect_docs, "prospect", k2_settings=settings),
        "criteria": _unique_source_uris(_criteria_documents(run, k2_settings=settings), "criteria", k2_settings=settings),
    }


class K2WorkspaceProvisioner:
    def __init__(
        self,
        *,
        client: K2RestClient,
        project_name: str | None = None,
        summary_path: Path = DEFAULT_SUMMARY_PATH,
        k2_settings: K2Settings | None = None,
    ) -> None:
        self.client = client
        self.k2 = k2_settings or K2Settings()
        self.project_name = project_name or self.k2.project_name
        self.summary_path = summary_path

    def ensure_workspace(
        self,
        *,
        apply_uploads: bool = False,
        apply_indexes: bool = False,
        apply_primitives: bool = False,
        batch_size: int = 250,
        poll_seconds: float = 10.0,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        project = self.client.ensure_project(self.project_name)
        project_id = _id(project)
        corpora = self._ensure_corpora(project_id)
        documents = build_seeded_workspace_documents(k2_settings=self.k2)
        summary: dict[str, Any] = {
            "status": "ready",
            "project": {"id": project_id, "name": project.get("name", self.project_name)},
            "corpora": {
                key: {**value, "documents_planned": len(documents[key])} for key, value in corpora.items()
            },
            "uploads": {},
            "index_sync": {},
            "agents": {},
            "feeds": {},
            "pipeline_spec": None,
        }
        self._write_summary(summary)

        if apply_uploads:
            for key in ("criteria", "source", "candidate", "evidence", "prospect"):
                corpus_id = corpora[key]["id"]
                summary["uploads"][key] = self._upload_batches(
                    corpus_id,
                    documents[key],
                    idempotency_prefix=f"{self.k2.workspace_namespace}-{project_id}-{key}",
                    batch_size=batch_size,
                    poll_seconds=poll_seconds,
                    timeout_seconds=timeout_seconds,
                )
                self._write_summary(summary)

        if apply_indexes:
            for key, corpus in corpora.items():
                job = self.client.sync_indexes(
                    corpus["id"],
                    idempotency_key=f"{self.k2.workspace_namespace}-{project_id}-index-sync-{key}",
                )
                summary["index_sync"][key] = {"start": job}
                self._write_summary(summary)
            for key, record in summary["index_sync"].items():
                job_id = _id(record.get("start", {}))
                if job_id:
                    record["job"] = self._wait_for_job(job_id, poll_seconds, timeout_seconds)
                    self._write_summary(summary)

        if apply_primitives:
            agents = self._ensure_agents(project_id, corpora)
            summary["agents"] = agents
            self._write_summary(summary)
            feeds = self._ensure_feeds(project_id, corpora, agents)
            summary["feeds"] = feeds
            self._write_summary(summary)
            pipeline = self.client.ensure_pipeline_spec(
                project_id=project_id,
                name="ICP Expansion Pipeline",
                description="Versioned K2-native ICP expansion graph for source discovery, qualification, prospects, and criteria refinement.",
                topology=build_pipeline_topology(corpora, agents, feeds, k2_settings=self.k2),
            )
            summary["pipeline_spec"] = pipeline
            self._write_summary(summary)

        return summary

    def health_check(self, corpora: dict[str, dict[str, Any]]) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        for key in ("candidate", "prospect", "criteria"):
            metadata = self.client.discover_metadata(corpora[key]["id"], refresh=True, include="top_values")
            fields = metadata.get("fields") if isinstance(metadata.get("fields"), list) else []
            checks[f"{key}_metadata"] = {
                "field_count": len(fields),
                "sample_fields": [field.get("key") for field in fields[:12] if isinstance(field, dict)],
                "total_documents": metadata.get("total_documents"),
                "total_chunks": metadata.get("total_chunks"),
            }
        for key, query in {
            "candidate": "Mojio moj.io fleet telematics",
            "prospect": "Mojio chief product officer prospect",
            "evidence": "Mojio fleet telematics evidence",
        }.items():
            payload = self.client.search_batch(corpora[key]["id"], [query], top_k=3)
            results = _search_results(payload)
            checks[f"{key}_search"] = {
                "query": query,
                "result_count": len(results),
                "warnings": _search_warnings(payload),
                "top_snippets": [_result_snippet(item) for item in results[:3]],
            }
        return checks

    def _ensure_corpora(self, project_id: str) -> dict[str, dict[str, Any]]:
        corpora: dict[str, dict[str, Any]] = {}
        for blueprint in CORPORA:
            corpus = self.client.ensure_corpus(project_id, blueprint.name, blueprint.description)
            corpora[blueprint.key] = {
                "id": _id(corpus),
                "name": str(corpus.get("name") or blueprint.name),
                "description": blueprint.description,
            }
        return corpora

    def _ensure_agents(self, project_id: str, corpora: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        agents: dict[str, dict[str, Any]] = {}
        for blueprint in AGENTS:
            corpus_id = corpora[blueprint["corpus_key"]]["id"]
            agent = self.client.ensure_agent(
                project_id=project_id,
                name=blueprint["name"],
                corpus_id=corpus_id,
                description=blueprint["description"],
                task_type=blueprint["task_type"],
                instructions=blueprint.get("instructions"),
                declared_schema=blueprint.get("declared_schema"),
                harvest_policy="declared-only" if blueprint.get("declared_schema") else None,
            )
            agent_id = _id(agent)
            existing_corpus_id = str(agent.get("corpus_id") or agent.get("corpusId") or "")
            if agent_id and existing_corpus_id and existing_corpus_id != corpus_id:
                agent = self.client.update_agent(
                    agent_id,
                    corpus_id=corpus_id,
                    description=blueprint["description"],
                    task_type=blueprint["task_type"],
                    instructions=blueprint.get("instructions"),
                    declared_schema=blueprint.get("declared_schema"),
                    harvest_policy="declared-only" if blueprint.get("declared_schema") else None,
                )
            if str(agent.get("status") or "").lower() != "active" and agent_id:
                agent = self.client.activate_agent(agent_id)
            agents[blueprint["key"]] = {
                "id": _id(agent) or agent_id,
                "name": str(agent.get("name") or blueprint["name"]),
                "status": str(agent.get("status") or "active"),
            }
        return agents

    def _ensure_feeds(
        self,
        project_id: str,
        corpora: dict[str, dict[str, Any]],
        agents: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        feeds: dict[str, dict[str, Any]] = {}
        for blueprint in FEEDS:
            feed = self.client.ensure_feed(
                project_id=project_id,
                name=blueprint["name"],
                source_agent_id=agents[blueprint["source_agent_key"]]["id"],
                description=blueprint["description"],
                target_corpus_id=corpora[blueprint["target_corpus_key"]]["id"],
                persistent=True,
                reactive=bool(blueprint.get("reactive", False)),
                execution_mode=str(blueprint.get("execution_mode") or "retrieve"),
                schedule_interval=blueprint.get("schedule_interval"),
                schedule_hour=blueprint.get("schedule_hour"),
            )
            feeds[blueprint["key"]] = {"id": _id(feed), "name": str(feed.get("name") or blueprint["name"])}
        return feeds

    def _upload_batches(
        self,
        corpus_id: str,
        documents: list[dict[str, Any]],
        *,
        idempotency_prefix: str,
        batch_size: int,
        poll_seconds: float,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        batches = []
        for index, offset in enumerate(range(0, len(documents), batch_size)):
            batch = documents[offset : offset + batch_size]
            upload = self.client.upload_documents(
                corpus_id,
                batch,
                idempotency_key=f"{idempotency_prefix}-batch-{index}",
                auto_index=False,
            )
            record = {"batch": index, "count": len(batch), "upload": upload}
            job_id = _id(upload)
            if job_id:
                record["job"] = self._wait_for_job(job_id, poll_seconds, timeout_seconds)
            batches.append(record)
        return batches

    def _wait_for_job(self, job_id: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        terminal = {"succeeded", "failed", "cancelled", "canceled"}
        last_job: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_job = self.client.get_job(job_id)
            status = str(last_job.get("status") or "").lower()
            if status in terminal:
                return last_job
            time.sleep(poll_seconds)
        return {**last_job, "status": last_job.get("status") or "timeout"}

    def _write_summary(self, summary: dict[str, Any]) -> None:
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_pipeline_topology(
    corpora: dict[str, dict[str, Any]],
    agents: dict[str, dict[str, Any]],
    feeds: dict[str, dict[str, Any]],
    *,
    k2_settings: K2Settings | None = None,
) -> dict[str, Any]:
    settings = k2_settings or K2Settings()
    return {
        "corpora": [
            {"id": value["id"], "name": value["name"], "description": value.get("description", "")}
            for value in corpora.values()
        ],
        "agents": [
            {
                "id": agents[blueprint["key"]]["id"],
                "name": agents[blueprint["key"]]["name"],
                "description": blueprint["description"],
                "corpus_ref": corpora[blueprint["corpus_key"]]["name"],
                "task_type": blueprint["task_type"],
                "instructions": blueprint.get("instructions"),
            }
            for blueprint in AGENTS
        ],
        "feeds": [
            {
                "id": feeds[blueprint["key"]]["id"],
                "name": feeds[blueprint["key"]]["name"],
                "description": blueprint["description"],
                "agent_ref": agents[blueprint["source_agent_key"]]["name"],
                "target_corpus_ref": corpora[blueprint["target_corpus_key"]]["name"],
                "execution_mode": blueprint.get("execution_mode", "retrieve"),
                "persistent": True,
                "reactive": bool(blueprint.get("reactive", False)),
                "schedule_interval": blueprint.get("schedule_interval"),
            }
            for blueprint in FEEDS
        ],
        "subscriptions": [
            {
                "feed_ref": feeds["source_to_candidate"]["name"],
                "agent_ref": agents["qualification"]["name"],
                "role": "input",
            },
            {
                "feed_ref": feeds["candidate_to_evidence"]["name"],
                "agent_ref": agents["evidence_gap"]["name"],
                "role": "input",
            },
            {
                "feed_ref": feeds["candidate_to_evidence"]["name"],
                "agent_ref": agents["prospect_role"]["name"],
                "role": "input",
            },
        ],
        "metadata": {
            "workspace": settings.workspace_namespace,
            "purpose": "scheduled-reactive-icp-expansion",
            "query_profiles": [
                "portfolio-expansion",
                "ai-gap-audit",
                "workflow-moat",
                "budget-access",
                "prospect-role-tree",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the K2-native ICP workspace.")
    parser.add_argument("--project-name", default=os.environ.get("K2_ICP_PROJECT_NAME", DEFAULT_PROJECT_NAME))
    parser.add_argument("--base-url", default=os.environ.get("K2_BASE_URL", K2Settings().base_url))
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--apply-uploads", action="store_true", help="Upload seeded criteria/source/candidate/evidence/prospect documents.")
    parser.add_argument("--apply-indexes", action="store_true", help="Sync retrieval indexes after upload.")
    parser.add_argument("--apply-primitives", action="store_true", help="Create K2 agents, feeds, and pipeline spec.")
    parser.add_argument("--health-check", action="store_true", help="Run metadata/search checks after provisioning.")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args(argv)

    api_key = os.environ.get("K2_API_KEY") or os.environ.get("K2_DEV_TOKEN")
    if not api_key:
        raise SystemExit("K2_API_KEY or K2_DEV_TOKEN is required.")

    provisioner = K2WorkspaceProvisioner(
        client=K2RestClient(api_key=api_key, base_url=args.base_url),
        project_name=args.project_name,
        summary_path=args.summary_path,
    )
    try:
        result = provisioner.ensure_workspace(
            apply_uploads=args.apply_uploads,
            apply_indexes=args.apply_indexes,
            apply_primitives=args.apply_primitives,
            batch_size=args.batch_size,
        )
        if args.health_check:
            result["health"] = provisioner.health_check(result["corpora"])
            provisioner._write_summary(result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except K2ApiError as exc:
        print(json.dumps({"status": "error", "status_code": exc.status_code, "body": exc.body}, indent=2), file=sys.stderr)
        return 1


def _with_metadata(
    document: dict[str, Any],
    *,
    entity_type: str,
    k2_settings: K2Settings | None = None,
) -> dict[str, Any]:
    settings = k2_settings or K2Settings()
    metadata = dict(document.get("metadata", {}) if isinstance(document.get("metadata"), dict) else {})
    metadata["entity_type"] = entity_type
    metadata.setdefault("workspace", settings.workspace_namespace)
    return {**document, "metadata": metadata}


def _criteria_documents(
    run: dict[str, Any],
    *,
    k2_settings: K2Settings | None = None,
) -> list[dict[str, Any]]:
    settings = k2_settings or K2Settings()
    criteria_hash = str(run.get("criteria", {}).get("hash") or "seeded-icp-v1")
    base_metadata = {
        "run_id": run.get("id"),
        "criteria_hash": criteria_hash,
        "criteria_version": criteria_hash,
        "entity_type": "criteria",
        "workspace": settings.workspace_namespace,
        "source_type": "seed",
    }
    prompt_docs = [
        {
            "sourceUri": f"{settings.source_uri_prefix}/criteria/prompts/{prompt['id']}",
            "rawText": f"{prompt['label']} ({prompt['kind']}): {prompt['text']}",
            "metadata": {
                **base_metadata,
                "label_source": "prompt",
                "prompt_id": prompt["id"],
                "prompt_kind": prompt["kind"],
            },
        }
        for prompt in SEEDED_PROMPTS
    ]
    return [
        {
            "sourceUri": f"{settings.source_uri_prefix}/criteria/seeded-markdown",
            "rawText": SEEDED_CRITERIA_MARKDOWN,
            "metadata": {**base_metadata, "label_source": "criteria_markdown"},
        },
        *prompt_docs,
        {
            "sourceUri": f"{settings.source_uri_prefix}/criteria/settings",
            "rawText": json.dumps(SEEDED_SETTINGS, indent=2, sort_keys=True),
            "metadata": {**base_metadata, "label_source": "settings"},
        },
        {
            "sourceUri": f"{settings.source_uri_prefix}/criteria/lists",
            "rawText": json.dumps(
                {
                    "priority_verticals": SEEDED_LISTS["priority_verticals"],
                    "account_count": len(SEEDED_LISTS["account_universe"]),
                    "sample_accounts": SEEDED_LISTS["account_universe"][:25],
                },
                indent=2,
                sort_keys=True,
            ),
            "metadata": {
                **base_metadata,
                "label_source": "lists",
                "account_count": len(SEEDED_LISTS["account_universe"]),
            },
        },
    ]


def _unique_source_uris(
    documents: list[dict[str, Any]],
    corpus_key: str,
    *,
    k2_settings: K2Settings | None = None,
) -> list[dict[str, Any]]:
    settings = k2_settings or K2Settings()
    unique = []
    for index, document in enumerate(documents):
        source_uri = str(document.get("sourceUri") or document.get("source_uri") or f"{settings.source_uri_prefix}/{corpus_key}/{index}")
        base, separator, fragment = source_uri.partition("#")
        joiner = "&" if "?" in base else "?"
        source_uri = f"{base}{joiner}k2_seq={index:05d}"
        if separator:
            source_uri = f"{source_uri}#{fragment}"
        unique.append({**document, "sourceUri": source_uri})
    return unique


def _id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("job_id") or payload.get("jobId") or payload.get("corpusId") or "")


def _search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    responses = payload.get("responses")
    if isinstance(responses, list) and responses:
        results = responses[0].get("results") if isinstance(responses[0], dict) else []
        return [item for item in (results or []) if isinstance(item, dict)]
    results = payload.get("results")
    return [item for item in (results or []) if isinstance(item, dict)] if isinstance(results, list) else []


def _search_warnings(payload: dict[str, Any]) -> list[str]:
    responses = payload.get("responses")
    if not isinstance(responses, list) or not responses or not isinstance(responses[0], dict):
        return []
    meta = responses[0].get("meta")
    warnings = meta.get("warnings") if isinstance(meta, dict) else []
    return [str(item) for item in (warnings or [])]


def _result_snippet(item: dict[str, Any]) -> str:
    document = item.get("document") if isinstance(item.get("document"), dict) else {}
    chunk = item.get("chunk") if isinstance(item.get("chunk"), dict) else {}
    text = str(item.get("text") or document.get("text") or chunk.get("text") or "")
    return text[:220].replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
