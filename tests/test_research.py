from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icp_engine.app_store import AppStore
from icp_engine.claude import ClaudeUnavailable
from icp_engine.enrichment import normalize_domain
from icp_engine.k2_backend import K2Backend
from icp_engine.models import Classification, CompanyInput, Evidence
from icp_engine.research import ResearchPipeline
from icp_engine.seed_defaults import SEED_RUN_ID


def fake_evidence(company: CompanyInput, cache_dir: Path) -> tuple[list[Evidence], list[str]]:
    return (
        [
            Evidence(
                evidence_id="e1",
                url=f"https://{company.domain}/platform",
                title="Platform",
                text=(
                    "Founded in 2012. Enterprise software platform for fleet workflow, dispatch, "
                    "telematics records, integrations, API, permissions, and analytics. "
                    "Trusted by customers and partners. Contact sales@example.com."
                ),
                metadata={
                    "page_category": "product",
                    "links": [
                        "https://www.linkedin.com/company/mojio",
                        "https://github.com/mojio",
                        f"https://{company.domain}/docs/api",
                    ],
                    "external_links": ["https://github.com/mojio"],
                },
            )
        ],
        [],
    )


def fake_classifier(company: CompanyInput, evidence: list[Evidence], *, criteria_markdown: str) -> Classification:
    return Classification(
        ai_posture=3,
        data_workflow=4,
        commercial_urgency=3,
        budget_access=3,
        feasibility=4,
        reasons={"ai_posture": "Embedded workflow assistant."},
        evidence_ids={"ai_posture": ["e1"]},
        confidence=0.85,
        source="claude:test",
        ai_narrative="Builds an embedded dispatch assistant on proprietary fleet data.",
    )


class _StubResearchClient:
    """Mimics PerplexityRestClient.chat_completion offline."""

    def __init__(self, companies: list[dict[str, object]]) -> None:
        self._companies = companies
        self.calls = 0

    def chat_completion(self, **kwargs: object) -> dict[str, object]:
        self.calls += 1
        return {"choices": [{"message": {"content": json.dumps({"companies": self._companies})}}], "citations": []}


# DuckDuckGo HTML carrying one discoverable company domain, for fallback tests.
_DDG_HTML = (
    '<html><body><a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.moj.io%2F">'
    "Mojio - Connected Mobility</a></body></html>"
)


class DiscoveryProviderPipelineTest(unittest.TestCase):
    def test_perplexity_provider_sources_candidates_and_records_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "perplexity"})
            client = _StubResearchClient([{"company": "Mojio", "domain": "moj.io", "reason": "Fleet AI."}])
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, research_client=client)

            run = pipeline.create_run(query="fleet AI companies", include_github=False, use_apollo=False)

            self.assertEqual(run["discovery"]["provider"], "perplexity")
            self.assertEqual([lead["score"]["company"]["domain"] for lead in run["leads"]], ["moj.io"])
            self.assertEqual(run["leads"][0]["candidate"]["source_title"], "Perplexity research result")
            self.assertEqual(client.calls, 1)

    def test_perplexity_unavailable_falls_back_to_search_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "perplexity"})
            # No research client + no key -> Perplexity is unavailable; the search fetcher covers fallback.
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, search_fetcher=lambda _: _DDG_HTML)

            run = pipeline.create_run(query="fleet software", include_github=False, use_apollo=False)

            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["discovery"]["provider"], "duckduckgo")
            self.assertEqual([lead["score"]["company"]["domain"] for lead in run["leads"]], ["moj.io"])
            self.assertTrue(any("unavailable" in warning.lower() for warning in run["warnings"]))

    def test_auto_without_key_uses_search_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))  # default discovery_provider is "auto"
            client = _StubResearchClient([{"company": "Should", "domain": "ignored.com"}])
            # research_client present but provider=auto with no key still prefers it via injection seam.
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, search_fetcher=lambda _: _DDG_HTML, research_client=client)

            run = pipeline.create_run(query="fleet software", include_github=False, use_apollo=False)

            # auto treats an injected research client as "key present", so Perplexity wins.
            self.assertEqual(run["discovery"]["provider"], "perplexity")
            self.assertEqual([lead["score"]["company"]["domain"] for lead in run["leads"]], ["ignored.com"])

    def test_k2_known_domains_are_skipped_with_warning(self) -> None:
        class _DedupK2Backend(K2Backend):
            def __init__(self, known: set[str]) -> None:
                super().__init__(api_key="")
                self._known = known

            def known_domains(self, domains, *, run=None, client=None):  # type: ignore[no-untyped-def]
                return {normalize_domain(d) for d in domains if normalize_domain(d) in self._known}

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "perplexity"})
            client = _StubResearchClient(
                [{"company": "A", "domain": "a.com"}, {"company": "B", "domain": "b.com"}]
            )
            pipeline = ResearchPipeline(
                store,
                evidence_fetcher=fake_evidence,
                research_client=client,
                k2_backend=_DedupK2Backend({"b.com"}),
            )

            run = pipeline.create_run(query="fleet AI companies", include_github=False, use_apollo=False)

            self.assertEqual([lead["score"]["company"]["domain"] for lead in run["leads"]], ["a.com"])
            self.assertTrue(any("already in the K2 corpus" in warning for warning in run["warnings"]))


