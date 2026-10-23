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
        for missing in (None, "", "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                b.action("pitch", project_id=project["id"], message="Ready", media_url=missing)
        self.assertEqual(b.rows("pitches"), [])
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
        delivered = b.rows("projects", id=project["id"])[0]
        self.assertEqual(delivered["delivery_description"], "Delivered")
        self.assertEqual(delivered["delivery_url"], "https://example.com/delivery")
        self.assertEqual(len(b.rows("submissions")), 1)
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
        self.assertEqual(public["projects"][0]["delivery_url"], "https://example.com/delivery")
        self.assertEqual(public["projects"][0]["artifact_url"], "https://example.com/delivery")
        b.switch_role("company")
        self.assertNotIn("delivery_url", b.rows("projects", id=project["id"])[0])
        self.assertEqual(b.rows("submissions"), [])
        self.assertEqual(b.rows("reviews"), [])

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
                        assessment((True, 40, 20)), {"scores": []}, {"scores": [None, None, None]}):
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
        retry = b.action("submit_learning", course_id="campaign-basics", title="Title",
                         description="Description", points=99999)
        self.assertEqual(retry["id"], row["id"])
        self.assertEqual(len(b.rows("submissions")), 1)
        with self.assertRaises(ValueError):
            b.action("submit_learning", course_id="campaign-basics", title="Different",
                     description="Description")
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

    def test_reviews_private_to_parties_and_public_only_with_consent(self):
        b = self.backend
        b._insert("reviews", project_id=b._data["projects"][0]["id"],
                  applicant_id="individual", ngo_id="ngo", rating=5, body="Private review")
        token = b.profile["public_token"]
        self.assertEqual(len(b.rows("reviews")), 1)
        self.assertEqual(len(b.public_profile(token)["reviews"]), 1)
        b.action("update_profile", public_enabled=False)
        self.assertEqual(len(b.rows("reviews")), 1)
        self.assertIsNone(b.public_profile(token))
        b.switch_role("ngo")
        self.assertEqual(len(b.rows("reviews")), 1)
        b.switch_role("company")
        self.assertEqual(b.rows("reviews"), [])
        self.assertEqual(b.rows("reviews", applicant_id="individual"), [])
        self.assertIsNone(b.public_profile(token))


class AdapterTests(unittest.TestCase):
    def test_project_rows_include_authorized_delivery_fields(self):
        class Query:
            def __init__(self, client, table):
                self.client, self.table = client, table
            def select(self, columns):
                self.client.selections[self.table] = columns
                return self
            def eq(self, key, value):
                return self
            def in_(self, key, values):
                self.client.delivery_filter = (key, values)
                return self
            def execute(self):
                records = ([{"id": "project", "status": "delivered"}] if self.table == "projects" else
                           [{"project_id": "project", "description": "Delivered evidence",
                             "artifact_url": "https://example.com/delivery"}])
                return type("Response", (), {"data": records})()
        class Client:
            def __init__(self):
                self.selections = {}
            def table(self, name):
                return Query(self, name)
        client = Client()
        backend = Backend(client)
        project = backend.rows("projects", ngo_id="ngo")[0]
        self.assertEqual(project["delivery_description"], "Delivered evidence")
        self.assertEqual(project["delivery_url"], "https://example.com/delivery")
        self.assertEqual(client.delivery_filter, ("project_id", ["project"]))
        self.assertNotIn("payment_reference", client.selections["projects"])

    def test_grading_identity_comes_from_authenticated_user(self):
        class Auth:
            def get_user(self):
                user = type("User", (), {"id": "verified-applicant"})()
                return type("Response", (), {"user": user})()
        class Client:
            auth = Auth()
            def table(self, name):
                self.table_name = name
                return self
            def select(self, columns):
                return self
            def eq(self, key, value):
                self.identity_filter = (key, value)
                return self
            def execute(self):
                return type("Response", (), {"data": [{"id": "verified-applicant"}]})()
        class Grader:
            def rpc(self, name, params):
                self.call = (name, params)
                return self
            def execute(self):
                return type("Response", (), {"data": {"id": "submission", "points": 100}})()
        client, grader = Client(), Grader()
        backend = Backend(client, grading_client=grader)
        backend.grade_submission("submission", assessment())
        self.assertEqual(client.identity_filter, ("id", "verified-applicant"))
        self.assertEqual(grader.call[1]["applicant_id"], "verified-applicant")
        self.assertIs(backend.grading_client, grader)

    def test_trusted_server_grading_alias(self):
        class Client:
            def rpc(self, name, params=None):
                self.last = (name, params)
                return self
            def execute(self):
                return type("Response", (), {"data": {"id": "submission", "points": 0}})()
        class TrustedBackend(Backend):
            def grade_submission(self, submission_id, result):
                self.graded = (submission_id, result)
                return {"id": submission_id, "points": 100}
        backend = TrustedBackend(Client(), grading_client=Client())
        result = backend.action("submit_learning", course_id="course", assessment=assessment())
        self.assertEqual(result["points"], 100)
        self.assertEqual(backend.graded[0], "submission")
        self.assertNotIn("assessment", backend.client.last[1]["payload"])

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
