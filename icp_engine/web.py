from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .app_store import AppStore
from .claude import ClaudeUnavailable, suggest_criteria
from .k2_client import K2ApiError, SEARCH_BATCH_MAX_TOP_K
from .k2_workspace_status import build_k2_workspace_status, run_k2_pipeline_action
from .mining import mining_to_csv
from .outreach import summarize_outreach_drafts
from .prospects import build_run_prospects, prospects_to_csv
from .research import ResearchPipeline


ASSET_DIR = Path(__file__).with_name("web_assets")
APP_VERSION = "0.1.0"
API_SESSION_TTL_SECONDS = 8 * 60 * 60


class GTMApp:
    def __init__(
        self,
        store: AppStore | None = None,
        pipeline: ResearchPipeline | None = None,
        admin_token: str | None = None,
    ) -> None:
        self.store = store or AppStore()
        self.pipeline = pipeline or ResearchPipeline(self.store)
        self.admin_token = (admin_token if admin_token is not None else os.environ.get("ICP_ADMIN_TOKEN", "")).strip()


def make_handler(app: GTMApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Knowledge2ICPWeb/0.1"

        def do_HEAD(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_asset_headers("index.html")
                return
            if parsed.path == "/healthz":
                self._send_json_headers()
                return
            if parsed.path.startswith("/assets/"):
                self._send_asset_headers(parsed.path.removeprefix("/assets/"))
                return
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_asset("index.html")
                return
            if parsed.path.startswith("/assets/"):
                self._send_asset(parsed.path.removeprefix("/assets/"))
                return
            if parsed.path == "/healthz":
                self._send_json(_health_payload(app, detailed=False))
                return
            if parsed.path.startswith("/api/") and not self._authorize_api():
                self._send_unauthorized()
                return
            if parsed.path == "/api/health":
                self._send_json(_health_payload(app, detailed=True))
                return
            if parsed.path == "/api/state":
                self._send_json(app.store.state())
                return
            if parsed.path == "/api/workspace-state":
                self._send_json(app.store.workspace_state_status())
                return
            if parsed.path == "/api/settings":
                self._send_json({"settings": app.store.load_settings()})
                return
            if parsed.path == "/api/criteria/versions":
                self._send_json({"versions": app.store.list_criteria_versions(), "current_hash": app.store.load_criteria().get("hash")})
                return
            if parsed.path == "/api/lead-views":
                self._send_json({"views": app.store.list_lead_views()})
                return
            if parsed.path == "/api/sources":
                self._send_json(
                    {
                        "sources": app.store.load_sources(),
                        "scans": app.store.list_source_scans(limit=50),
                        "expansion_runs": app.store.list_expansion_runs(limit=25),
                        "coverage": app.store.source_coverage(),
                    }
                )
                return
            if parsed.path == "/api/expansion/runs":
                self._send_json({"runs": app.store.list_expansion_runs(limit=100), "coverage": app.store.source_coverage()})
                return
            if parsed.path == "/api/audit-log":
                self._send_json({"events": app.store.list_audit_events(limit=100)})
                return
            if parsed.path == "/api/evals/cases":
                self._send_json({"cases": app.store.list_eval_cases()})
                return
            if parsed.path == "/api/evals/runs.csv":
                self._send_text(
                    app.store.eval_runs_csv(),
                    content_type="text/csv; charset=utf-8",
                    filename="icp-eval-runs.csv",
                )
                return
            if parsed.path == "/api/evals/runs":
                self._send_json({"runs": app.store.list_eval_runs(limit=100), "summary": app.store.eval_summary()})
                return
            if parsed.path == "/api/evals/summary":
                self._send_json(app.store.eval_summary())
                return
            if parsed.path == "/api/k2-workspace":
                self._send_json(build_k2_workspace_status())
                return
            if parsed.path == "/api/mining/profiles":
                self._send_json({"profiles": app.store.list_query_profiles()})
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/workflow"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(
                    {
                        "run_id": run_id,
                        "lead_statuses": run.get("workflow", {}).get("lead_statuses", []),
                        "status_counts": run.get("workflow", {}).get("status_counts", {}),
                        "lead_states": list(app.store.load_lead_states(run_id).values()),
                        "saved_views": app.store.list_lead_views(),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-manifest"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(app.pipeline.k2.build_manifest(run))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/prospects"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(build_run_prospects(run))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/prospects.csv"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_text(
                    prospects_to_csv(build_run_prospects(run)),
                    content_type="text/csv; charset=utf-8",
                    filename=f"{run_id}-prospects.csv",
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/quality-feedback.csv"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_text(
                    app.store.quality_feedback_csv(run_id=run_id),
                    content_type="text/csv; charset=utf-8",
                    filename=f"{run_id}-quality-feedback.csv",
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/quality-feedback"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(
                    {
                        "run_id": run_id,
                        "feedback": app.store.list_quality_feedback(run_id=run_id, limit=200),
                        "summary": app.store.quality_feedback_summary(run_id=run_id),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/outreach-drafts.csv"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_text(
                    app.store.outreach_drafts_csv(run_id=run_id),
                    content_type="text/csv; charset=utf-8",
                    filename=f"{run_id}-outreach-drafts.csv",
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/outreach-drafts"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                drafts = app.store.list_outreach_drafts(run_id=run_id)
                self._send_json(
                    {
                        "run_id": run_id,
                        "drafts": drafts,
                        "summary": app.store.outreach_summary(run_id=run_id),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and "/accounts/" in parsed.path:
                parts = parsed.path.split("/")
                if len(parts) >= 6:
                    run_id = parts[3]
                    account_key = unquote(parts[5])
                    detail = app.store.account_detail(run_id, account_key)
                    if not detail:
                        self._send_json({"error": "Account not found."}, status=HTTPStatus.NOT_FOUND)
                        return
                    self._send_json(detail)
                    return
            if parsed.path.startswith("/api/runs/"):
                run_id = parsed.path.rsplit("/", 1)[-1]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(run)
                return
            self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/auth/session":
                self._send_auth_session()
                return
            if parsed.path.startswith("/api/") and not self._authorize_api():
                self._send_unauthorized()
                return
            if parsed.path == "/api/criteria":
                payload = self._read_json()
                markdown = str(payload.get("markdown", ""))
                if not markdown.strip():
                    self._send_json({"error": "Criteria markdown is required."}, status=HTTPStatus.BAD_REQUEST)
                    return
                criteria = app.store.save_criteria(markdown)
                self._send_json({"criteria": criteria, "versions": app.store.list_criteria_versions(), "lint": app.store.lint_criteria(criteria["markdown"])})
                return
            if parsed.path == "/api/criteria/lint":
                payload = self._read_json()
                self._send_json(app.store.lint_criteria(str(payload.get("markdown", ""))))
                return
            if parsed.path == "/api/criteria/impact":
                payload = self._read_json()
                try:
                    impact = app.store.criteria_impact(str(payload.get("run_id") or ""), str(payload.get("markdown") or ""))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(impact)
                return
            if parsed.path == "/api/criteria/suggest":
                guard = app.store.authorize_provider_action("criteria_suggest")
                if not guard.get("allowed", True):
                    self._send_provider_denied(guard)
                    return
                payload = self._read_json()
                current = str(payload.get("markdown") or "") or str(app.store.load_criteria().get("markdown", ""))
                run_ids = payload.get("run_ids") if isinstance(payload.get("run_ids"), list) else None
                sample_runs = _sample_runs_for_suggestion(app.store, run_ids)
                try:
                    proposal = suggest_criteria(current, sample_runs)
                except ClaudeUnavailable as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                self._send_json({"proposal": proposal, "current_hash": app.store.load_criteria().get("hash")})
                return
            if parsed.path == "/api/criteria/restore":
                payload = self._read_json()
                criteria = app.store.restore_criteria_version(str(payload.get("id") or payload.get("hash") or ""))
                if not criteria:
                    self._send_json({"error": "Criteria version not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"criteria": criteria, "versions": app.store.list_criteria_versions(), "lint": app.store.lint_criteria(criteria["markdown"])})
                return
            if parsed.path == "/api/settings":
                payload = self._read_json()
                try:
                    settings = app.store.save_settings(payload)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"settings": settings, "provider_controls": app.store.provider_usage_summary()})
                return
            if parsed.path == "/api/lead-views":
                payload = self._read_json()
                try:
                    view = app.store.save_lead_view(
                        str(payload.get("name") or ""),
                        filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
                        sort=payload.get("sort") if isinstance(payload.get("sort"), dict) else None,
                        page_size=int(payload.get("page_size") or 50),
                    )
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"view": view, "views": app.store.list_lead_views()})
                return
            if parsed.path == "/api/sources":
                payload = self._read_json()
                try:
                    source = app.store.save_source(
                        str(payload.get("name") or ""),
                        source_type=str(payload.get("type") or "serp_query"),
                        value=str(payload.get("value") or ""),
                        source_group=str(payload.get("source_group") or ""),
                        schedule=str(payload.get("schedule") or "manual"),
                        enabled=bool(payload.get("enabled", True)),
                        source_id=str(payload.get("id") or "") or None,
                    )
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"source": source, "sources": app.store.load_sources(), "coverage": app.store.source_coverage()})
                return
            if parsed.path == "/api/expansion/run":
                payload = self._read_json()
                due_only = bool(payload.get("due_only", True))
                max_companies = max(1, min(int(payload.get("max_companies") or 25), 100))
                sources = app.store.expansion_sources_due() if due_only else [
                    item for item in app.store.load_sources() if item.get("enabled", True) and item.get("schedule") != "manual"
                ]
                results: list[dict[str, Any]] = []
                warnings: list[str] = []
                for source in sources:
                    guard = app.store.authorize_provider_action(
                        "source_scan",
                        details={
                            "source_id": source.get("id"),
                            "source_type": source.get("type"),
                            "max_companies": max_companies,
                            "trigger": "expansion",
                        },
                    )
                    if not guard["allowed"]:
                        results.append(
                            {
                                "source_id": source.get("id"),
                                "source_name": source.get("name"),
                                "status": "skipped",
                                "candidate_count": 0,
                                "warning_count": 1,
                                "reason": guard.get("reason") or "Provider budget denied.",
                            }
                        )
                        continue
                    try:
                        candidates, source_warnings = app.pipeline.scan_source(source, max_companies=max_companies)
                        candidate_payloads = _candidate_payloads(candidates)
                        scan = app.store.record_source_scan(
                            str(source.get("id") or ""),
                            status="completed" if candidate_payloads else "empty",
                            candidates=candidate_payloads,
                            warnings=source_warnings,
                        )
                        results.append(
                            {
                                "source_id": source.get("id"),
                                "source_name": source.get("name"),
                                "status": scan["status"],
                                "scan_id": scan["id"],
                                "candidate_count": scan["candidate_count"],
                                "warning_count": scan["warning_count"],
                            }
                        )
                    except Exception as exc:
                        results.append(
                            {
                                "source_id": source.get("id"),
                                "source_name": source.get("name"),
                                "status": "failed",
                                "candidate_count": 0,
                                "warning_count": 1,
                                "reason": str(exc),
                            }
                        )
                status = "completed" if results and not any(item.get("status") == "failed" for item in results) else "failed" if results else "empty"
                run = app.store.record_expansion_run(
                    trigger="manual_due" if due_only else "manual_all_scheduled",
                    status=status,
                    source_results=results,
                    warnings=warnings,
                )
                self._send_json(
                    {
                        "run": run,
                        "sources": app.store.load_sources(),
                        "scans": app.store.list_source_scans(limit=50),
                        "expansion_runs": app.store.list_expansion_runs(limit=25),
                        "coverage": app.store.source_coverage(),
                    }
                )
                return
            if parsed.path.startswith("/api/sources/") and parsed.path.endswith("/scan"):
                source_id = parsed.path.split("/")[3]
                source = next((item for item in app.store.load_sources() if item.get("id") == source_id), None)
                if not source:
                    self._send_json({"error": "Source not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                max_companies = int(payload.get("max_companies") or 25)
                guard = app.store.authorize_provider_action(
                    "source_scan",
                    details={
                        "source_id": source_id,
                        "source_type": source.get("type"),
                        "max_companies": max_companies,
                    },
                )
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                candidates, warnings = app.pipeline.scan_source(source, max_companies=max_companies)
                candidate_payloads = _candidate_payloads(candidates)
                try:
                    scan = app.store.record_source_scan(
                        source_id,
                        status="completed" if candidate_payloads else "empty",
                        candidates=candidate_payloads,
                        warnings=warnings,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                updated_source = next((item for item in app.store.load_sources() if item.get("id") == source_id), source)
                self._send_json(
                    {
                        "source": updated_source,
                        "scan": scan,
                        "candidates": candidate_payloads,
                        "warnings": warnings,
                        "coverage": app.store.source_coverage(),
                    }
                )
                return
            if parsed.path == "/api/search":
                payload = self._read_json()
                max_companies = int(payload.get("max_companies") or 10)
                guard = app.store.authorize_provider_action(
                    "search",
                    details={"max_companies": max_companies},
                )
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                if _discovery_provider_is_metered(app.store) and str(payload.get("query", "")).strip():
                    discovery_guard = app.store.authorize_provider_action(
                        "discovery",
                        details={"max_companies": max_companies, "source": "search"},
                    )
                    if not discovery_guard["allowed"]:
                        self._send_provider_denied(discovery_guard)
                        return
                candidates, warnings, _ = app.pipeline.discover(
                    str(payload.get("query", "")),
                    seed_text=str(payload.get("seed_text", "")),
                    max_companies=max_companies,
                )
                self._send_json(
                    {
                        "candidates": _candidate_payloads(candidates),
                        "warnings": warnings,
                    }
                )
                return
            if parsed.path == "/api/runs":
                payload = self._read_json()
                candidate_payloads = payload.get("candidates")
                max_companies = int(payload.get("max_companies") or 8)
                max_pages = int(payload.get("max_pages") or 8)
                guard = app.store.authorize_provider_action(
                    "run",
                    details={
                        "max_companies": max_companies,
                        "max_pages": max_pages,
                        "use_apollo": bool(payload.get("use_apollo", False)),
                    },
                )
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                if not isinstance(candidate_payloads, list) and str(payload.get("query", "")).strip():
                    search_guard = app.store.authorize_provider_action(
                        "search",
                        details={"max_companies": max_companies, "source": "run"},
                    )
                    if not search_guard["allowed"]:
                        self._send_provider_denied(search_guard)
                        return
                    if _discovery_provider_is_metered(app.store):
                        discovery_guard = app.store.authorize_provider_action(
                            "discovery",
                            details={"max_companies": max_companies, "source": "run"},
                        )
                        if not discovery_guard["allowed"]:
                            self._send_provider_denied(discovery_guard)
                            return
                if bool(payload.get("use_apollo", False)):
                    apollo_guard = app.store.authorize_provider_action(
                        "apollo_enrichment",
                        amount=max_companies,
                        details={"max_companies": max_companies},
                    )
                    if not apollo_guard["allowed"]:
                        self._send_provider_denied(apollo_guard)
                        return
                if _outreach_mode_is_claude(app.store):
                    outreach_guard = app.store.authorize_provider_action(
                        "outreach",
                        amount=max_companies,
                        details={"max_companies": max_companies, "source": "run"},
                    )
                    if not outreach_guard["allowed"]:
                        self._send_provider_denied(outreach_guard)
                        return
                try:
                    run = app.pipeline.create_run(
                        query=str(payload.get("query", "")),
                        seed_text=str(payload.get("seed_text", "")),
                        candidate_payloads=candidate_payloads if isinstance(candidate_payloads, list) else None,
                        max_companies=max_companies,
                        fetch=bool(payload.get("fetch", True)),
                        max_pages=max_pages,
                        include_github=bool(payload.get("include_github", True)),
                        use_apollo=bool(payload.get("use_apollo", False)),
                    )
                except Exception as exc:
                    self._send_json({"error": f"Run failed: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(run)
                return
            if parsed.path == "/api/research":
                payload = self._read_json()
                guard = app.store.authorize_provider_action(
                    "research",
                    details={"run_id": str(payload.get("run_id", ""))},
                )
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                answer = app.pipeline.answer_question(
                    run_id=str(payload.get("run_id", "")),
                    question=str(payload.get("question", "")),
                )
                self._send_json(answer)
                return
            if parsed.path in ("/api/mining/search", "/api/mining/search.csv"):
                payload = self._read_json()
                guard = app.store.authorize_provider_action("mining", details={"mode": "search"})
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                try:
                    result = app.pipeline.k2.mine_corpus(
                        query=_mining_query(payload),
                        filters=payload.get("filters"),
                        corpus_key=_mining_corpus_key(app.store, payload),
                        top_k=_mining_top_k(payload),
                        store=app.store,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                if parsed.path.endswith(".csv"):
                    self._send_text(
                        mining_to_csv(result),
                        content_type="text/csv; charset=utf-8",
                        filename="corpus-mining.csv",
                    )
                    return
                self._send_json(result)
                return
            if parsed.path == "/api/mining/lookalikes":
                payload = self._read_json()
                guard = app.store.authorize_provider_action("mining", details={"mode": "lookalikes"})
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                result = app.pipeline.k2.find_lookalikes(
                    seed_domains=_seed_domains(payload),
                    corpus_key=_mining_corpus_key(app.store, payload),
                    top_k=_mining_top_k(payload),
                    store=app.store,
                )
                self._send_json(result)
                return
            if parsed.path == "/api/mining/profiles":
                payload = self._read_json()
                if str(payload.get("action") or "save") == "delete":
                    try:
                        app.store.delete_query_profile(str(payload.get("id") or ""))
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                        return
                    self._send_json({"profiles": app.store.list_query_profiles()})
                    return
                try:
                    profile = app.store.save_query_profile(payload)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"profile": profile, "profiles": app.store.list_query_profiles()})
                return
            if parsed.path == "/api/evals/cases":
                payload = self._read_json()
                try:
                    case = app.store.save_eval_case(payload)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"case": case, "cases": app.store.list_eval_cases()})
                return
            if parsed.path == "/api/evals/runs":
                payload = self._read_json()
                run_id = str(payload.get("run_id") or "")
                case_ids = payload.get("case_ids") if isinstance(payload.get("case_ids"), list) else None
                try:
                    result = app.store.run_eval(run_id, case_ids=[str(item) for item in case_ids] if case_ids else None)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"eval_run": result, "summary": app.store.eval_summary(run_id=run_id)})
                return
            if parsed.path == "/api/k2-workspace/pipeline":
                payload = self._read_json()
                try:
                    result = run_k2_pipeline_action(
                        str(payload.get("action") or ""),
                        sample_input=payload.get("sample_input") if isinstance(payload.get("sample_input"), dict) else None,
                        activate_entities=bool(payload.get("activate_entities", True)),
                        start_from=str(payload.get("start_from") or "") or None,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                except K2ApiError as exc:
                    body = {"error": str(exc)}
                    if exc.body:
                        body["detail"] = exc.body[:1000]
                    self._send_json(body, status=_http_status_from_k2_error(exc))
                    return
                self._send_json(result)
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/lead-state"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                try:
                    record = app.store.save_lead_state(
                        run_id,
                        str(payload.get("domain") or ""),
                        company=str(payload.get("company") or ""),
                        status=str(payload.get("status") or "Review"),
                        note=str(payload.get("note") or ""),
                        owner=str(payload.get("owner") or ""),
                        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else None,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(
                    {
                        "lead_state": record,
                        "status_counts": app.store.lead_status_counts(run_id, run),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/quality-feedback"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                try:
                    record = app.store.save_quality_feedback(
                        run_id,
                        str(payload.get("domain") or ""),
                        company=str(payload.get("company") or ""),
                        dimension=str(payload.get("dimension") or "score"),
                        rating=str(payload.get("rating") or "positive"),
                        note=str(payload.get("note") or ""),
                        target_id=str(payload.get("target_id") or ""),
                        target_label=str(payload.get("target_label") or ""),
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(
                    {
                        "feedback": record,
                        "summary": app.store.quality_feedback_summary(run_id=run_id),
                        "account_summary": app.store.quality_feedback_summary(run_id=run_id, domain=record["domain"]),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/outreach-drafts/status"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                try:
                    record = app.store.save_outreach_status(
                        run_id,
                        str(payload.get("prospect_id") or ""),
                        domain=str(payload.get("domain") or ""),
                        company=str(payload.get("company") or ""),
                        status=str(payload.get("status") or "Approved"),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(
                    {
                        "outreach_status": record,
                        "summary": app.store.outreach_summary(run_id=run_id),
                        "account_summary": summarize_outreach_drafts(app.store.list_outreach_drafts(run_id=run_id, domain=record["domain"])),
                    }
                )
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/lead-state/bulk"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                domains = payload.get("domains")
                if not isinstance(domains, list):
                    self._send_json({"error": "domains must be a list."}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    result = app.store.bulk_update_lead_states(
                        run_id,
                        [str(domain) for domain in domains],
                        status=str(payload.get("status") or "Review"),
                        note=str(payload.get("note") or ""),
                        owner=str(payload.get("owner") or ""),
                        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else None,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(result)
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-export"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                out_path = app.store.state_dir / "k2_manifests" / f"{run_id}.json"
                self._send_json(app.pipeline.k2.export_manifest(run, out_path))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-sync"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                action_name = "k2_apply" if bool(payload.get("apply", False)) else "k2_dry_run"
                guard = app.store.authorize_provider_action(
                    action_name,
                    details={"run_id": run_id, "apply": bool(payload.get("apply", False))},
                )
                if not guard["allowed"]:
                    self._send_provider_denied(guard)
                    return
                result = app.pipeline.k2.sync_manifest(
                    run,
                    project_name=str(payload.get("project_name") or "Knowledge2 ICP GTM"),
                    corpus_name=str(payload.get("corpus_name") or f"ICP Run {run_id}"),
                    apply=bool(payload.get("apply", False)),
                )
                if result.get("status") == "uploaded":
                    run["k2"] = result
                    app.store.save_run(run)
                status = HTTPStatus.BAD_REQUEST if result.get("status") == "error" else HTTPStatus.OK
                self._send_json(result, status=status)
                return
            self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_asset(self, name: str) -> None:
            path = self._asset_path(name)
            if not path.exists() or not path.is_file():
                self._send_json({"error": "Asset not found."}, status=HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_asset_headers(self, name: str) -> None:
            path = self._asset_path(name)
            if not path.exists() or not path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()

        def _send_json_headers(self, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _asset_path(self, name: str) -> Path:
            return ASSET_DIR / Path(name).name

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorize_api(self) -> bool:
            if not app.admin_token:
                return True
            auth_header = self.headers.get("Authorization", "")
            scheme, _, token = auth_header.partition(" ")
            if scheme.lower() != "bearer" or not token:
                return False
            presented = token.strip()
            return hmac.compare_digest(presented, app.admin_token) or _verify_session_token(app.admin_token, presented)

        def _send_auth_session(self) -> None:
            if not app.admin_token:
                self._send_json({"error": "ICP_ADMIN_TOKEN is required for API access."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            payload = self._read_json()
            auth_header = self.headers.get("Authorization", "")
            scheme, _, bearer = auth_header.partition(" ")
            token = str(payload.get("token") or (bearer if scheme.lower() == "bearer" else "")).strip()
            if not hmac.compare_digest(token, app.admin_token):
                self._send_unauthorized()
                return
            now = int(time.time())
            self._send_json(
                {
                    "session_token": _create_session_token(app.admin_token, now),
                    "expires_at": _iso_from_epoch(now + API_SESSION_TTL_SECONDS),
                    "expires_in_seconds": API_SESSION_TTL_SECONDS,
                }
            )

        def _send_unauthorized(self) -> None:
            body = json.dumps({"error": "Admin token required."}, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("WWW-Authenticate", 'Bearer realm="knowledge2-icp"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_provider_denied(self, guard: dict[str, Any]) -> None:
            self._send_json(
                {
                    "error": guard.get("reason") or "Provider action denied by budget policy.",
                    "provider_control": guard,
                },
                status=HTTPStatus.TOO_MANY_REQUESTS,
            )

        def _send_text(
            self,
            payload: str,
            *,
            content_type: str = "text/plain; charset=utf-8",
            status: HTTPStatus = HTTPStatus.OK,
            filename: str | None = None,
        ) -> None:
            body = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            body = self.rfile.read(min(length, 5_000_000))
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

    return Handler


def _health_payload(app: GTMApp, *, detailed: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "service": "knowledge2-icp",
        "version": APP_VERSION,
        "auth_required": bool(app.admin_token),
    }
    if detailed:
        app.store.ensure()
        payload.update(
            {
                "state_dir": str(app.store.state_dir),
                "state_dir_writable": os.access(app.store.state_dir, os.W_OK),
                "run_count": len(app.store.list_runs()),
                "provider_status": app.store.state().get("provider_status", {}),
                "provider_controls": app.store.provider_usage_summary(),
            }
        )
    return payload


def _http_status_from_k2_error(exc: K2ApiError) -> HTTPStatus:
    try:
        return HTTPStatus(exc.status_code or HTTPStatus.BAD_GATEWAY)
    except ValueError:
        return HTTPStatus.BAD_GATEWAY


def _create_session_token(secret: str, now: int) -> str:
    payload = {
        "exp": now + API_SESSION_TTL_SECONDS,
        "iat": now,
        "nonce": secrets.token_urlsafe(16),
    }
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _session_signature(secret, payload_b64)
    return f"{payload_b64}.{_base64url_encode(signature)}"


def _verify_session_token(secret: str, token: str) -> bool:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        if "." in signature_b64:
            return False
        expected = _base64url_encode(_session_signature(secret, payload_b64))
        if not hmac.compare_digest(signature_b64, expected):
            return False
        payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    exp = payload.get("exp")
    return isinstance(exp, int | float) and exp > time.time()


def _session_signature(secret: str, payload_b64: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _iso_from_epoch(epoch_seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


def _sample_runs_for_suggestion(store: AppStore, run_ids: list[Any] | None) -> list[dict[str, Any]]:
    if run_ids:
        runs = [store.load_run(str(run_id)) for run_id in run_ids[:5]]
        return [run for run in runs if isinstance(run, dict)]
    recent = store.list_runs()[:3]
    runs = [store.load_run(str(item.get("id"))) for item in recent if isinstance(item, dict) and item.get("id")]
    return [run for run in runs if isinstance(run, dict)]


def _discovery_provider_is_metered(store: AppStore) -> bool:
    """True when the configured discovery provider hits the paid research API.

    Perplexity is the only metered research provider; the Serper/DuckDuckGo fallback
    is already covered by the ``search`` action budget. ``auto`` only reaches
    Perplexity when a key is set.
    """
    provider = str(store.load_settings().get("discovery_provider") or "auto").strip().lower()
    if provider == "perplexity":
        return True
    if provider == "auto":
        return bool(os.environ.get("PERPLEXITY_API_KEY"))
    return False


def _outreach_mode_is_claude(store: AppStore) -> bool:
    """True when outreach is set to Claude personalization (the metered path).

    The ``template`` default is deterministic and free; only ``claude`` calls the
    paid model, so only it draws against the ``outreach`` budget.
    """
    return str(store.load_settings().get("outreach_mode") or "template").strip().lower() == "claude"


_MINING_CORPUS_KEYS = {"candidate", "evidence", "prospect", "source", "criteria"}


def _mining_corpus_key(store: AppStore, payload: dict[str, Any]) -> str:
    """Resolve the corpus to mine: explicit request wins, else the ``mining_corpus`` setting.

    ``auto`` (the default, on both the request and the setting) maps to the candidate
    corpus — the run/lead index the growth loop fills.
    """
    requested = str(payload.get("corpus") or "").strip().lower()
    if requested in _MINING_CORPUS_KEYS:
        return requested
    setting = str(store.load_settings().get("mining_corpus") or "auto").strip().lower()
    return setting if setting in _MINING_CORPUS_KEYS else "candidate"


def _mining_top_k(payload: dict[str, Any]) -> int:
    try:
        requested = int(payload.get("top_k") or 20)
    except (TypeError, ValueError):
        requested = 20
    # Cap at the live /search:batch ceiling so the surface never promises more
    # results than the K2 path can actually return.
    return max(1, min(requested, SEARCH_BATCH_MAX_TOP_K))


_MINING_QUERY_MAX_CHARS = 1000
_MINING_SEEDS_MAX = 50


def _mining_query(payload: dict[str, Any]) -> str:
    return str(payload.get("query", ""))[:_MINING_QUERY_MAX_CHARS]


def _seed_domains(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("seed_domains")
    if isinstance(raw, list):
        seeds = [str(item).strip() for item in raw if str(item).strip()]
    else:
        seeds = [part.strip() for part in str(raw or "").replace("\n", ",").split(",") if part.strip()]
    return seeds[:_MINING_SEEDS_MAX]


def _candidate_payloads(candidates: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "company": item.company,
            "domain": item.domain,
            "source_url": item.source_url,
            "source_title": item.source_title,
            "notes": item.notes,
            "github_urls": item.github_urls,
            "linkedin_urls": item.linkedin_urls,
            "other_urls": item.other_urls,
        }
        for item in candidates
    ]


def run_server(
    host: str,
    port: int,
    store_dir: Path | None = None,
    admin_token: str | None = None,
    *,
    allow_open_api: bool | None = None,
) -> ThreadingHTTPServer:
    token = (admin_token if admin_token is not None else os.environ.get("ICP_ADMIN_TOKEN", "")).strip()
    if not token and not _open_api_allowed(host, allow_open_api):
        raise ValueError("ICP_ADMIN_TOKEN is required when binding the API to a non-loopback host.")
    store = AppStore(state_dir=store_dir) if store_dir else AppStore()
    app = GTMApp(store=store, admin_token=token)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Knowledge2 ICP web app running at http://{host}:{port}")
    server.serve_forever()
    return server


def _open_api_allowed(host: str, allow_open_api: bool | None = None) -> bool:
    if allow_open_api is None:
        allow_open_api = os.environ.get("ICP_ALLOW_OPEN_API", "").strip().lower() in {"1", "true", "yes"}
    return allow_open_api or _is_loopback_bind_host(host)


def _is_loopback_bind_host(host: str) -> bool:
    if host.lower() in {"localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Knowledge2 Agentic GTM dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--admin-token", default=None, help="Optional bearer token for /api/* routes. Defaults to ICP_ADMIN_TOKEN.")
    parser.add_argument(
        "--allow-open-api",
        action="store_true",
        default=None,
        help="Allow unauthenticated /api/* routes on non-loopback hosts. Intended only for isolated local networks.",
    )
    args = parser.parse_args(argv)
    run_server(args.host, args.port, args.state_dir, admin_token=args.admin_token, allow_open_api=args.allow_open_api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
