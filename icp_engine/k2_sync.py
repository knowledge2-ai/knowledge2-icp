from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .app_store import AppStore
from .k2_backend import K2Backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync an ICP research run manifest to Knowledge2")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-id", help="Run ID stored in the local app state")
    source.add_argument("--manifest", type=Path, help="Path to a K2 manifest JSON file")
    parser.add_argument("--state-dir", type=Path, default=Path("out/app_state"))
    parser.add_argument("--project-name", default="Knowledge2 ICP GTM")
    parser.add_argument("--corpus-name", default=None)
    parser.add_argument("--description", default="Agentic GTM lead research evidence and metadata.")
    parser.add_argument("--apply", action="store_true", help="Actually upload documents to K2. Default is dry-run.")
    args = parser.parse_args(argv)

    run = _load_run(args)
    backend = K2Backend()
    result = backend.sync_manifest(
        run,
        project_name=args.project_name,
        corpus_name=args.corpus_name,
        description=args.description,
        apply=args.apply,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") not in {"error"} else 1


def _load_run(args: argparse.Namespace) -> dict[str, object]:
    if args.run_id:
        run = AppStore(args.state_dir).load_run(args.run_id)
        if not run:
            raise SystemExit(f"Run not found: {args.run_id}")
        return run

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = payload.get("documents", [])
    return {
        "id": payload.get("run_id") or args.manifest.stem,
        "query": payload.get("query", ""),
        "criteria": {},
        "leads": _leads_from_manifest_documents(documents if isinstance(documents, list) else []),
    }


def _leads_from_manifest_documents(documents: list[object]) -> list[dict[str, object]]:
    leads: dict[str, dict[str, object]] = {}
    for item in documents:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        domain = str(metadata.get("domain") or "unknown")
        lead = leads.setdefault(
            domain,
            {
                "score": {
                    "company": {
                        "company": metadata.get("company") or domain,
                        "domain": domain,
                    },
                    "tier": metadata.get("tier"),
                    "total_score": metadata.get("total_score"),
                    "classification": {"ai_posture": metadata.get("ai_posture")},
                },
                "strategy": {
                    "personas": [{"title": title} for title in metadata.get("persona_titles", [])]
                    if isinstance(metadata.get("persona_titles"), list)
                    else [],
                    "outreach_angle": metadata.get("outreach_angle"),
                },
                "metadata": {"signal_tags": metadata.get("signal_tags", [])},
                "evidence": [],
            },
        )
        if metadata.get("evidence_id") != "account-summary":
            lead["evidence"].append(
                {
                    "evidence_id": metadata.get("evidence_id"),
                    "url": metadata.get("source_url"),
                    "title": metadata.get("source_title"),
                    "text": item.get("text", ""),
                    "source_type": metadata.get("source_type"),
                    "metadata": metadata,
                }
            )
    return list(leads.values())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
