from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from icp_engine.k2_workspace import (
    AGENTS,
    FEEDS,
    K2WorkspaceProvisioner,
    build_seeded_workspace_documents,
    build_pipeline_topology,
)
from icp_engine.k2_workspace_status import build_k2_workspace_status, run_k2_pipeline_action


class FakeWorkspaceClient:
    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}
        self.corpora: dict[str, dict[str, Any]] = {}
        self.agents: dict[str, dict[str, Any]] = {}
        self.feeds: dict[str, dict[str, Any]] = {}
        self.pipeline_specs: dict[str, dict[str, Any]] = {}
        self.pipeline_actions: list[dict[str, Any]] = []

    def ensure_project(self, name: str) -> dict[str, Any]:
        return self.projects.setdefault(name, {"id": "project-1", "name": name})

    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return list(self.projects.values())[offset : offset + limit]

    def ensure_corpus(self, project_id: str, name: str, description: str = "") -> dict[str, Any]:
        return self.corpora.setdefault(
            name,
            {"id": f"corpus-{len(self.corpora) + 1}", "name": name, "project_id": project_id, "description": description},
        )

    def list_corpora(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return list(self.corpora.values())[offset : offset + limit]

    def discover_metadata(self, corpus_id: str, *, refresh: bool = False, include: str | None = None) -> dict[str, Any]:
        return {
            "total_documents": 12,
            "total_chunks": 24,
            "fields": [
                {"key": "company"},
                {"key": "domain"},
                {"key": "criteria_hash"},
            ],
        }

    def list_agents(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return list(self.agents.values())[offset : offset + limit]

    def ensure_agent(self, *, project_id: str, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.agents.setdefault(
            name,
            {
                "id": f"agent-{len(self.agents) + 1}",
                "name": name,
                "project_id": project_id,
                "status": "draft",
                **kwargs,
            },
        )

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        for agent in self.agents.values():
            if agent["id"] == agent_id:
                agent["status"] = "active"
                return agent
        raise AssertionError(f"Unknown agent: {agent_id}")

    def list_feeds(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return list(self.feeds.values())[offset : offset + limit]

    def ensure_feed(self, *, project_id: str, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.feeds.setdefault(
            name,
            {
                "id": f"feed-{len(self.feeds) + 1}",
                "name": name,
                "project_id": project_id,
                **kwargs,
            },
        )

    def list_pipeline_specs(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return list(self.pipeline_specs.values())[offset : offset + limit]

    def ensure_pipeline_spec(self, *, project_id: str, name: str, topology: dict[str, Any], description: str = "") -> dict[str, Any]:
        return self.pipeline_specs.setdefault(
            name,
            {
                "id": f"pipeline-{len(self.pipeline_specs) + 1}",
                "name": name,
                "project_id": project_id,
                "description": description,
                "topology": topology,
            },
        )

    def dry_run_pipeline_spec(self, pipeline_spec_id: str, *, sample_input: dict[str, Any] | None = None) -> dict[str, Any]:
        self.pipeline_actions.append({"action": "dry_run", "id": pipeline_spec_id, "sample_input": sample_input})
        return {"valid": True, "issues": [], "simulated_nodes": []}

    def apply_pipeline_spec(self, pipeline_spec_id: str, *, activate_entities: bool = True) -> dict[str, Any]:
        self.pipeline_actions.append({"action": "apply", "id": pipeline_spec_id, "activate_entities": activate_entities})
        return {"created_agent_ids": [], "updated_agent_ids": [], "activate_entities": activate_entities}

    def trigger_pipeline_spec(self, pipeline_spec_id: str) -> dict[str, Any]:
        self.pipeline_actions.append({"action": "trigger", "id": pipeline_spec_id})
        return {"pipeline_run_id": "pipeline-run-1", "child_run_ids": ["job-1"]}

    def backfill_pipeline_spec(self, pipeline_spec_id: str, *, start_from: str) -> dict[str, Any]:
        self.pipeline_actions.append({"action": "backfill", "id": pipeline_spec_id, "start_from": start_from})
        return {"pipeline_run_id": "pipeline-run-2", "start_from": start_from, "layers": []}


class K2WorkspaceTest(unittest.TestCase):
    def test_seeded_workspace_documents_split_into_expected_corpora(self) -> None:
        documents = build_seeded_workspace_documents()

        self.assertEqual(len(documents["source"]), 428)
        self.assertEqual(len(documents["candidate"]), 428)
        # evidence (== research/grounding corpus) carries every doc plus the new
        # per-account dossier (+428): 428 summaries + 428 evidence pages + 428 dossiers.
        self.assertEqual(len(documents["evidence"]), 1284)
        # Seed personas now come from strategy.build_strategy (live parity), which
        # yields 3 base + optional vertical/CEO personas capped at 5 per lead, instead
        # of the old hand-built fixed list. Prospect docs are one-per-persona.
        self.assertEqual(len(documents["prospect"]), 1607)
        self.assertEqual(len(documents["criteria"]), 7)

        for key, docs in documents.items():
            source_uris = [str(doc["sourceUri"]) for doc in docs]
            self.assertEqual(len(source_uris), len(set(source_uris)), key)
            self.assertTrue(all(doc.get("metadata", {}).get("workspace") == "knowledge2-icp" for doc in docs), key)

        self.assertEqual(documents["candidate"][0]["metadata"]["entity_type"], "company")
        self.assertEqual(documents["prospect"][0]["metadata"]["entity_type"], "prospect")
        self.assertIn("Seeded ICP Criteria", documents["criteria"][0]["rawText"])

    def test_provisioner_can_ensure_workspace_primitives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeWorkspaceClient()
            provisioner = K2WorkspaceProvisioner(
                client=client,  # type: ignore[arg-type]
                project_name="Knowledge2 ICP GTM Test",
                summary_path=Path(tmp) / "summary.json",
            )

            summary = provisioner.ensure_workspace(apply_primitives=True)
            status = build_k2_workspace_status(
                client=client,
                project_name="Knowledge2 ICP GTM Test",
                summary_path=Path(tmp) / "missing.json",
            )

        self.assertEqual(summary["project"]["id"], "project-1")
        self.assertEqual(set(summary["corpora"]), {"source", "candidate", "evidence", "prospect", "criteria"})
        self.assertEqual(set(summary["agents"]), {agent["key"] for agent in AGENTS})
        self.assertEqual(set(summary["feeds"]), {feed["key"] for feed in FEEDS})
        self.assertEqual(summary["pipeline_spec"]["name"], "ICP Expansion Pipeline")
        self.assertTrue(all(agent["status"] == "active" for agent in summary["agents"].values()))

        prospect_feed = client.feeds["ICP Prospect Expansion Feed"]
        self.assertEqual(prospect_feed["target_corpus_id"], summary["corpora"]["prospect"]["id"])
        self.assertTrue(prospect_feed["persistent"])
        self.assertTrue(prospect_feed["reactive"])
        self.assertEqual(status["source"], "k2_api")
        self.assertEqual(status["project"]["status"], "found")
        self.assertTrue(all(item["status"] == "found" for item in status["corpora"]))
        self.assertTrue(all(item["health"]["status"] == "ready" for item in status["corpora"]))
        self.assertTrue(all(item["health"]["total_documents"] == 12 for item in status["corpora"]))
        self.assertTrue(all(item["status"] == "active" for item in status["agents"]))
        self.assertTrue(all(item["status"] == "found" for item in status["feeds"]))
        self.assertEqual(status["pipeline_spec"]["status"], "found")

    def test_pipeline_topology_references_existing_entities(self) -> None:
        corpora = {
            "source": {"id": "c-source", "name": "ICP Source Corpus", "description": ""},
            "candidate": {"id": "c-candidate", "name": "ICP Candidate Corpus", "description": ""},
            "evidence": {"id": "c-evidence", "name": "ICP Evidence Corpus", "description": ""},
            "prospect": {"id": "c-prospect", "name": "ICP Prospect Corpus", "description": ""},
            "criteria": {"id": "c-criteria", "name": "ICP Criteria Corpus", "description": ""},
        }
        agents = {agent["key"]: {"id": f"a-{agent['key']}", "name": agent["name"]} for agent in AGENTS}
        feeds = {feed["key"]: {"id": f"f-{feed['key']}", "name": feed["name"]} for feed in FEEDS}

        topology = build_pipeline_topology(corpora, agents, feeds)

        self.assertEqual(len(topology["corpora"]), 5)
        self.assertEqual(len(topology["agents"]), len(AGENTS))
        self.assertEqual(len(topology["feeds"]), len(FEEDS))
        self.assertEqual(topology["metadata"]["purpose"], "scheduled-reactive-icp-expansion")
        self.assertIn("portfolio-expansion", topology["metadata"]["query_profiles"])

    def test_pipeline_action_dispatches_against_workspace_spec(self) -> None:
        client = FakeWorkspaceClient()
        project = client.ensure_project("Knowledge2 ICP GTM Test")
        client.ensure_pipeline_spec(
            project_id=project["id"],
            name="ICP Expansion Pipeline",
            topology={"metadata": {"purpose": "test"}},
            description="K2-native ICP expansion graph.",
        )

        dry_run = run_k2_pipeline_action("dry-run", client=client, project_name="Knowledge2 ICP GTM Test")
        applied = run_k2_pipeline_action("apply", client=client, project_name="Knowledge2 ICP GTM Test", activate_entities=False)
        triggered = run_k2_pipeline_action("trigger", client=client, project_name="Knowledge2 ICP GTM Test")
        backfilled = run_k2_pipeline_action(
            "backfill",
            client=client,
            project_name="Knowledge2 ICP GTM Test",
            start_from="2026-05-01T00:00:00Z",
        )

        self.assertEqual(dry_run["action"], "dry_run")
        self.assertTrue(dry_run["result"]["valid"])
        self.assertFalse(applied["result"]["activate_entities"])
        self.assertEqual(triggered["result"]["pipeline_run_id"], "pipeline-run-1")
        self.assertEqual(backfilled["backfill_start_from"], "2026-05-01T00:00:00Z")
        self.assertEqual([item["action"] for item in client.pipeline_actions], ["dry_run", "apply", "trigger", "backfill"])
        self.assertTrue(all(item["id"] == "pipeline-1" for item in client.pipeline_actions))


if __name__ == "__main__":
    unittest.main()
