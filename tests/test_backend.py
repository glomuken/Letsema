import unittest

from backend import Backend, DemoBackend


def assessment(points=(40, 40, 20)):
    return {"scores": [{"criterion": c, "score": p, "feedback": "Useful work"}
                       for c, p in zip(("Clarity", "Impact", "Feasibility"), points)],
            "feedback": "Strong campaign", "points": 999999}


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.backend = DemoBackend()

    def learn(self):
        return self.backend.action("submit_learning", course_id="campaign-basics", title="Campaign",
                                   description="A practical community campaign",
                                   artifact_url="https://example.com/campaign", assessment=assessment())

    def test_full_project_workflow_and_safe_portfolio(self):
        b = self.backend
        project = b.rows("projects")[0]
        with self.assertRaises(ValueError):
            b.action("pitch", project_id=project["id"], message="Ready")
        submission = self.learn()
        self.assertEqual(submission["points"], 100)
        self.assertEqual(b.profile["points"], 100)
        b.action("pitch", project_id=project["id"], message="Ready", media_url="https://example.com/pitch")
        with self.assertRaises(ValueError):
            b.action("pitch", project_id=project["id"], message="Duplicate")
        b.switch_role("ngo")
        b.action("assign_project", project_id=project["id"], applicant_id="individual")
        with self.assertRaises(ValueError):
            b.action("complete_project", project_id=project["id"], payment_reference="Manual only",
                     rating=5, body="Good")
        b.switch_role("individual")
        with self.assertRaises(ValueError):
            b.action("deliver_project", project_id=project["id"], description="Delivered", artifact_url="")
        delivery = b.action("deliver_project", project_id=project["id"], description="Delivered",
                            artifact_url="https://example.com/delivery")
        self.assertEqual(delivery["points"], 0)
        b.switch_role("ngo")
        review = b.action("complete_project", project_id=project["id"], payment_reference="Manual only",
                          rating=5, body="Excellent")
        self.assertEqual(review["rating"], 5)
        with self.assertRaises(ValueError):
            b.action("complete_project", project_id=project["id"], payment_reference="Again",
                     rating=5, body="Duplicate")
        b.switch_role("individual")
        public = b.public_profile(b.profile["public_token"])
        self.assertEqual(len(public["submissions"]), 2)
        self.assertEqual(len(public["reviews"]), 1)
        self.assertNotIn("payment_reference", str(public))
        self.assertNotIn("fee_reference", str(public))
        self.assertNotIn("pitches", public)
        self.assertNotIn("public_token", public["profile"])
        self.assertEqual(public["projects"][0]["status"], "complete")

    def test_isolation_copying_and_role_permissions(self):
        self.learn()
        self.assertEqual(DemoBackend().profile["points"], 0)
        copied = self.backend.profile
        copied["points"] = 9000
        self.assertEqual(self.backend.profile["points"], 100)
        for action, params in [
            ("create_profile", {"role": "company"}),
            ("create_project", {"title": "Denied"}),
            ("subscribe", {"field": "Digital marketing", "area": "Johannesburg"}),
        ]:
            with self.assertRaises((ValueError, PermissionError)):
                self.backend.action(action, **params)
        with self.assertRaises(PermissionError):
            self.backend.weekly_digest()
        with self.assertRaises(ValueError):
            self.backend.switch_role("admin")
        self.backend.action("update_profile", role="company", points=999999)
        self.assertEqual(self.backend.profile["role"], "individual")
        self.assertEqual(self.backend.profile["points"], 100)

    def test_rubric_validation_and_no_duplicate_points(self):
        for invalid in (assessment((41, 40, 20)), assessment((-1, 40, 20)),
                        assessment((True, 40, 20)), {"scores": []}):
            with self.assertRaises(ValueError):
                self.backend.action("submit_learning", course_id="campaign-basics", title="Title",
                                    description="Description", assessment=invalid)
        self.assertEqual(self.backend.rows("submissions"), [])
        self.learn()
        with self.assertRaises(ValueError):
            self.learn()
        self.assertEqual(self.backend.profile["points"], 100)

    def test_pending_grading_once(self):
        b = self.backend
        row = b.action("submit_learning", course_id="campaign-basics", title="Title",
                       description="Description", points=99999)
        self.assertEqual(row["points"], 0)
        b.grade_submission(row["id"], assessment())
        with self.assertRaises(ValueError):
            b.grade_submission(row["id"], assessment())
        self.assertEqual(b.profile["points"], 100)

    def test_digest_snapshot_and_consent(self):
        b = self.backend
        b.switch_role("company")
        sub = b.action("subscribe", field="Digital marketing", area="Johannesburg")
        first = b.weekly_digest()
        self.assertEqual(len(first[0]["talent"]), 1)
        b.switch_role("individual")
        self.learn()
        b.switch_role("company")
        self.assertEqual(first, b.weekly_digest())
        b.switch_role("individual")
        token = b.profile["public_token"]
        b.action("update_profile", public_enabled=False)
        self.assertIsNone(b.public_profile(token))
        self.assertIsNone(b.public_profile("guess"))
        b.switch_role("company")
        self.assertEqual(b.weekly_digest()[0]["talent"], [])
        b.action("unsubscribe", subscription_id=sub["id"])
        self.assertEqual(b.weekly_digest(), [])

    def test_private_rows_and_owner_checks(self):
        b = self.backend
        b.switch_role("ngo")
        draft = b.action("create_project", title="Private", field="Digital marketing", area="Johannesburg",
                         brief="A brief", budget=19.99, min_points=0)
        self.assertEqual(draft["platform_fee"], 2.0)
        b._data["projects"][0]["ngo_id"] = "different-ngo"
        with self.assertRaises(PermissionError):
            b.action("assign_project", project_id=b._data["projects"][0]["id"], applicant_id="individual")
        b.switch_role("individual")
        self.assertEqual(len(b.rows("projects")), 1)
        self.assertEqual(b.rows("profiles")[0]["id"], "individual")
        self.assertNotIn("fee_reference", b.rows("projects")[0])
        with self.assertRaises(PermissionError):
            b.action("record_platform_fee", project_id=draft["id"], reference="fake")
        with self.assertRaises(ValueError):
            b.action("submit_learning", course_id="campaign-basics", title="Title",
                     description="Description", artifact_url="javascript:alert(1)")


class AdapterTests(unittest.TestCase):
    def test_strip_untrusted_assessment(self):
        class Response:
            data = {"id": "submission", "points": 0}
        class Client:
            def rpc(self, name, params=None):
                self.last = (name, params)
                return self
            def execute(self):
                return Response()
        client = Client()
        backend = Backend(client)
        result = backend.action("submit_learning", course_id="course", assessment=assessment(), points=999)
        self.assertEqual(result["points"], 0)
        self.assertNotIn("assessment", client.last[1]["payload"])
        with self.assertRaises(PermissionError):
            backend.grade_submission("submission", assessment())
        with self.assertRaises(ValueError):
            backend.rows("auth.users")


if __name__ == "__main__":
    unittest.main()
