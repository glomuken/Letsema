"""UI contract tests use a stub, independent of the persistence implementation."""

import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


class DemoStub:
    def __init__(self):
        self.role = "individual"
        self.actions = []
        self.projects = []
        self.submissions = []

    def switch_role(self, role):
        self.role = role

    @property
    def profile(self):
        return {
            "id": "person", "role": self.role, "name": "Demo user",
            "field": "Design", "area": "Johannesburg", "resume": "",
            "public_enabled": False, "public_token": "demo-token", "points": 0,
        }

    def rows(self, table, **filters):
        if table == "projects":
            return self.projects
        if table == "submissions":
            return self.submissions
        if table == "courses":
            return [{
                "id": "course", "title": "Build a campaign", "field": "Design",
                "brief": "Create a campaign for a community garden.",
                "rubric": [{"criterion": "Evidence", "max_points": 20}],
                "max_points": 20,
            }]
        return []

    def action(self, name, **params):
        self.actions.append((name, params))

    def weekly_digest(self):
        return []

    def public_profile(self, token):
        if token == "demo-token":
            return {"profile": self.profile, "submissions": [], "projects": [], "reviews": []}
        return None


class AppTests(unittest.TestCase):
    def setUp(self):
        backend = types.ModuleType("backend")
        backend.Backend = DemoStub
        backend.DemoBackend = DemoStub
        supabase = types.ModuleType("supabase")
        supabase.create_client = lambda *args: None
        self.modules = patch.dict(sys.modules, {"backend": backend, "supabase": supabase})
        self.env = patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_ANON_KEY": ""})
        self.modules.start()
        self.env.start()
        self.addCleanup(self.modules.stop)
        self.addCleanup(self.env.stop)

    def app(self):
        app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        return app

    def test_demo_and_navigation(self):
        app = self.app()
        self.assertIn("Interactive demo", app.warning[0].value)
        for page in ["NGO opportunities", "My repository", "My profile", "Learn"]:
            app.selectbox[1].select(page).run()
            self.assertFalse(app.exception)
        for role in ["ngo", "company"]:
            app.selectbox[0].select(role).run()
            self.assertFalse(app.exception)
            app.selectbox[1].select("My profile").run()
            self.assertFalse(app.exception)

    def test_learning_simulation_is_labelled_and_passes_rubric_result(self):
        app = self.app()
        app.text_input[0].set_value("Garden campaign")
        app.text_area[0].set_value("I designed a campaign, interviewed users and tested it.")
        app.text_input[1].set_value("https://example.org/project")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        name, params = app.session_state["demo_store"].actions[-1]
        self.assertEqual(name, "submit_learning")
        self.assertEqual(params["assessment"]["points"], 10)
        self.assertIn("Demo assessment", params["assessment"]["feedback"])

    def test_missing_evidence_is_not_submitted(self):
        app = self.app()
        app.button[0].click().run()
        self.assertFalse(app.session_state["demo_store"].actions)
        self.assertIn("written evidence", app.error[0].value)

    def test_pending_assessment_can_retry_saved_evidence(self):
        app = self.app()
        app.session_state["demo_store"].submissions = [{
            "id": "pending", "course_id": "course", "assessment": None,
            "title": "Saved campaign", "description": "Saved evidence",
            "artifact_url": "https://example.org/saved",
        }]
        app.run()
        self.assertTrue(app.text_input[0].disabled)
        self.assertTrue(app.text_area[0].disabled)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        _, params = app.session_state["demo_store"].actions[-1]
        self.assertEqual(params["description"], "Saved evidence")

    def test_public_portfolio_needs_no_authentication(self):
        app = AppTest.from_file(APP)
        app.query_params["profile"] = "demo-token"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.header[0].value, "Demo user")
        self.assertFalse(app.selectbox)

    def test_revoked_or_unknown_portfolio_is_unavailable(self):
        app = AppTest.from_file(APP)
        app.query_params["profile"] = "unknown"
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("unavailable", app.info[0].value)

    def test_payment_forms_accept_confirmation_on_submit(self):
        for status, action in [("draft", "record_platform_fee"), ("delivered", "complete_project")]:
            with self.subTest(status=status):
                app = self.app()
                app.session_state["demo_store"].projects = [{
                    "id": "project", "ngo_id": "person", "title": "Campaign",
                    "brief": "Build a campaign", "budget": 1000, "platform_fee": 100,
                    "status": status,
                }]
                app.selectbox[0].select("ngo").run()
                self.assertFalse(app.button[-1].disabled)
                app.button[-1].click().run()
                self.assertFalse(app.session_state["demo_store"].actions)
                self.assertIn("Confirm", app.error[0].value)
                app.text_input[-1].set_value("MANUAL-DEMO-REFERENCE")
                if status == "delivered":
                    app.text_area[-1].set_value("Useful work delivered.")
                app.checkbox[-1].check()
                app.button[-1].click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["demo_store"].actions[-1][0], action)


if __name__ == "__main__":
    unittest.main()