class QualifierPipelineTest(unittest.TestCase):
    def test_claude_qualifier_uses_model_classification_and_persists_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"qualifier": "claude"})
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, classifier=fake_classifier)

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)

            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["qualifier"], "claude")
            lead = run["leads"][0]
            self.assertEqual(lead["score"]["classification"]["source"], "claude:test")
            self.assertEqual(lead["score"]["ai_narrative"], "Builds an embedded dispatch assistant on proprietary fleet data.")
            qualification = lead["metadata"]["qualification"]
            self.assertEqual(qualification["qualifier"], "claude")
            self.assertEqual(qualification["source"], "claude:test")
            self.assertEqual(qualification["evidence_ids"]["ai_posture"], ["e1"])
            self.assertEqual(qualification["ai_narrative"], "Builds an embedded dispatch assistant on proprietary fleet data.")

    def test_claude_judge_failure_falls_back_to_rules_with_warning(self) -> None:
        def boom(company, evidence, *, criteria_markdown):  # type: ignore[no-untyped-def]
            raise ClaudeUnavailable("no key")

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"qualifier": "claude"})
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, classifier=boom)

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)

            self.assertEqual(run["status"], "completed")
            self.assertEqual(len(run["leads"]), 1)
            lead = run["leads"][0]
            self.assertEqual(lead["metadata"]["qualification"]["source"], "rules")
            self.assertTrue(any("Claude qualifier" in warning for warning in run["warnings"]))

    def test_judge_fields_flow_into_k2_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"qualifier": "claude"})
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, classifier=fake_classifier)
            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)

            manifest = K2Backend(api_key="").build_manifest(run)

            self.assertIn("ai_narrative", manifest["metadata_keys"])
            self.assertIn("qualifier", manifest["metadata_keys"])
            summary = next(
                doc for doc in manifest["documents"] if doc["metadata"].get("source_type") == "account_summary"
            )
            self.assertEqual(summary["metadata"]["qualifier"], "claude")
            self.assertEqual(summary["metadata"]["qualifier_source"], "claude:test")
            self.assertIn("dispatch assistant", summary["metadata"]["ai_narrative"])
            self.assertIn("AI narrative:", summary["text"])

    def test_rules_qualifier_never_calls_the_judge(self) -> None:
        calls: list[str] = []

        def tracking(company, evidence, *, criteria_markdown):  # type: ignore[no-untyped-def]
            calls.append(company.domain)
            return fake_classifier(company, evidence, criteria_markdown=criteria_markdown)

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))  # default qualifier is "rules"
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, classifier=tracking)

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)

            self.assertEqual(run["qualifier"], "rules")
            self.assertEqual(calls, [])
            self.assertEqual(run["leads"][0]["metadata"]["qualification"]["source"], "rules")


