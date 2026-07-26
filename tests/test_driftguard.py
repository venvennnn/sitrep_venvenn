"""Unit tests for DriftGuard detection + glossary memory (no LLM / network)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from driftguard.detect import detect_findings
from driftguard.extract import extract_metrics_from_fixture
from driftguard.models import GlossaryEntry, MetricMention
from driftguard.normalize import definitions_equivalent, normalize_name
from driftguard.pipeline import run_driftguard_offline
from driftguard.store import GlossaryStore
from driftguard.workspace import resolve_workspace


class NormalizeTests(unittest.TestCase):
    def test_alias_normalization(self):
        self.assertEqual(normalize_name("ARR"), "annual recurring revenue")
        self.assertEqual(normalize_name("weekly actives"), "weekly actives")

    def test_definition_drift_detection(self):
        old = "signup and verifies their email within 24 hours"
        new = "completes onboarding profile and first project"
        self.assertFalse(definitions_equivalent(old, new))
        self.assertTrue(
            definitions_equivalent(
                "users with a session in the last 7 days",
                "Users with at least one session in the last 7 days",
            )
        )


class DetectTests(unittest.TestCase):
    def test_definition_drift_and_confound(self):
        prior = [
            GlossaryEntry(
                metric_id="m1",
                canonical_name="Activation",
                definition="A new user who signs up and verifies their email within 24 hours",
                team="Growth",
                latest_value="45%",
                first_seen_at="2026-03-04T00:00:00+00:00",
                last_seen_at="2026-03-04T00:00:00+00:00",
                meeting_count=1,
            )
        ]
        mentions = [
            MetricMention(
                name="Activation",
                definition="A user who completes onboarding (profile + first project created)",
                value="55%",
                previous_value="45%",
                team="Product",
                speaker="Alex",
            )
        ]
        findings = detect_findings(mentions, prior)
        kinds = {f.kind for f in findings}
        self.assertIn("confounded_value", kinds)
        self.assertIn("cross_team_conflict", kinds)

    def test_intra_meeting_arr_conflict(self):
        mentions = [
            MetricMention(
                name="ARR",
                definition="Includes committed trials",
                value="RM13.1M",
                team="Sales",
            ),
            MetricMention(
                name="ARR",
                definition="Excludes trials",
                value="RM12.4M",
                team="Finance",
            ),
        ]
        findings = detect_findings(mentions, [])
        self.assertTrue(any(f.kind == "cross_team_conflict" for f in findings))


class StorePipelineTests(unittest.TestCase):
    def test_multi_meeting_memory(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GlossaryStore(Path(tmp) / "g.db")
                f1 = json.loads(
                    (ROOT / "fixtures" / "meeting1_growth_standup.json").read_text()
                )
                f2 = json.loads(
                    (ROOT / "fixtures" / "meeting2_product_review.json").read_text()
                )

                r1 = await run_driftguard_offline(
                    summary=f1["summary"],
                    attendees=f1["attendees"],
                    task=f1["task"],
                    fixture_extraction=f1["extraction"],
                    instructions=f1["agent"]["instructions"],
                    store=store,
                )
                self.assertEqual(r1["meta"]["findings"], [])
                self.assertEqual(r1["meta"]["glossary_count"], 1)

                r2 = await run_driftguard_offline(
                    summary=f2["summary"],
                    attendees=f2["attendees"],
                    task=f2["task"],
                    fixture_extraction=f2["extraction"],
                    instructions=f2["agent"]["instructions"],
                    store=store,
                )
                kinds = {f["kind"] for f in r2["meta"]["findings"]}
                # Cross-team conflict is the clearer framing when teams differ;
                # confounded value is the insight that the 45%→55% move isn't real.
                self.assertIn("confounded_value", kinds)
                self.assertIn("cross_team_conflict", kinds)
                self.assertTrue(
                    any(f["metric_name"] == "Activation" for f in r2["meta"]["findings"])
                )
                self.assertTrue(
                    any(f["metric_name"] == "ARR" for f in r2["meta"]["findings"])
                )
                self.assertGreaterEqual(r2["meta"]["glossary_count"], 2)
                self.assertEqual(r2["meta"]["meetings_seen"], 2)
                self.assertTrue(
                    any("Definition drift" in a["content"] for a in r2["artifacts"])
                )

        asyncio.run(_run())

    def test_workspace_from_instructions(self):
        self.assertEqual(
            resolve_workspace(instructions="workspace: acme-corp"),
            "acme-corp",
        )


class ExtractFixtureTests(unittest.TestCase):
    def test_fixture_parse(self):
        payload = json.loads(
            (ROOT / "fixtures" / "meeting2_product_review.json").read_text()
        )
        result = extract_metrics_from_fixture(payload["extraction"])
        self.assertEqual(len(result.metrics), 3)
        self.assertEqual(result.metrics[0].name, "Activation")


if __name__ == "__main__":
    unittest.main()
