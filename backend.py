"""Supabase adapter and isolated, session-local demonstration backend."""
from __future__ import annotations

import copy
import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4


ROLES = {"individual", "ngo", "company"}
TABLES = {"profiles", "courses", "submissions", "projects", "pitches", "reviews", "subscriptions"}


class Backend:
    """Use an authenticated client; never expose ``service_client`` to browsers."""

    def __init__(self, client, service_client=None):
        self.client = client
        self.service_client = service_client

    @property
    def profile(self):
        user = self.client.auth.get_user().user
        if not user:
            return None
        records = self.rows("profiles", id=user.id)
        return records[0] if records else None

    def rows(self, table, **filters):
        if table not in TABLES:
            raise ValueError("Unknown table")
        columns = ("id,ngo_id,title,field,area,brief,budget,min_points,platform_fee,"
                   "fee_status,status,assigned_to,created_at") if table == "projects" else "*"
        query = self.client.table(table).select(columns)
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.execute().data or []

    def action(self, name, **params):
        # Assessment is untrusted input. Only the service-role grading RPC awards points.
        if name == "submit_learning":
            params.pop("assessment", None)
        return self.client.rpc("letsema_action", {
            "action_name": name, "payload": params,
        }).execute().data

    def grade_submission(self, submission_id, assessment):
        if self.service_client is None:
            raise PermissionError("Trusted server-side grading is not configured")
        # The RPC validates that this submission belongs to the logged-in caller.
        profile = self.profile
        if not profile:
            raise PermissionError("Create a profile first")
        return self.service_client.rpc("grade_submission", {
            "submission_id": submission_id, "applicant_id": profile["id"],
            "assessment": assessment,
        }).execute().data

    def public_profile(self, token):
        return self.client.rpc("public_portfolio", {"token": token}).execute().data

    def weekly_digest(self):
        return self.client.rpc("weekly_digest").execute().data or []


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name, required=True, limit=10000):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Invalid {name}")
    return value.strip()


def _url(value):
    value = _text(value or "", "artifact URL", required=False, limit=2000)
    if value and not value.startswith(("https://", "http://")):
        raise ValueError("Use an http(s) URL")
    return value


def _money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 100000000:
            raise ValueError("Invalid budget")
        return float(amount.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))
    except (ArithmeticError, TypeError):
        raise ValueError("Invalid budget") from None


def _assessment(course, assessment):
    if not isinstance(assessment, dict) or not isinstance(assessment.get("scores"), list):
        raise ValueError("Assessment must include rubric scores")
    scores = assessment["scores"]
    rubric = course["rubric"]
    if len(scores) != len(rubric):
        raise ValueError("Every rubric criterion must be graded exactly once")
    normalized, total = [], 0
    for criterion in rubric:
        matches = [s for s in scores if s.get("criterion") == criterion["criterion"]]
        if len(matches) != 1:
            raise ValueError("Invalid rubric criterion")
        score = matches[0].get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= criterion["max_points"]:
            raise ValueError("Score outside rubric bounds")
        total += score
        normalized.append({"criterion": criterion["criterion"], "score": score,
                           "feedback": _text(matches[0].get("feedback", ""), "feedback", False)})
    return {"scores": normalized, "feedback": _text(assessment.get("feedback", ""), "feedback", False),
            "points": total}


