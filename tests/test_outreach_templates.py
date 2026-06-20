from __future__ import annotations

import unittest

from icp_engine.outreach_templates import (
    OUTREACH_TEMPLATES,
    render_template,
    select_template,
)


class SelectTemplateTest(unittest.TestCase):
    def test_persona_match_wins(self) -> None:
        # A CEO/founder title routes to the exec scaffold even with a data signal present.
        template = select_template({"title": "Chief Executive Officer"}, ["data"])
        self.assertEqual(template.name, "exec-ai-urgency")

    def test_persona_beats_signal(self) -> None:
        # Engineering persona + a data signal -> persona routing takes precedence.
        template = select_template({"title": "VP Engineering"}, ["qualified-data"])
        self.assertEqual(template.name, "workflow-efficiency")

    def test_signal_routes_when_persona_is_generic(self) -> None:
        template = select_template({"title": "Operations Lead"}, ["proprietary data"])
        # "operations" is a workflow persona keyword, so it routes there first.
        self.assertEqual(template.name, "workflow-efficiency")

    def test_pure_signal_routing_without_persona_keyword(self) -> None:
        template = select_template({"title": "Buyer"}, ["proprietary data"])
        self.assertEqual(template.name, "data-advantage")

    def test_default_fallback_when_nothing_routes(self) -> None:
        template = select_template({"title": "Buyer"}, [])
        self.assertEqual(template.name, "default")

    def test_none_inputs_fall_back_to_default(self) -> None:
        self.assertEqual(select_template(None, None).name, "default")


class RenderTemplateTest(unittest.TestCase):
    def test_renders_merge_fields(self) -> None:
        template = select_template({"title": "VP Engineering"}, [])
        rendered = render_template(
            template,
            {
                "first_name": "Dana",
                "company": "Acme",
                "evidence_line": "a recent launch post",
                "angle": "Your workflow data is an AI asset.",
                "offer": "a 2-week opportunity map",
            },
        )
        self.assertIn("Acme", rendered["subject"])
        self.assertIn("Dana", rendered["body"])
        self.assertIn("a recent launch post", rendered["body"])
        self.assertTrue(rendered["cta"])

    def test_missing_keys_render_empty_not_raise(self) -> None:
        for template in OUTREACH_TEMPLATES:
            rendered = render_template(template, {"company": "Acme"})
            # No KeyError; unfilled merge fields collapse to empty.
            self.assertIn("Acme", rendered["subject"] + rendered["body"] + rendered["cta"])
            self.assertNotIn("{", rendered["body"])


if __name__ == "__main__":
    unittest.main()
