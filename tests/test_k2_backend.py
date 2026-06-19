from __future__ import annotations

import unittest

from icp_engine.k2_backend import (
    K2Backend,
    _account_dossier_document,
    _excerpt,
    build_metadata_filter,
)


class _FakeSearchClient:
    """Stub K2 client capturing search_batch calls and returning canned hits."""

    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.calls: list[dict[str, object]] = []

    def search_batch(self, corpus_id, queries, *, top_k=5, filters=None):  # type: ignore[no-untyped-def]
        self.calls.append({"corpus_id": corpus_id, "queries": queries, "top_k": top_k, "filters": filters})
        return {"responses": [{"results": self.hits}]}


def _hit(company: str, domain: str, *, tier: str, posture: str, vertical: str) -> dict[str, object]:
    return {
        "text": f"{company} workflow platform",
        "document": {"source_uri": f"https://{domain}/about"},
        "metadata": {
            "company": company,
            "domain": domain,
            "tier": tier,
            "ai_posture": posture,
            "vertical": vertical,
            "total_score": 80,
        },
    }


class MetadataFilterTest(unittest.TestCase):
    def test_builds_and_shaped_filter_from_clauses(self) -> None:
        result = build_metadata_filter([("tier", "==", "A"), ("ai_posture", "==", "none")])

        self.assertEqual(result["condition"], "and")
        self.assertEqual(
            result["filters"],
            [
                {"key": "tier", "op": "==", "value": "A"},
                {"key": "ai_posture", "op": "==", "value": "none"},
            ],
        )

    def test_empty_clauses_yield_empty_filter(self) -> None:
        self.assertEqual(build_metadata_filter([]), {"condition": "and", "filters": []})

    def test_unknown_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_metadata_filter([("bogus_field", "==", "x")])

    def test_unknown_op_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_metadata_filter([("tier", "~=", "A")])


class AnswerQuestionFilterRegressionTest(unittest.TestCase):
    def test_answer_question_still_scopes_to_run_id(self) -> None:
        captured: dict[str, object] = {}

        class _Client:
            def generate_answer(self, corpus_id, query, *, top_k=8, filters=None):  # type: ignore[no-untyped-def]
                captured["corpus_id"] = corpus_id
                captured["filters"] = filters
                return {"answer": "ok", "model": "stub", "results": []}

        backend = K2Backend(api_key="test-key")
        run = {"id": "run-9", "k2": {"corpus_id": "corpus-9"}}

        result = backend.answer_question(run, "who?", client=_Client())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            captured["filters"],
            {"condition": "and", "filters": [{"key": "run_id", "op": "==", "value": "run-9"}]},
        )


