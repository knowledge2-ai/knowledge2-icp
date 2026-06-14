from __future__ import annotations

import unittest

from icp_engine.claude import (
    ClaudeUnavailable,
    classify_with_claude,
    suggest_criteria,
)
from icp_engine.models import CompanyInput, Evidence


class _Block:
    """Mimics an Anthropic tool_use content block."""

    def __init__(self, name: str, payload: dict[str, object], block_type: str = "tool_use") -> None:
        self.type = block_type
        self.name = name
        self.input = payload


class _Response:
    def __init__(self, content: list[_Block]) -> None:
        self.content = content


class _Messages:
    def __init__(self, response: _Response) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _Response:
        self.calls.append(kwargs)
        return self._response


class _Client:
    def __init__(self, response: _Response) -> None:
        self.messages = _Messages(response)


def _company() -> CompanyInput:
    return CompanyInput(company="Acme Fleet", domain="acme.example", category="fleet telematics")


def _evidence() -> list[Evidence]:
    return [
        Evidence(
            "e1",
            "https://acme.example/platform",
            "Platform",
            "Fleet workflow analytics with API integrations and enterprise customers.",
        )
    ]


def _classification_block(**overrides: object) -> _Block:
    payload = {
        "ai_posture": 3,
        "data_workflow": 4,
        "commercial_urgency": 3,
        "budget_access": 3,
        "feasibility": 4,
        "confidence": 0.82,
        "reasons": {"ai_posture": "Embedded workflow assistant in the dispatch product."},
        "evidence_ids": {"ai_posture": ["e1"]},
        "ai_narrative": "Acme embeds an AI dispatch assistant inside its fleet workflow.",
    }
    payload.update(overrides)
    return _Block("record_classification", payload)


class ClaudeAdapterTest(unittest.TestCase):
    def test_classify_returns_classification_with_citations_and_narrative(self) -> None:
        client = _Client(_Response([_classification_block()]))

        classification = classify_with_claude(
            _company(),
            _evidence(),
            criteria_markdown="# ICP\n\n- Prefer embedded workflow AI.",
            client=client,
        )

        self.assertEqual(classification.ai_posture, 3)
        self.assertEqual(classification.data_workflow, 4)
        self.assertAlmostEqual(classification.confidence, 0.82)
        self.assertTrue(classification.source.startswith("claude:"))
        self.assertEqual(classification.evidence_ids["ai_posture"], ["e1"])
        self.assertIn("dispatch assistant", classification.ai_narrative)

    def test_criteria_markdown_reaches_the_prompt(self) -> None:
        client = _Client(_Response([_classification_block()]))
        marker = "UNIQUE-RUBRIC-MARKER-9f3a"

        classify_with_claude(
            _company(),
            _evidence(),
            criteria_markdown=f"# ICP\n\n- {marker}",
            client=client,
        )

        system_prompt = client.messages.calls[0]["system"]
        self.assertIn(marker, str(system_prompt))

    def test_low_confidence_passes_through_untouched(self) -> None:
        client = _Client(_Response([_classification_block(confidence=0.1)]))

        classification = classify_with_claude(
            _company(),
            _evidence(),
            criteria_markdown="# ICP",
            client=client,
        )

        # The adapter does not gate; scoring._merge_classification owns the 0.35 gate.
        self.assertAlmostEqual(classification.confidence, 0.1)

    def test_missing_tool_call_raises_claude_unavailable(self) -> None:
        client = _Client(_Response([_Block("record_classification", {}, block_type="text")]))

        with self.assertRaises(ClaudeUnavailable):
            classify_with_claude(
                _company(),
                _evidence(),
                criteria_markdown="# ICP",
                client=client,
            )

    def test_default_client_without_sdk_or_key_raises(self) -> None:
        # No client injected and no ANTHROPIC_API_KEY in the offline test env.
        import os

        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(ClaudeUnavailable):
                classify_with_claude(
                    _company(),
                    _evidence(),
                    criteria_markdown="# ICP",
                )
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_suggest_criteria_returns_proposal(self) -> None:
        block = _Block(
            "propose_criteria",
            {
                "markdown": "# Improved ICP\n\n- Sharper disqualifiers.",
                "rationale": "Tightens the AI-posture rubric.",
                "diff_summary": "Clarified ai_posture levels.",
            },
        )
        client = _Client(_Response([block]))

        proposal = suggest_criteria("# Current ICP", [], client=client)

        self.assertEqual(proposal["markdown"], "# Improved ICP\n\n- Sharper disqualifiers.")
        self.assertIn("Tightens", proposal["rationale"])
        self.assertTrue(proposal["model"].startswith("claude:"))


if __name__ == "__main__":
    unittest.main()
