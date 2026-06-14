"""Sources cluster: source CRUD, scans, scheduled expansion runs, and coverage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ._helpers import (
    _candidate_preview_record,
    _count_by_key,
    _default_sources,
    _load_json_file,
    _normalize_source_record,
    _normalize_source_schedule,
    _normalize_source_type,
    _source_group_for_type,
    _source_schedule_due,
    now_iso,
    stable_hash,
)


class SourcesMixin:
    def load_sources(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.sources_path, list)
        sources = value if value is not None else _default_sources()
        return [_normalize_source_record(item) for item in sources if isinstance(item, dict) and item.get("name")]

    def save_source(
        self,
        name: str,
        *,
        source_type: str,
        value: str,
        source_group: str = "",
        schedule: str = "",
        enabled: bool = True,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_name = " ".join(name.strip().split())
        clean_value = value.strip()
        clean_type = _normalize_source_type(source_type)
        if not clean_name:
            raise ValueError("Source name is required.")
        if not clean_value:
            raise ValueError("Source value is required.")
        now = now_iso()
        sources = self.load_sources()
        record_id = source_id or stable_hash(f"{clean_type}:{clean_name.lower()}:{clean_value.lower()}")
        previous = next((item for item in sources if item.get("id") == record_id), {})
        record = {
            "id": record_id,
            "name": clean_name,
            "type": clean_type,
            "value": clean_value,
            "source_group": " ".join(source_group.strip().split()) or _source_group_for_type(clean_type),
            "schedule": _normalize_source_schedule(schedule),
            "enabled": bool(enabled),
            "created_at": str(previous.get("created_at") or now),
            "updated_at": now,
            "last_scan_at": str(previous.get("last_scan_at") or ""),
            "last_status": str(previous.get("last_status") or "never_scanned"),
            "last_candidate_count": int(previous.get("last_candidate_count") or 0),
            "last_warning_count": int(previous.get("last_warning_count") or 0),
        }
        next_sources = [item for item in sources if item.get("id") != record_id]
        next_sources.append(record)
        self.sources_path.write_text(json.dumps(sorted(next_sources, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "source.saved",
            subject_type="source",
            subject_id=record_id,
            details={"name": clean_name, "type": clean_type, "source_group": record["source_group"]},
        )
        return record

    def record_source_scan(
        self,
        source_id: str,
        *,
        status: str,
        candidates: list[dict[str, Any]],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        source = next((item for item in self.load_sources() if item.get("id") == source_id), None)
        if not source:
            raise ValueError("Source not found.")
        now = now_iso()
        clean_candidates = [_candidate_preview_record(item) for item in candidates if isinstance(item, dict)]
        clean_warnings = [str(item) for item in warnings or [] if str(item).strip()]
        scan = {
            "id": stable_hash(f"{now}:{source_id}:{len(clean_candidates)}:{len(clean_warnings)}"),
            "source_id": source_id,
            "source_name": source.get("name", ""),
            "source_type": source.get("type", ""),
            "source_group": source.get("source_group", ""),
            "status": status,
            "scanned_at": now,
            "candidate_count": len(clean_candidates),
            "warning_count": len(clean_warnings),
            "warnings": clean_warnings[:20],
            "candidates": clean_candidates[:100],
        }
        scans = self.list_source_scans(limit=500)
        scans.append(scan)
        self.source_scans_path.write_text(json.dumps(scans[-500:], indent=2, sort_keys=True), encoding="utf-8")

        sources = self.load_sources()
        for item in sources:
            if item.get("id") != source_id:
                continue
            item["last_scan_at"] = now
            item["last_status"] = status
            item["last_candidate_count"] = len(clean_candidates)
            item["last_warning_count"] = len(clean_warnings)
            item["updated_at"] = now
        self.sources_path.write_text(json.dumps(sorted(sources, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "source.scan",
            subject_type="source",
            subject_id=source_id,
            details={"status": status, "candidate_count": len(clean_candidates), "warning_count": len(clean_warnings)},
        )
        return scan

    def list_source_scans(self, *, source_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.source_scans_path, list)
        scans = [item for item in value or [] if isinstance(item, dict)]
        if source_id:
            scans = [item for item in scans if item.get("source_id") == source_id]
        return scans[-max(1, min(limit, 500)) :]

    def list_expansion_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.expansion_runs_path, list)
        runs = [item for item in value or [] if isinstance(item, dict)]
        return runs[-max(1, min(limit, 500)) :]

    def expansion_sources_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now_value = now or datetime.now(timezone.utc)
        return [
            source
            for source in self.load_sources()
            if source.get("enabled", True)
            and str(source.get("schedule") or "manual") != "manual"
            and _source_schedule_due(source, now_value)
        ]

    def record_expansion_run(
        self,
        *,
        trigger: str,
        status: str,
        source_results: list[dict[str, Any]],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        now = now_iso()
        run = {
            "id": stable_hash(f"{now}:{trigger}:{len(source_results)}:{status}"),
            "created_at": now,
            "trigger": trigger,
            "status": status,
            "source_count": len(source_results),
            "scanned_source_count": sum(1 for item in source_results if item.get("status") != "skipped"),
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in source_results),
            "warning_count": sum(int(item.get("warning_count") or 0) for item in source_results) + len(warnings or []),
            "source_results": source_results[:100],
            "warnings": [str(item) for item in warnings or [] if str(item).strip()][:50],
        }
        runs = self.list_expansion_runs(limit=500)
        runs.append(run)
        self.expansion_runs_path.write_text(json.dumps(runs[-500:], indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "expansion.run",
            subject_type="expansion",
            subject_id=run["id"],
            details={"trigger": trigger, "status": status, "candidate_count": run["candidate_count"]},
        )
        return run

    def source_coverage(self) -> dict[str, Any]:
        sources = self.load_sources()
        scans = self.list_source_scans(limit=500)
        expansion_runs = self.list_expansion_runs(limit=25)
        domains = {
            str(candidate.get("domain") or "")
            for scan in scans
            for candidate in scan.get("candidates", [])
            if isinstance(candidate, dict) and candidate.get("domain")
        }
        return {
            "source_count": len(sources),
            "enabled_count": sum(1 for item in sources if item.get("enabled")),
            "source_type_counts": _count_by_key(sources, "type"),
            "source_group_counts": _count_by_key(sources, "source_group"),
            "scan_count": len(scans),
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in scans),
            "unique_candidate_domains": len(domains),
            "latest_scan": scans[-1] if scans else None,
            "latest_expansion_run": expansion_runs[-1] if expansion_runs else None,
            "due_source_count": len(self.expansion_sources_due()),
        }