class MineCorpusTest(unittest.TestCase):
    def test_live_path_shapes_results_and_facets(self) -> None:
        client = _FakeSearchClient(
            [
                _hit("Mojio", "moj.io", tier="A", posture="none", vertical="telematics"),
                _hit("FleetCo", "fleetco.com", tier="A", posture="none", vertical="telematics"),
            ]
        )
        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        payload = backend.mine_corpus(
            query="telematics",
            filters=[{"key": "tier", "op": "==", "value": "A"}],
            corpus_key="candidate",
            client=client,
        )

        self.assertEqual(payload["provider"], "k2")
        self.assertEqual(payload["corpus_id"], "corpus-cand")
        self.assertEqual({r["domain"] for r in payload["results"]}, {"moj.io", "fleetco.com"})
        self.assertEqual(payload["facets"]["tier"], {"A": 2})
        # The metadata filter actually reached the client.
        self.assertEqual(client.calls[0]["filters"]["filters"][0]["key"], "tier")

    def test_filter_ops_drop_semantic_query(self) -> None:
        # When metadata clauses are present, the operation is an exact filter: the
        # free-text query must NOT ride along, or K2's semantic ranker narrows the
        # result off the exact match set (bake-off: F1 1.0 -> 0.05). The query is
        # dropped to "" so the metadata filter behaves as a pure WHERE.
        client = _FakeSearchClient([_hit("Mojio", "moj.io", tier="A", posture="none", vertical="telematics")])
        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        backend.mine_corpus(
            query="telematics workflow platform",
            filters=[{"key": "tier", "op": "==", "value": "A"}],
            corpus_key="candidate",
            client=client,
        )

        self.assertEqual(client.calls[0]["queries"], [""])
        self.assertEqual(client.calls[0]["filters"]["filters"][0]["key"], "tier")

    def test_filter_free_mining_keeps_semantic_query(self) -> None:
        # No clauses -> pure semantic mining: the query must reach the ranker.
        client = _FakeSearchClient([_hit("Mojio", "moj.io", tier="A", posture="none", vertical="telematics")])
        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        backend.mine_corpus(query="telematics platforms", filters=[], corpus_key="candidate", client=client)

        self.assertEqual(client.calls[0]["queries"], ["telematics platforms"])

    def test_bad_filter_key_raises(self) -> None:
        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"
        with self.assertRaises(ValueError):
            backend.mine_corpus(query="x", filters=[{"key": "bogus", "op": "==", "value": "A"}], client=_FakeSearchClient([]))

    def test_unconfigured_falls_back_to_local_store(self) -> None:
        backend = K2Backend(api_key="")  # no key, no corpus

        payload = backend.mine_corpus(query="", filters=[("tier", "==", "A")], store=_FakeStore())

        self.assertEqual(payload["provider"], "local")
        self.assertEqual({r["domain"] for r in payload["results"]}, {"moj.io", "fleetco.com"})

    def test_live_failure_falls_back_to_local_with_warning(self) -> None:
        class _Boom:
            def search_batch(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("k2 down")

        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        payload = backend.mine_corpus(query="", filters=[], client=_Boom(), store=_FakeStore())

        self.assertEqual(payload["provider"], "local")
        self.assertTrue(any("k2 down" in warning for warning in payload["warnings"]))


class FindLookalikesTest(unittest.TestCase):
    def test_live_path_excludes_seed_domains(self) -> None:
        client = _FakeSearchClient(
            [
                _hit("Mojio", "moj.io", tier="A", posture="none", vertical="telematics"),
                _hit("FleetCo", "fleetco.com", tier="A", posture="none", vertical="telematics"),
            ]
        )
        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        payload = backend.find_lookalikes(seed_domains=["moj.io"], client=client, store=_FakeStore())

        domains = {r["domain"] for r in payload["results"]}
        self.assertNotIn("moj.io", domains)
        self.assertIn("fleetco.com", domains)

    def test_local_path_ranks_by_shared_features(self) -> None:
        backend = K2Backend(api_key="")
        payload = backend.find_lookalikes(seed_domains=["moj.io"], store=_FakeStore())

        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["results"][0]["domain"], "fleetco.com")

    def test_empty_seeds_returns_warning(self) -> None:
        payload = K2Backend(api_key="").find_lookalikes(seed_domains=[], store=_FakeStore())
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["warnings"])

    def test_live_failure_falls_back_to_local_with_warning(self) -> None:
        class _Boom:
            def search_batch(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("k2 down")

        backend = K2Backend(api_key="test-key")
        backend.corpus_ids["candidate"] = "corpus-cand"

        payload = backend.find_lookalikes(seed_domains=["moj.io"], client=_Boom(), store=_FakeStore())

        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["results"][0]["domain"], "fleetco.com")
        self.assertTrue(any("k2 down" in warning for warning in payload["warnings"]))


def _dossier_lead() -> dict[str, object]:
    return {
        "score": {
            "tier": "A",
            "total_score": 82,
            "company": {"company": "Mojio", "domain": "moj.io"},
            "classification": {"ai_posture": "none"},
        },
        "metadata": {
            "vertical": "telematics",
            "signal_tags": ["telematics", "workflow-data"],
            "criteria_profile": {"tier_a_threshold": 75, "tier_b_threshold": 60, "min_employee_count": 25, "max_employee_count": 2000},
            "qualification": {"qualifier": "claude", "source": "llm", "ai_narrative": "Mojio runs connected-vehicle telematics with a workflow-data backbone, a strong fit for the data wedge."},
            "source_refs": {"github_urls": ["https://github.com/mojio"], "docs_urls": ["https://moj.io/docs"]},
        },
        "strategy": {
            "outreach_angle": "telematics data wedge",
            "offer": "pilot integration",
            "personas": [{"title": "VP Engineering", "why": "owns the data platform"}, {"title": "Head of Data"}],
        },
        "evidence": [
            {"url": "https://moj.io/about", "title": "About Mojio", "text": "Mojio is a connected-car platform. " * 20},
            {"url": "https://moj.io/product", "title": "Product", "text": "Short evidence note."},
        ],
    }


