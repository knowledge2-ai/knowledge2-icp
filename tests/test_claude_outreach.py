from __future__ import annotations

import os
import unittest

from icp_engine.claude import ClaudeUnavailable
from icp_engine.claude_outreach import generate_outreach
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


def _persona() -> dict[str, object]:
    return {
        "role": "economic_buyer",
        "title": "Chief Product Officer",
        "rationale": "Owns AI product strategy and roadmap tradeoffs.",
    }


def _outreach_block(**overrides: object) -> _Block:
    payload = {
        "subject": "Acme Fleet's dispatch data as an AI wedge",
        "body": "Hi — saw your platform pairs fleet workflow analytics with open APIs...",
        "cta": "Open to a 20-minute look at one workflow?",
        "angle": "Tied the opener to their API-integrated workflow analytics.",
    }
    payload.update(overrides)
    return _Block("write_outreach", payload)


class ClaudeOutreachTest(unittest.TestCase):
    def test_generate_returns_structured_draft(self) -> None:
        client = _Client(_Response([_outreach_block()]))

        draft = generate_outreach(
            _company(),
            _persona(),
            _evidence(),
            role="economic_buyer",
            criteria_markdown="# ICP\n\n- Prefer embedded workflow AI.",
            client=client,
        )

        self.assertEqual(draft["subject"], "Acme Fleet's dispatch data as an AI wedge")
        self.assertIn("workflow", draft["body"])
        self.assertTrue(draft["cta"])
        self.assertTrue(draft["model"].startswith("claude:"))

    def test_criteria_and_account_context_reach_the_prompt(self) -> None:
        client = _Client(_Response([_outreach_block()]))
        rubric_marker = "UNIQUE-RUBRIC-7c1d"
        context_marker = "UNIQUE-K2-CONTEXT-44ab"

        generate_outreach(
            _company(),
            _persona(),
            _evidence(),
            account_context=f"K2 says: {context_marker}",
            criteria_markdown=f"# ICP\n\n- {rubric_marker}",
            client=client,
        )

        call = client.messages.calls[0]
        self.assertIn(rubric_marker, str(call["system"]))
        self.assertIn(context_marker, str(call["messages"]))

    def test_selected_template_structure_reaches_prompt_and_payload(self) -> None:
        client = _Client(_Response([_outreach_block()]))

        draft = generate_outreach(
            _company(),
            {"title": "Chief Executive Officer", "role": "economic_buyer"},
            _evidence(),
            signal_tags=["ai-native"],
            client=client,
        )

        # CEO persona routes to the exec scaffold; its name rides on the payload...
        self.assertEqual(draft["template"], "exec-ai-urgency")
        # ...and its numbered beats are injected into the user prompt for the LLM to fill.
        user_prompt = str(client.messages.calls[0]["messages"])
        self.assertIn("exec-ai-urgency", user_prompt)
        self.assertIn("category positioning", user_prompt)
        self.assertIn("published_at", user_prompt)

    def test_missing_tool_call_raises_claude_unavailable(self) -> None:
        client = _Client(_Response([_Block("write_outreach", {}, block_type="text")]))

        with self.assertRaises(ClaudeUnavailable):
            generate_outreach(_company(), _persona(), _evidence(), client=client)

    def test_default_client_without_sdk_or_key_raises(self) -> None:
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(ClaudeUnavailable):
                generate_outreach(_company(), _persona(), _evidence())
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
