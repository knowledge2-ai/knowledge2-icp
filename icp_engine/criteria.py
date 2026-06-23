from __future__ import annotations

import re
from dataclasses import dataclass, field


DEFAULT_TIER_A_THRESHOLD = 75
DEFAULT_TIER_B_THRESHOLD = 60
DEFAULT_MIN_EMPLOYEES = 25
DEFAULT_MAX_EMPLOYEES = 2000

DEFAULT_PRIORITY_TERMS = [
    "automotive",
    "dealer",
    "dealership",
    "fleet",
    "telematics",
    "field service",
    "maintenance",
    "logistics",
    "warehouse",
    "construction",
    "property",
    "real estate",
    "facilities",
    "insurance",
    "claims",
    "healthcare",
    "life sciences",
    "pharma",
    "dental",
    "veterinary",
    "manufacturing",
    "erp",
    "compliance",
    "legal",
    "accounting",
    "banking",
    "credit union",
    "lending",
    "mortgage",
    "nonprofit",
    "restaurant",
    "hospitality",
    "government",
    "public sector",
    "education",
    "retail",
    "grocery",
    "agriculture",
    "energy",
    "utilities",
    "transportation",
    "trucking",
    "vertical market",
]

KNOWN_PRIORITY_TERMS = sorted(
    set(
        DEFAULT_PRIORITY_TERMS
        + [
            "admin",
            "billing",
            "cmms",
            "education",
            "fintech",
            "govtech",
            "healthcare admin",
            "legaltech",
            "maritime",
            "permitting",
            "payments",
            "practice management",
            "rcm",
            "tms",
            "wms",
        ]
    )
)


@dataclass(frozen=True)
class CriteriaProfile:
    source: str = ""
    hash: str = ""
    tier_a_threshold: int = DEFAULT_TIER_A_THRESHOLD
    tier_b_threshold: int = DEFAULT_TIER_B_THRESHOLD
    min_employee_count: int = DEFAULT_MIN_EMPLOYEES
    max_employee_count: int = DEFAULT_MAX_EMPLOYEES
    priority_terms: list[str] = field(default_factory=lambda: list(DEFAULT_PRIORITY_TERMS))
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "hash": self.hash,
            "tier_a_threshold": self.tier_a_threshold,
            "tier_b_threshold": self.tier_b_threshold,
            "min_employee_count": self.min_employee_count,
            "max_employee_count": self.max_employee_count,
            "priority_terms": list(self.priority_terms),
            "warnings": list(self.warnings),
        }


def build_criteria_profile(markdown: str, *, source: str = "", criteria_hash: str = "") -> CriteriaProfile:
    warnings: list[str] = []
    tier_a = _extract_threshold(markdown, "a", DEFAULT_TIER_A_THRESHOLD, warnings)
    tier_b = _extract_threshold(markdown, "b", DEFAULT_TIER_B_THRESHOLD, warnings)
    if tier_b >= tier_a:
        warnings.append("Tier B threshold must be lower than Tier A; using default thresholds.")
        tier_a = DEFAULT_TIER_A_THRESHOLD
        tier_b = DEFAULT_TIER_B_THRESHOLD

    min_employees, max_employees = _extract_employee_range(markdown, warnings)
    priority_terms = _extract_priority_terms(markdown)

    return CriteriaProfile(
        source=source,
        hash=criteria_hash,
        tier_a_threshold=tier_a,
        tier_b_threshold=tier_b,
        min_employee_count=min_employees,
        max_employee_count=max_employees,
        priority_terms=priority_terms,
        warnings=warnings,
    )


def _extract_threshold(markdown: str, tier: str, default: int, warnings: list[str]) -> int:
    normalized = markdown.lower().replace("–", "-").replace("—", "-")
    patterns = [
        rf"tier\s*{tier}\s*(?:threshold|score)?\D{{0,30}}(\d{{2,3}})",
        rf"\b{tier.upper()}\s*tier\s*(?:threshold|score)?\D{{0,30}}(\d{{2,3}})",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.I)
        if not match:
            continue
        value = int(match.group(1))
        if 0 <= value <= 100:
            return value
        warnings.append(f"Ignored out-of-range Tier {tier.upper()} threshold {value}.")
        return default
    return default


def _extract_employee_range(markdown: str, warnings: list[str]) -> tuple[int, int]:
    normalized = markdown.lower().replace("–", "-").replace("—", "-").replace(",", "")
    match = re.search(r"(\d{1,5})\s*-\s*(\d{1,5})\s+employees", normalized)
    if not match:
        return DEFAULT_MIN_EMPLOYEES, DEFAULT_MAX_EMPLOYEES
    minimum = int(match.group(1))
    maximum = int(match.group(2))
    if minimum <= 0 or maximum < minimum:
        warnings.append("Ignored invalid employee range in criteria markdown.")
        return DEFAULT_MIN_EMPLOYEES, DEFAULT_MAX_EMPLOYEES
    return minimum, maximum


def _extract_priority_terms(markdown: str) -> list[str]:
    normalized = markdown.lower()
    terms = {term for term in KNOWN_PRIORITY_TERMS if term in normalized}
    terms.update(_extract_structured_terms(normalized))
    if not terms:
        return list(DEFAULT_PRIORITY_TERMS)
    return sorted(terms)


def _extract_structured_terms(markdown: str) -> set[str]:
    terms: set[str] = set()
    for line in markdown.splitlines():
        lower = line.lower()
        if not any(label in lower for label in ["priority vertical", "target vertical", "priority category", "target category"]):
            continue
        payload = line.split(":", 1)[1] if ":" in line else line
        for item in re.split(r"[,;|/]", payload):
            cleaned = re.sub(r"[^a-z0-9 +&-]+", " ", item.lower())
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if 2 <= len(cleaned) <= 40 and not cleaned.startswith(("priority", "target")):
                terms.add(cleaned)
    return terms
