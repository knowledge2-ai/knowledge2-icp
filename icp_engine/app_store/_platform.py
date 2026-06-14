"""Platform cluster: audit log and provider metering/authorization."""

from __future__ import annotations

import json
from typing import Any

from ..seed_defaults import SEEDED_SETTINGS
from ._helpers import (
    _deep_merge_provider_limits,
    _load_json_file,
    _normalize_provider_action,
    _provider_action_amount,
    _provider_amounts_by_action,
    _provider_event_is_today,
    _provider_event_within_seconds,
    now_iso,
    stable_hash,
)


class PlatformMixin:
    def append_audit_event(
        self,
        action: str,
        *,
        subject_type: str,
        subject_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        events = self.list_audit_events(limit=500)
        event = {
            "id": stable_hash(f"{now_iso()}:{action}:{subject_type}:{subject_id}:{len(events)}"),
            "created_at": now_iso(),
            "action": action,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "details": details or {},
        }
        events.append(event)
        self.audit_log_path.write_text(json.dumps(events[-500:], indent=2, sort_keys=True), encoding="utf-8")
        return event

    def list_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.audit_log_path, list)
        events = [item for item in value or [] if isinstance(item, dict)]
        return events[-max(1, min(limit, 500)) :]

    def provider_policy(self) -> dict[str, Any]:
        return _deep_merge_provider_limits(
            SEEDED_SETTINGS.get("provider_limits", {}),
            self.load_settings().get("provider_limits", {}),
        )

    def authorize_provider_action(
        self,
        action: str,
        *,
        amount: int = 1,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_action = _normalize_provider_action(action)
        clean_amount = max(1, int(amount or 1))
        clean_details = details if isinstance(details, dict) else {}
        policy = self.provider_policy()
        if not policy.get("enabled", True):
            event = self.record_provider_usage(
                clean_action,
                status="allowed",
                amount=clean_amount,
                details={**clean_details, "policy_disabled": True},
            )
            return {"allowed": True, "action": clean_action, "event": event, "policy": policy}
        denial = self._provider_action_denial(clean_action, clean_amount, clean_details, policy)
        if denial:
            event = self.record_provider_usage(
                clean_action,
                status="denied",
                amount=clean_amount,
                reason=denial["reason"],
                details=clean_details,
            )
            return {
                "allowed": False,
                "action": clean_action,
                "reason": denial["reason"],
                "event": event,
                "policy": policy,
                **denial,
            }
        event = self.record_provider_usage(
            clean_action,
            status="allowed",
            amount=clean_amount,
            details=clean_details,
        )
        return {"allowed": True, "action": clean_action, "event": event, "policy": policy}

    def record_provider_usage(
        self,
        action: str,
        *,
        status: str,
        amount: int = 1,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_action = _normalize_provider_action(action)
        now = now_iso()
        events = self.list_provider_usage(limit=1000)
        event = {
            "id": stable_hash(f"{now}:{clean_action}:{status}:{len(events)}"),
            "created_at": now,
            "action": clean_action,
            "status": status,
            "amount": max(1, int(amount or 1)),
            "reason": reason,
            "details": details or {},
        }
        events.append(event)
        self.provider_usage_path.write_text(
            json.dumps(events[-1000:], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            f"provider_action.{status}",
            subject_type="provider_action",
            subject_id=clean_action,
            details={
                "action": clean_action,
                "amount": event["amount"],
                "reason": reason,
                **(details or {}),
            },
        )
        return event

    def list_provider_usage(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.provider_usage_path, list)
        events = [item for item in value or [] if isinstance(item, dict)]
        return events[-max(1, min(limit, 1000)) :]

    def provider_usage_summary(self) -> dict[str, Any]:
        policy = self.provider_policy()
        events = self.list_provider_usage(limit=1000)
        today = now_iso()[:10]
        allowed_today = [
            event
            for event in events
            if str(event.get("created_at", "")).startswith(today)
            and event.get("status") == "allowed"
        ]
        denied_today = [
            event
            for event in events
            if str(event.get("created_at", "")).startswith(today)
            and event.get("status") == "denied"
        ]
        return {
            "policy": policy,
            "today": today,
            "allowed_counts": _provider_amounts_by_action(allowed_today),
            "denied_counts": _provider_amounts_by_action(denied_today),
            "recent_events": events[-25:],
        }

    def _provider_action_denial(
        self,
        action: str,
        amount: int,
        details: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any] | None:
        per_run = policy.get("per_run", {}) if isinstance(policy.get("per_run"), dict) else {}
        max_companies = int(details.get("max_companies") or 0)
        max_pages = int(details.get("max_pages") or 0)
        if (
            max_companies
            and int(per_run.get("max_companies") or 0)
            and max_companies > int(per_run["max_companies"])
        ):
            return {
                "reason": f"Requested max_companies={max_companies} exceeds provider policy max_companies={per_run['max_companies']}.",
                "limit_type": "per_run",
                "limit": int(per_run["max_companies"]),
                "usage": max_companies,
            }
        if (
            max_pages
            and int(per_run.get("max_pages") or 0)
            and max_pages > int(per_run["max_pages"])
        ):
            return {
                "reason": f"Requested max_pages={max_pages} exceeds provider policy max_pages={per_run['max_pages']}.",
                "limit_type": "per_run",
                "limit": int(per_run["max_pages"]),
                "usage": max_pages,
            }
        events = self.list_provider_usage(limit=1000)
        daily_limits = policy.get("daily", {}) if isinstance(policy.get("daily"), dict) else {}
        daily_limit = int(daily_limits.get(action) or 0)
        if daily_limit:
            usage = _provider_action_amount(
                [
                    event
                    for event in events
                    if _provider_event_is_today(event)
                    and event.get("action") == action
                    and event.get("status") == "allowed"
                ]
            )
            if usage + amount > daily_limit:
                return {
                    "reason": f"Daily provider budget for {action} is exhausted ({usage}/{daily_limit}, requested {amount}).",
                    "limit_type": "daily",
                    "limit": daily_limit,
                    "usage": usage,
                }
        rate_limits = policy.get("rate_per_minute", {}) if isinstance(policy.get("rate_per_minute"), dict) else {}
        rate_limit = int(rate_limits.get(action) or 0)
        if rate_limit:
            usage = _provider_action_amount(
                [
                    event
                    for event in events
                    if _provider_event_within_seconds(event, 60)
                    and event.get("action") == action
                    and event.get("status") == "allowed"
                ]
            )
            if usage + amount > rate_limit:
                return {
                    "reason": f"Rate limit for {action} is exceeded ({usage}/{rate_limit} in the last minute, requested {amount}).",
                    "limit_type": "rate_per_minute",
                    "limit": rate_limit,
                    "usage": usage,
                }
        return None
