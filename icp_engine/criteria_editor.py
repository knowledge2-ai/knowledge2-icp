from __future__ import annotations

import re
from typing import Any


def format_criteria_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    formatted: list[str] = []
    blank_count = 0
    in_fence = False

    for raw_line in lines:
        line = raw_line.rstrip().replace("\t", "  ")
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            line = _normalize_bullet(line)
            if line.startswith("#") and formatted and formatted[-1] != "":
                formatted.append("")
        if line == "":
            blank_count += 1
            if blank_count <= 1:
                formatted.append(line)
            continue
        blank_count = 0
        formatted.append(line)

    while formatted and formatted[0] == "":
        formatted.pop(0)
    while formatted and formatted[-1] == "":
        formatted.pop()
    return "\n".join(formatted) + "\n"


def lint_criteria_markdown(markdown: str) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    raw_lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    non_empty_lines = [line for line in raw_lines if line.strip()]
    heading_levels: list[tuple[int, int]] = []
    h1_count = 0
    in_fence = False

    if not markdown.strip():
        diagnostics.append(_diagnostic("error", 1, "empty", "Criteria markdown is empty."))

    for index, line in enumerate(raw_lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        if line.rstrip() != line:
            diagnostics.append(_diagnostic("warning", index, "trailing-whitespace", "Remove trailing whitespace."))
        if "\t" in line:
            diagnostics.append(_diagnostic("warning", index, "tab-indentation", "Use spaces instead of tabs."))
        stripped = line.strip()
        if re.match(r"^[*+]\s+", stripped):
            diagnostics.append(_diagnostic("info", index, "bullet-style", "Use '-' for markdown bullets."))
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            heading_levels.append((index, level))
            if level == 1:
                h1_count += 1

    if non_empty_lines and not any(line.startswith("# ") for line in non_empty_lines):
        diagnostics.append(_diagnostic("warning", 1, "missing-h1", "Add a top-level '# ...' heading."))
    if h1_count > 1:
        diagnostics.append(_diagnostic("warning", 1, "multiple-h1", "Use one top-level H1 heading."))

    previous_level = 0
    for line_number, level in heading_levels:
        if previous_level and level > previous_level + 1:
            diagnostics.append(_diagnostic("warning", line_number, "heading-jump", "Do not skip heading levels."))
        previous_level = level

    text = markdown.lower()
    if "tier a" not in text:
        diagnostics.append(_diagnostic("info", 1, "tier-a-default", "No Tier A threshold found; default scoring threshold applies."))
    if "tier b" not in text:
        diagnostics.append(_diagnostic("info", 1, "tier-b-default", "No Tier B threshold found; default scoring threshold applies."))
    if "employee" not in text and "budget" not in text:
        diagnostics.append(_diagnostic("info", 1, "budget-default", "No employee or budget range found; default budget gates apply."))

    formatted = format_criteria_markdown(markdown)
    return {
        "diagnostics": diagnostics,
        "error_count": sum(1 for item in diagnostics if item["severity"] == "error"),
        "warning_count": sum(1 for item in diagnostics if item["severity"] == "warning"),
        "info_count": sum(1 for item in diagnostics if item["severity"] == "info"),
        "formatted": formatted,
        "changed": formatted != markdown,
    }


def _normalize_bullet(line: str) -> str:
    indentation = line[: len(line) - len(line.lstrip(" "))]
    stripped = line.strip()
    bullet = re.match(r"^[*+]\s+(.+)$", stripped)
    if bullet:
        return f"{indentation}- {bullet.group(1)}"
    return line


def _diagnostic(severity: str, line: int, rule: str, message: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "line": line,
        "rule": rule,
        "message": message,
    }
