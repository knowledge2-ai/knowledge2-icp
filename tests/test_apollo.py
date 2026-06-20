from __future__ import annotations

import json
import unittest
from unittest import mock

from icp_engine import apollo
from icp_engine.apollo import ApolloClient


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self, _size: int | None = None) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake_apollo(*, search: dict[str, object], match: dict[str, object]):
    """Return (urlopen_stub, calls) that answers search + bulk_match by URL."""
    calls: list[dict[str, str]] = []

    def _urlopen(request, timeout: float = 0.0):  # noqa: ANN001 - urllib Request
        url = request.full_url
        body = request.data.decode("utf-8") if request.data else ""
        calls.append({"url": url, "body": body})
        if "/people/bulk_match" in url:
            return _FakeResponse(match)
        if "/mixed_people/api_search" in url:
            return _FakeResponse(search)
        raise AssertionError(f"unexpected Apollo URL {url}")

    return _urlopen, calls


class ApolloPeopleRevealTest(unittest.TestCase):
    def test_people_match_reveals_real_email(self) -> None:
        # Search teaser: obfuscated last name, locked placeholder email.
        search = {
            "people": [
                {
                    "id": "p1",
                    "first_name": "Dana",
                    "last_name_obfuscated": "L.",
                    "title": "VP Product",
                    "email": "email_not_unlocked@domain.com",
                    "has_email": True,
                    "organization": {"name": "Durable Fleet"},
                }
            ]
        }
        # Match reveal: full name + real verified email.
        match = {
            "matches": [
                {
                    "id": "p1",
                    "name": "Dana Lopez",
                    "title": "VP Product",
                    "email": "dana@durable.example",
                    "email_status": "verified",
                    "linkedin_url": "https://www.linkedin.com/in/dana-lopez",
                }
            ]
        }
        urlopen_stub, calls = _fake_apollo(search=search, match=match)
        client = ApolloClient(api_key="test-key")

        with mock.patch.object(apollo, "urlopen", urlopen_stub):
            result = client.search_people(domain="durable.example", titles=["vp product"])

        self.assertEqual(result["status"], "ok")
        people = result["people"]
        self.assertEqual(len(people), 1)
        person = people[0]
        self.assertEqual(person["name"], "Dana Lopez")
        self.assertEqual(person["email"], "dana@durable.example")
        self.assertEqual(person["email_status"], "verified")
        self.assertTrue(person["revealed"])

        # People Match was actually called, asking to reveal the personal email.
        match_call = next((c for c in calls if "/people/bulk_match" in c["url"]), None)
        self.assertIsNotNone(match_call, "bulk_match was not called")
        self.assertIn("reveal_personal_emails=true", match_call["url"])
        self.assertEqual(json.loads(match_call["body"]), {"details": [{"id": "p1"}]})

        # The locked placeholder never leaks as a real address.
        for item in people:
            self.assertNotIn("email_not_unlocked", str(item.get("email") or ""))

    def test_locked_placeholder_stripped_when_reveal_unavailable(self) -> None:
        search = {
            "people": [
                {
                    "id": "p2",
                    "name": "Sam Rivera",
                    "title": "CTO",
                    "email": "email_not_unlocked@domain.com",
                    "has_email": True,
                    "organization": {"name": "Durable Fleet"},
                }
            ]
        }
        # Reveal returns nothing (no credits / no match) -> fall back to teaser.
        urlopen_stub, _calls = _fake_apollo(search=search, match={"matches": []})
        client = ApolloClient(api_key="test-key")

        with mock.patch.object(apollo, "urlopen", urlopen_stub):
            person = client.search_people(domain="durable.example")["people"][0]

        self.assertEqual(person["email"], "")
        self.assertFalse(person["revealed"])
        # has_email teaser is surfaced honestly, not as "verified".
        self.assertEqual(person["email_status"], "available_unrevealed")

    def test_search_people_skipped_without_key(self) -> None:
        result = ApolloClient(api_key=None).search_people(domain="durable.example")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["people"], [])


if __name__ == "__main__":
    unittest.main()