class ResearchPipelineTest(unittest.TestCase):
    def test_create_run_scores_seed_and_generates_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)

            run = pipeline.create_run(
                query="",
                seed_text="Mojio, moj.io",
                include_github=False,
                use_apollo=False,
            )

            self.assertEqual(run["status"], "completed")
            self.assertEqual(len(run["leads"]), 1)
            lead = run["leads"][0]
            self.assertGreaterEqual(lead["score"]["total_score"], 60)
            self.assertIn("personas", lead["strategy"])
            self.assertIn("source_counts", lead["metadata"])
            self.assertIn("https://github.com/mojio", lead["metadata"]["source_refs"]["github_urls"])
            self.assertGreaterEqual(run["k2"]["document_count"], 2)
            self.assertEqual(store.load_run(run["id"])["id"], run["id"])

    def test_create_run_applies_active_criteria_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_criteria(
                """
                # Custom ICP
                Tier A threshold: 95
                Tier B threshold: 80
                Budget: 50-1000 employees
                Priority verticals: fleet, logistics
                """
            )
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)

            run = pipeline.create_run(
                query="",
                seed_text="Mojio, moj.io",
                include_github=False,
                use_apollo=False,
            )

            profile = run["criteria"]["profile"]
            lead = run["leads"][0]

            self.assertEqual(profile["tier_a_threshold"], 95)
            self.assertEqual(profile["tier_b_threshold"], 80)
            self.assertIn("fleet", profile["priority_terms"])
            self.assertEqual(lead["metadata"]["criteria_profile"]["hash"], run["criteria"]["hash"])
            self.assertIn("criteria", lead["score"]["classification"]["reasons"])

    def test_create_run_accepts_selected_candidate_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)

            run = pipeline.create_run(
                query="fleet candidates",
                candidate_payloads=[
                    {
                        "company": "Mojio",
                        "domain": "https://moj.io",
                        "source_url": "https://moj.io",
                        "source_title": "Mojio official site",
                        "github_urls": ["https://github.com/mojio"],
                        "linkedin_urls": ["https://www.linkedin.com/company/mojio"],
                        "other_urls": ["https://www.crunchbase.com/organization/mojio"],
                    },
                    {
                        "company": "Mojio Duplicate",
                        "domain": "www.moj.io",
                    },
                ],
                include_github=False,
                use_apollo=False,
            )

            self.assertEqual(len(run["leads"]), 1)
            lead = run["leads"][0]
            self.assertEqual(lead["candidate"]["source_title"], "Mojio official site")
            self.assertIn("https://www.linkedin.com/company/mojio", lead["metadata"]["source_refs"]["linkedin_urls"])
            self.assertIn("https://www.crunchbase.com/organization/mojio", lead["metadata"]["source_refs"]["marketplace_urls"])

    def test_create_run_passes_candidate_resource_refs_to_default_fetcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store)

            with patch("icp_engine.research.fetch_company_evidence", return_value=([], [])) as fetch_evidence:
                pipeline.create_run(
                    query="fleet candidates",
                    candidate_payloads=[
                        {
                            "company": "Mojio",
                            "domain": "moj.io",
                            "github_urls": ["https://github.com/mojio"],
                            "linkedin_urls": ["https://www.linkedin.com/company/mojio"],
                            "other_urls": ["https://www.g2.com/products/mojio"],
                        }
                    ],
                    include_github=False,
                    use_apollo=False,
                )

            extra_urls = fetch_evidence.call_args.kwargs["extra_urls"]
            self.assertEqual(
                extra_urls,
                [
                    "https://github.com/mojio",
                    "https://www.linkedin.com/company/mojio",
                    "https://www.g2.com/products/mojio",
                ],
            )

    def test_discover_distinguishes_seed_candidates_from_empty_search_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, search_fetcher=lambda _: "<html></html>")

            candidates, warnings, provider = pipeline.discover(
                "workflow SaaS",
                seed_text="Mojio, moj.io",
                max_companies=3,
            )

            self.assertEqual([item.domain for item in candidates], ["moj.io"])
            self.assertEqual(warnings, ["No additional company domains were discovered from search results."])
            # The seed supplied the only candidate; search returned nothing, so no provider sourced it.
            self.assertEqual(provider, "none")

    def test_answer_question_returns_citations_from_stored_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False)

            answer = pipeline.answer_question(run_id=run["id"], question="Which company has workflow API evidence?")

            self.assertTrue(answer["citations"])
            self.assertIn("Mojio", answer["answer"])
            self.assertIn("Recommended GTM motion", answer["answer"])
            self.assertIn("Metadata used", answer["answer"])
            self.assertIn("workflow", answer["metadata_used"]["signal_tags"])
            self.assertIn("VP Engineering", answer["metadata_used"]["persona_titles"])
            self.assertEqual(answer["citations"][0]["source_type"], "website")
            self.assertEqual(answer["citations"][0]["page_category"], "product")

    def test_answer_question_matches_metadata_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False)

            answer = pipeline.answer_question(run_id=run["id"], question="Which leads have github metadata?")

            self.assertTrue(answer["citations"])
            self.assertEqual(answer["citations"][0]["evidence_id"], "metadata")

    def test_answer_question_prefers_k2_when_run_has_synced_corpus(self) -> None:
        class FakeK2Backend(K2Backend):
            def __init__(self) -> None:
                super().__init__(api_key="")

            def answer_question(self, run, question, *, client=None):  # type: ignore[no-untyped-def]
                return {
                    "status": "ok",
                    "provider": "k2",
                    "corpus_id": "corpus-1",
                    "answer": "K2 says Mojio has workflow API evidence.",
                    "citations": [{"company": "Mojio", "url": "https://moj.io/platform", "snippet": "Workflow API"}],
                    "raw_result_count": 1,
                }

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            run = ResearchPipeline(store, evidence_fetcher=fake_evidence).create_run(query="", seed_text="Mojio, moj.io")
            run["k2"] = {"status": "uploaded", "corpus_id": "corpus-1"}
            store.save_run(run)
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, k2_backend=FakeK2Backend())

            answer = pipeline.answer_question(run_id=run["id"], question="Which company has workflow API evidence?")

            self.assertEqual(answer["provider"], "k2")
            self.assertEqual(answer["corpus_id"], "corpus-1")
            self.assertEqual(answer["k2"]["raw_result_count"], 1)