class DemoBackend:
    """An isolated demo world. Role switching selects seeded identities, not role mutation."""

    def __init__(self, role="individual"):
        self._data = {name: [] for name in TABLES}
        self._snapshots = {}
        for r, name in (("individual", "Lerato Mokoena"), ("ngo", "Community Futures"),
                        ("company", "Ubuntu Talent")):
            self._data["profiles"].append({
                "id": r, "role": r, "name": name, "field": "Digital marketing", "area": "Johannesburg",
                "resume": "", "public_token": secrets.token_urlsafe(32),
                "public_enabled": r == "individual", "points": 0,
            })
        self._data["courses"] = [{
            "id": "campaign-basics", "title": "Build a community campaign",
            "field": "Digital marketing", "brief": "Design a practical outreach campaign for a local NGO.",
            "rubric": [{"criterion": "Clarity", "max_points": 40},
                       {"criterion": "Impact", "max_points": 40},
                       {"criterion": "Feasibility", "max_points": 20}], "max_points": 100,
        }, {
            "id": "data-story", "title": "Tell a story with data", "field": "Data analysis",
            "brief": "Explain a community challenge using a small dataset and clear visualizations.",
            "rubric": [{"criterion": "Accuracy", "max_points": 50},
                       {"criterion": "Communication", "max_points": 50}], "max_points": 100,
        }]
        self._role = "ngo"
        project = self.action("create_project", title="Youth programme launch", field="Digital marketing",
                              area="Johannesburg", brief="Create an outreach plan for a youth programme.",
                              budget=2500, min_points=50)
        self.action("record_platform_fee", project_id=project["id"], reference="DEMO-MANUAL-DECLARATION")
        self.switch_role(role)

    def switch_role(self, role):
        if role not in ROLES:
            raise ValueError("Invalid role")
        self._role = role

    @property
    def profile(self):
        return copy.deepcopy(self._own())

    def _own(self):
        return next(p for p in self._data["profiles"] if p["id"] == self._role)

    def _require(self, role):
        if self._own()["role"] != role:
            raise PermissionError(f"Requires {role} role")

    def _get(self, table, record_id):
        for row in self._data[table]:
            if row["id"] == record_id:
                return row
        raise ValueError("Record not found")

    def rows(self, table, **filters):
        if table not in TABLES:
            raise ValueError("Unknown table")
        uid = self._own()["id"]
        def visible(row):
            if table == "profiles":
                return row["id"] == uid
            if table == "projects":
                return row["ngo_id"] == uid or row["status"] != "draft"
            if table == "submissions":
                return row["applicant_id"] == uid
            if table == "pitches":
                return row["applicant_id"] == uid or self._get("projects", row["project_id"])["ngo_id"] == uid
            if table == "subscriptions":
                return row["company_id"] == uid
            return True
        records = [r for r in self._data[table]
                   if visible(r) and all(r.get(k) == v for k, v in filters.items())]
        if table == "projects":
            records = [{k: v for k, v in r.items() if k not in {"fee_reference", "payment_reference"}}
                       for r in records]
        return copy.deepcopy(records)

    def _insert(self, table, **values):
        row = {"id": str(uuid4()), **values}
        self._data[table].append(row)
        return row

    def action(self, name, **p):
        uid = self._own()["id"]
        if name == "create_profile":
            raise ValueError("A demo profile already exists; use the role selector")
        if name == "update_profile":
            values = {k: _text(p.get(k, self._own()[k]), k, k != "resume")
                      for k in ("name", "field", "area", "resume")}
            enabled = p.get("public_enabled", self._own()["public_enabled"])
            if not isinstance(enabled, bool):
                raise ValueError("Invalid public_enabled")
            self._own().update(values, public_enabled=enabled)
            return self.profile
        if name == "submit_learning":
            self._require("individual")
            course = self._get("courses", p["course_id"])
            if any(s["applicant_id"] == uid and s["course_id"] == course["id"]
                   for s in self._data["submissions"]):
                raise ValueError("This course has already been submitted")
            assessment = _assessment(course, p["assessment"]) if p.get("assessment") else None
            row = self._insert("submissions", applicant_id=uid, course_id=course["id"], project_id=None,
                               title=_text(p["title"], "title"), description=_text(p["description"], "description"),
                               artifact_url=_url(p.get("artifact_url")), assessment=assessment,
                               points=assessment["points"] if assessment else 0, created_at=_now())
            self._own()["points"] += row["points"]
        elif name == "create_project":
            self._require("ngo")
            budget = _money(p["budget"])
            minimum = p["min_points"]
            if isinstance(minimum, bool) or not isinstance(minimum, int) or not 0 <= minimum <= 1000000:
                raise ValueError("Invalid minimum points")
            row = self._insert("projects", ngo_id=uid, title=_text(p["title"], "title"),
                               field=_text(p["field"], "field"), area=_text(p["area"], "area"),
                               brief=_text(p["brief"], "brief"), budget=budget, min_points=minimum,
                               platform_fee=_money(Decimal(str(budget)) / 10), status="draft",
                               assigned_to=None, payment_reference=None, fee_reference=None,
                               fee_status="unpaid", created_at=_now())
        elif name in {"record_platform_fee", "assign_project", "deliver_project", "complete_project", "pitch"}:
            project = self._get("projects", p["project_id"])
            if name in {"record_platform_fee", "assign_project", "complete_project"}:
                self._require("ngo")
                if project["ngo_id"] != uid:
                    raise PermissionError("Only the project owner can do this")
            if name == "record_platform_fee":
                if project["status"] != "draft":
                    raise ValueError("Project must be draft")
                project.update(fee_reference=_text(p["reference"], "manual fee reference"),
                               fee_status="manually_declared", status="open")
                row = project
            elif name == "pitch":
                self._require("individual")
                if project["status"] != "open" or self._own()["points"] < project["min_points"]:
                    raise ValueError("Project is not open or minimum points not met")
                if any(x["project_id"] == project["id"] and x["applicant_id"] == uid
                       for x in self._data["pitches"]):
                    raise ValueError("Already pitched")
                row = self._insert("pitches", project_id=project["id"], applicant_id=uid,
                                   message=_text(p["message"], "message"), media_url=_url(p.get("media_url")))
            elif name == "assign_project":
                applicant = self._get("profiles", p["applicant_id"])
                if project["status"] != "open" or applicant["role"] != "individual" or not any(
                    x["project_id"] == project["id"] and x["applicant_id"] == applicant["id"]
                    for x in self._data["pitches"]
                ):
                    raise ValueError("Assign an applicant who pitched to this open project")
                project.update(assigned_to=applicant["id"], status="assigned")
                row = project
            elif name == "deliver_project":
                self._require("individual")
                if project["assigned_to"] != uid or project["status"] != "assigned":
                    raise PermissionError("Only the assigned individual can deliver an assigned project")
                description = _text(p["description"], "description")
                artifact = _url(p.get("artifact_url"))
                if not artifact:
                    raise ValueError("A delivery artifact URL is required")
                row = self._insert("submissions", applicant_id=uid, course_id=None, project_id=project["id"],
                                   title=project["title"], description=description, artifact_url=artifact,
                                   assessment=None, points=0, created_at=_now())
                project["status"] = "delivered"
            else:
                if project["status"] != "delivered":
                    raise ValueError("Only delivered projects can be completed")
                rating = p["rating"]
                if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                    raise ValueError("Rating must be 1–5")
                reference = _text(p["payment_reference"], "manual payment reference")
                body = _text(p["body"], "review")
                row = self._insert("reviews", project_id=project["id"], applicant_id=project["assigned_to"],
                                   ngo_id=uid, rating=rating, body=body, created_at=_now())
                project.update(status="complete", payment_reference=reference)
        elif name == "subscribe":
            self._require("company")
            field, area = _text(p["field"], "field"), _text(p["area"], "area")
            row = next((s for s in self._data["subscriptions"]
                        if s["company_id"] == uid and s["field"] == field and s["area"] == area), None)
            if row:
                row["active"] = True
            else:
                row = self._insert("subscriptions", company_id=uid, field=field, area=area, active=True)
        elif name == "unsubscribe":
            self._require("company")
            row = self._get("subscriptions", p["subscription_id"])
            if row["company_id"] != uid:
                raise PermissionError("Only the subscription owner can unsubscribe")
            row["active"] = False
        else:
            raise ValueError("Unknown action")
        return copy.deepcopy(row)

    def grade_submission(self, submission_id, assessment):
        self._require("individual")
        row = self._get("submissions", submission_id)
        if row["applicant_id"] != self._own()["id"]:
            raise PermissionError("Not your submission")
        if row["assessment"] is not None or row["course_id"] is None:
            raise ValueError("Submission cannot be graded")
        result = _assessment(self._get("courses", row["course_id"]), assessment)
        row.update(assessment=result, points=result["points"])
        self._own()["points"] += result["points"]
        return copy.deepcopy(row)

    def public_profile(self, token):
        profile = next((r for r in self._data["profiles"] if r["public_token"] == token
                        and r["public_enabled"] and r["role"] == "individual"), None)
        if not profile:
            return None
        uid = profile["id"]
        return copy.deepcopy({
            "profile": {k: profile[k] for k in ("id", "name", "field", "area", "resume", "points")},
            "submissions": [r for r in self._data["submissions"] if r["applicant_id"] == uid],
            "reviews": [r for r in self._data["reviews"] if r["applicant_id"] == uid],
            "projects": [{k: r[k] for k in ("id", "title", "field", "area", "brief", "status", "assigned_to")}
                         for r in self._data["projects"] if r["assigned_to"] == uid],
        })

    def weekly_digest(self):
        self._require("company")
        now = datetime.now(timezone.utc)
        week = (now - timedelta(days=now.weekday())).date().isoformat()
        result = []
        for sub in self.rows("subscriptions", active=True):
            key = (sub["id"], week)
            if key not in self._snapshots:
                talent = sorted((r for r in self._data["profiles"]
                                 if r["role"] == "individual" and r["public_enabled"]
                                 and r["field"] == sub["field"] and r["area"] == sub["area"]),
                                key=lambda r: (-r["points"], r["id"]))
                self._snapshots[key] = {**sub, "week_start": week,
                                        "talent": [{k: r[k] for k in ("id", "name", "field", "area", "points", "public_token")}
                                                   for r in talent]}
            snapshot = copy.deepcopy(self._snapshots[key])
            # Withdrawn consent takes precedence over snapshot stability.
            snapshot["talent"] = [r for r in snapshot["talent"]
                                  if self._get("profiles", r["id"])["public_enabled"]]
            result.append(snapshot)
        return result
