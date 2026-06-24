from __future__ import annotations

import json
import os
import unittest

from icp_engine.perplexity import (
    PerplexityApiError,
    PerplexityUnavailable,
    research_companies,
)


class _StubClient:
    """Mimics PerplexityRestClient.chat_completion without any network."""

    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def chat_completion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self._response


class _FailingClient:
    def chat_completion(self, **kwargs: object) -> object:
        raise PerplexityApiError("upstream boom", status_code=500)


def _sonar_response(companies: list[dict[str, object]], citations: list[str] | None = None) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": json.dumps({"companies": companies})}}],
        "citations": citations or [],
    }


class ResearchCompaniesTests(unittest.TestCase):
    def test_happy_path_returns_candidates_with_matched_citations(self) -> None:
        companies = [
            {"company": "Mojio", "domain": "moj.io", "reason": "Embedded fleet workflow AI."},
            {"company": "Acme", "domain": "https://www.acme.com/", "reason": "Dispatch assistant."},
        ]
        client = _StubClient(_sonar_response(companies, citations=["https://moj.io/ai", "https://unrelated.com"]))

        candidates, warnings = research_companies("fleet AI companies", criteria_markdown="# ICP", client=client)

        self.assertEqual(warnings, [])
        self.assertEqual([c.domain for c in candidates], ["moj.io", "www.acme.com"])
        self.assertEqual(candidates[0].source_url, "https://moj.io/ai")
        self.assertEqual(candidates[0].other_urls, ["https://moj.io/ai"])
        self.assertIn("Embedded fleet workflow AI.", candidates[0].notes)
        # Acme has no matching citation -> falls back to https://domain, empty other_urls.
        self.assertEqual(candidates[1].source_url, "https://www.acme.com")
        self.assertEqual(candidates[1].other_urls, [])

    def test_dedupes_and_caps_at_max_results(self) -> None:
        companies = [
            {"company": "A", "domain": "a.com"},
            {"company": "A dup", "domain": "a.com"},
            {"company": "B", "domain": "b.com"},
            {"company": "C", "domain": "c.com"},
        ]
        client = _StubClient(_sonar_response(companies))

        candidates, _ = research_companies("brief", max_results=2, client=client)

        self.assertEqual([c.domain for c in candidates], ["a.com", "b.com"])

    def test_criteria_markdown_reaches_request_body(self) -> None:
        client = _StubClient(_sonar_response([{"company": "X", "domain": "x.com"}]))

        research_companies("brief", criteria_markdown="UNIQUE-RUBRIC-MARKER-XYZ", client=client)

        system_message = client.calls[0]["messages"][0]["content"]
        self.assertIn("UNIQUE-RUBRIC-MARKER-XYZ", system_message)

    def test_oversized_criteria_is_bounded_in_system_prompt(self) -> None:
        # A full analyst rubric (~17KB) over-constrains Sonar into returning an
        # empty list; discovery only injects the decision-relevant head.
        client = _StubClient(_sonar_response([{"company": "X", "domain": "x.com"}]))
        # Realistic rubric shape: paragraph-broken sections, the gating tail far
        # past the budget.
        head = "HEAD-MARKER bottom line and hard gates.\n\n"
        filler = "".join(f"Section {i} of the rubric methodology.\n\n" for i in range(200))  # ~7KB
        tail = "\n\nTAIL-MARKER exclusion methodology that silences Sonar."
        research_companies("brief", criteria_markdown=head + filler + tail, client=client)

        system_message = client.calls[0]["messages"][0]["content"]
        self.assertIn("HEAD-MARKER", system_message)
        self.assertNotIn("TAIL-MARKER", system_message)
        self.assertIn("truncated for sourcing", system_message)

    def test_empty_brief_returns_warning(self) -> None:
        candidates, warnings = research_companies("   ", client=_StubClient(_sonar_response([])))
        self.assertEqual(candidates, [])
        self.assertTrue(any("empty" in w.lower() for w in warnings))

    def test_missing_key_raises_unavailable(self) -> None:
        saved = os.environ.pop("PERPLEXITY_API_KEY", None)
        try:
            with self.assertRaises(PerplexityUnavailable):
                research_companies("brief")
        finally:
            if saved is not None:
                os.environ["PERPLEXITY_API_KEY"] = saved

    def test_non_json_content_is_graceful(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": "not json at all"}}]})
        candidates, warnings = research_companies("brief", client=client)
        self.assertEqual(candidates, [])
        self.assertTrue(any("non-JSON" in w for w in warnings))

    def test_empty_content_is_graceful(self) -> None:
        client = _StubClient({"choices": []})
        candidates, warnings = research_companies("brief", client=client)
        self.assertEqual(candidates, [])
        self.assertTrue(warnings)

    def test_missing_companies_array_is_graceful(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": json.dumps({"foo": "bar"})}}]})
        candidates, warnings = research_companies("brief", client=client)
        self.assertEqual(candidates, [])
        self.assertTrue(warnings)

    def test_api_error_falls_back_to_warning(self) -> None:
        candidates, warnings = research_companies("brief", client=_FailingClient())
        self.assertEqual(candidates, [])
        self.assertTrue(any("Perplexity research provider failed" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