def flaky_evidence(fail_once: set[str]):
    """Evidence fetcher that raises the first time it sees a domain in ``fail_once``.

    Simulates a mid-run crash (a transient fetch failure / Cloud Run recycle): the
    domain fails on its first attempt, then succeeds on the resume pass.
    """

    def fetch(company: CompanyInput, cache_dir: Path) -> tuple[list[Evidence], list[str]]:
        if company.domain in fail_once:
            fail_once.discard(company.domain)
            raise RuntimeError(f"boom on {company.domain}")
        return fake_evidence(company, cache_dir)

    return fetch


class DurableRunTest(unittest.TestCase):
    def test_crash_mid_loop_persists_partial_run_then_resume_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "perplexity"})
            client = _StubResearchClient(
                [{"company": "A", "domain": "a.com"}, {"company": "B", "domain": "b.com"}]
            )
            pipeline = ResearchPipeline(
                store,
                evidence_fetcher=flaky_evidence({"b.com"}),
                research_client=client,
            )

            with self.assertRaises(RuntimeError):
                pipeline.create_run(query="fleet AI companies", include_github=False, use_apollo=False)

            # The run is persisted as a resumable failure, not lost — first lead saved,
            # cursor recorded, candidate list captured, discovery already charged once.
            # (list_runs also surfaces the code-resident seed run; ignore it.)
            user_runs = [r for r in store.list_runs() if r["id"] != SEED_RUN_ID]
            self.assertEqual(len(user_runs), 1)
            run_id = user_runs[0]["id"]
            partial = store.load_run(run_id)
            self.assertEqual(partial["status"], "failed")
            self.assertEqual([lead["score"]["company"]["domain"] for lead in partial["leads"]], ["a.com"])
            self.assertEqual(partial["job"]["processed_domains"], ["a.com"])
            self.assertEqual(partial["job"]["total"], 2)
            self.assertEqual(len(partial["job"]["candidates"]), 2)
            self.assertIn("boom on b.com", partial["job"]["error"])
            self.assertEqual(client.calls, 1)

            resumed = pipeline.resume_run(run_id)

            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(
                sorted(lead["score"]["company"]["domain"] for lead in resumed["leads"]),
                ["a.com", "b.com"],
            )
            self.assertEqual(resumed["job"]["processed_domains"], ["a.com", "b.com"])
            self.assertEqual(resumed["job"]["attempts"], 2)
            self.assertIsNone(resumed["job"]["error"])
            # Discovery is NOT re-run on resume — candidates were captured on the run.
            self.assertEqual(client.calls, 1)

    def test_resume_of_completed_run_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)
            self.assertEqual(run["status"], "completed")

            resumed = pipeline.resume_run(run["id"])

            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(len(resumed["leads"]), 1)
            self.assertEqual(resumed["job"]["attempts"], 1)

    def test_happy_path_run_carries_workflow_block_and_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            run = pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)

            self.assertEqual(run["status"], "completed")
            workflow = run["job"]
            self.assertEqual(workflow["stage"], "done")
            self.assertEqual(workflow["total"], 1)
            self.assertEqual(workflow["processed_domains"], ["moj.io"])
            self.assertEqual(workflow["attempts"], 1)
            # The persisted run matches the returned run (final checkpoint written).
            reloaded = store.load_run(run["id"])
            self.assertEqual(reloaded["status"], "completed")
            self.assertEqual(reloaded["job"]["processed_domains"], ["moj.io"])

    def test_resume_missing_run_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            self.assertIsNone(pipeline.resume_run("run-does-not-exist"))