class AccountDossierDocumentTest(unittest.TestCase):
    def _build(self) -> dict[str, object]:
        lead = _dossier_lead()
        return _account_dossier_document(
            {"id": "run-1", "query": "telematics", "criteria": {"hash": "h1"}},
            lead,
            lead["score"],
            lead["score"]["company"],
            lead["strategy"],
            lead["metadata"],
        )

    def test_text_carries_every_section_and_known_facts(self) -> None:
        doc = self._build()
        text = doc["text"]
        for header in ("# Mojio — moj.io", "## Classification", "## Why they fit the ICP", "## Evidence", "## Outreach posture", "## Public footprint"):
            self.assertIn(header, text)
        # The bake-off grounding facts must be present in prose, not just metadata.
        self.assertIn("telematics", text)
        self.assertIn("none", text)  # ai_posture
        self.assertIn("A (score 82)", text)
        self.assertIn("workflow-data", text)  # top signal
        self.assertIn("connected-vehicle telematics", text)  # ai_narrative woven in
        self.assertIn("VP Engineering — owns the data platform", text)
        self.assertIn("https://moj.io/about", text)

    def test_metadata_marks_dossier_type(self) -> None:
        meta = self._build()["metadata"]
        self.assertEqual(meta["source_type"], "account_dossier")
        self.assertEqual(meta["evidence_id"], "account-dossier")
        self.assertEqual(meta["tier"], "A")
        self.assertEqual(meta["vertical"], "telematics")
        self.assertEqual(meta["signal_tags"], ["telematics", "workflow-data"])

    def test_id_is_stable_and_account_scoped(self) -> None:
        self.assertEqual(self._build()["id"], "run-1:moj.io:account-dossier")

    def test_dossier_is_substantially_richer_than_a_label_dump(self) -> None:
        # The whole point: more than the ~400-char summary the grounding ties on.
        self.assertGreater(len(self._build()["text"]), 600)

    def test_missing_evidence_does_not_break_the_section(self) -> None:
        lead = _dossier_lead()
        lead["evidence"] = []
        doc = _account_dossier_document(
            {"id": "run-1"}, lead, lead["score"], lead["score"]["company"], lead["strategy"], lead["metadata"]
        )
        self.assertIn("No scraped page content captured", doc["text"])


class ExcerptTest(unittest.TestCase):
    def test_short_text_passes_through_with_whitespace_collapsed(self) -> None:
        self.assertEqual(_excerpt("a   b\n c"), "a b c")

    def test_truncates_at_sentence_boundary(self) -> None:
        # Boundary in the back half (>= limit/2) is honored; a too-early period is
        # ignored so the excerpt isn't truncated to a tiny fragment.
        text = "a" * 150 + ". " + "b" * 200
        out = _excerpt(text, limit=280)
        self.assertTrue(out.endswith("."))
        self.assertLessEqual(len(out), 280)

    def test_hard_cut_when_no_boundary(self) -> None:
        out = _excerpt("x" * 400, limit=280)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 281)


class BuildDocumentsDossierTest(unittest.TestCase):
    def test_emits_one_dossier_per_lead(self) -> None:
        run = {"id": "run-1", "leads": [_dossier_lead(), _dossier_lead()]}
        docs = K2Backend(api_key="test-key").build_documents(run)
        dossiers = [d for d in docs if d["metadata"].get("evidence_id") == "account-dossier"]
        self.assertEqual(len(dossiers), 2)


class _FakeStore:
    def list_runs(self):  # type: ignore[no-untyped-def]
        return [{"id": "run-1"}]

    def load_run(self, run_id):  # type: ignore[no-untyped-def]
        return {
            "id": "run-1",
            "leads": [
                {
                    "score": {"tier": "A", "total_score": 82, "company": {"company": "Mojio", "domain": "moj.io"}, "classification": {"ai_posture": "none"}},
                    "metadata": {"vertical": "telematics"},
                    "strategy": {"outreach_angle": "telematics data wedge"},
                    "evidence": [{"url": "https://moj.io/about", "text": "Mojio platform"}],
                    "workflow": {"status": "new"},
                },
                {
                    "score": {"tier": "A", "total_score": 78, "company": {"company": "FleetCo", "domain": "fleetco.com"}, "classification": {"ai_posture": "none"}},
                    "metadata": {"vertical": "telematics"},
                    "strategy": {"outreach_angle": "fleet workflow data"},
                    "evidence": [{"url": "https://fleetco.com/about", "text": "FleetCo platform"}],
                    "workflow": {"status": "new"},
                },
                {
                    "score": {"tier": "C", "total_score": 40, "company": {"company": "WidgetCorp", "domain": "widget.com"}, "classification": {"ai_posture": "ai-native"}},
                    "metadata": {"vertical": "martech"},
                    "strategy": {"outreach_angle": "n/a"},
                    "evidence": [],
                    "workflow": {"status": "new"},
                },
            ],
        }


if __name__ == "__main__":
    unittest.main()