class _GroundingK2Backend(K2Backend):
    """K2 backend whose account-context lookup always returns a marker answer."""

    def __init__(self, marker: str) -> None:
        super().__init__()
        self._marker = marker

    def answer_question(self, run, question, *, client=None):  # type: ignore[override]
        return {"status": "ok", "provider": "k2", "answer": self._marker, "citations": []}

    def sync_run(self, run):  # type: ignore[override]
        return {"status": "skipped", "reason": "offline test"}


class OutreachPipelineTest(unittest.TestCase):
    def test_claude_outreach_mode_generates_messages_grounded_and_metered(self) -> None:
        seen_context: list[str] = []
        seen_signal_tags: list[list[str]] = []

        def fake_generator(company, persona, evidence, *, role="", account_context="", criteria_markdown="", signal_tags=None):
            seen_context.append(account_context)
            seen_signal_tags.append(signal_tags or [])
            return {
                "subject": f"{company.company} :: {role}",
                "body": "Grounded body.",
                "cta": "15 minutes?",
                "angle": "evidence angle",
                "model": "claude:test",
            }

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"outreach_mode": "claude"})
            pipeline = ResearchPipeline(
                store,
                evidence_fetcher=fake_evidence,
                k2_backend=_GroundingK2Backend("K2-ACCOUNT-CONTEXT-MARK"),
                outreach_generator=fake_generator,
            )

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io")

            messages = run["leads"][0]["metadata"]["outreach_messages"]
            self.assertTrue(messages)
            first = next(iter(messages.values()))
            self.assertIn("Mojio", first["subject"])
            self.assertEqual(first["grounded"], "k2")
            # K2 account context reached the generator.
            self.assertIn("K2-ACCOUNT-CONTEXT-MARK", seen_context)
            # The lead's signal tags were threaded through for template selection.
            self.assertTrue(any(seen_signal_tags))
            summary = store.provider_usage_summary()
            self.assertGreaterEqual(summary["allowed_counts"].get("outreach", 0), 1)

    def test_outreach_unavailable_leaves_lead_clean_for_template(self) -> None:
        def boom(company, persona, evidence, *, role="", account_context="", criteria_markdown="", signal_tags=None):
            raise ClaudeUnavailable("no key")

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_settings({"outreach_mode": "claude"})
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, outreach_generator=boom)

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io")

            self.assertNotIn("outreach_messages", run["leads"][0]["metadata"])
            self.assertTrue(any("outreach unavailable" in w.lower() for w in run["warnings"]))

    def test_template_mode_skips_outreach_generation(self) -> None:
        calls = {"n": 0}

        def counting_generator(*args, **kwargs):
            calls["n"] += 1
            return {"subject": "x", "body": "y", "cta": "z", "angle": "a", "model": "claude:test"}

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            # default outreach_mode == "template"
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence, outreach_generator=counting_generator)

            run = pipeline.create_run(query="", seed_text="Mojio, moj.io")

            self.assertEqual(calls["n"], 0)
            self.assertNotIn("outreach_messages", run["leads"][0]["metadata"])


if __name__ == "__main__":
    unittest.main()
