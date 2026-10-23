"""Letsema's responsive web app. Run with streamlit run streamlit_app.py."""

import os
from urllib.parse import quote, urlparse

import streamlit as st
from supabase import create_client

from assessment import AssessmentError, assess_submission
from backend import Backend, DemoBackend


st.set_page_config(page_title="Letsema · Learn. Build. Belong.", page_icon="🌱", layout="centered")


def setting(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name, "")
    except FileNotFoundError:
        return ""


def link(label, url):
    """Only render navigable HTTP(S) artifact links, never arbitrary schemes."""
    if url and urlparse(url).scheme in ("http", "https") and urlparse(url).netloc:
        st.link_button(label, url)


def act(store, name, **params):
    try:
        store.action(name, **params)
        st.session_state["notice"] = "Saved successfully."
        st.rerun()
    except Exception:
        st.error("Could not save. Check required fields, permissions, and the project's current status.")


def show_portfolio(data):
    profile = data["profile"]
    st.header(profile["name"])
    st.write(f"{profile['field']} · {profile['area']}")
    st.metric("Experience points", profile["points"])
    st.subheader("Resume")
    st.text(profile.get("resume") or "No resume added yet.")
    st.subheader("Project repository")
    for item in data.get("submissions", []):
        learning = bool(item.get("course_id"))
        label = f"Learning · {item['title']} · {item.get('points', 0)} points" if learning else f"NGO · {item['title']}"
        with st.expander(label):
            st.text(item["description"])
            link("View project", item.get("artifact_url"))
            if learning:
                assessment = item.get("assessment") or {}
                st.text(assessment.get("feedback", "Awaiting assessment."))
    for item in data.get("projects", []):
        with st.expander(f"NGO · {item['title']}"):
            st.text(item.get("delivery_description") or item.get("brief", ""))
            link("View delivered work", item.get("artifact_url") or item.get("delivery_url"))
    st.subheader("NGO reviews")
    reviews = data.get("reviews", [])
    if not reviews:
        st.caption("Reviews appear after completed NGO projects.")
    for review in reviews:
        st.write(f"{review['rating']}/5")
        st.text(review["body"])


def edit_profile(store):
    p = store.profile
    st.subheader("Your profile")
    with st.form("profile"):
        name = st.text_input("Display name", value=p["name"], max_chars=120)
        field = st.text_input("Industry / field", value=p["field"], max_chars=100)
        area = st.text_input("Area / city", value=p["area"], max_chars=100)
        resume = st.text_area("Resume, skills and experience", value=p.get("resume", ""), max_chars=10000)
        public = st.checkbox("Share my portfolio and include me in talent lists",
                             value=p.get("public_enabled", False),
                             disabled=p["role"] != "individual")
        if st.form_submit_button("Save profile"):
            act(store, "update_profile", name=name, field=field, area=area,
                resume=resume, public_enabled=public)
    if p["role"] == "individual" and p.get("public_enabled"):
        base = setting("APP_BASE_URL").rstrip("/")
        path = "?profile=" + quote(str(p["public_token"]), safe="")
        st.code(base + "/" + path if base else path, language=None)
        st.caption("Anyone with this link can see your resume, projects and reviews without an account. "
                   "Turn sharing off to revoke access. Never include private information in public work.")
        if st.button("Preview public portfolio"):
            data = store.public_profile(p["public_token"])
            if data:
                show_portfolio(data)


def learn(store, demo):
    st.subheader("Build skills. Earn experience.")
    st.caption("Project challenges, not academic tests. Complete each challenge once to earn points.")
    courses = store.rows("courses")
    field = st.selectbox("Explore an industry", ["All"] + sorted({c["field"] for c in courses}))
    submissions = {s["course_id"]: s for s in store.rows("submissions", applicant_id=store.profile["id"])
                   if s.get("course_id")}
    for course in courses:
        if field != "All" and course["field"] != field:
            continue
        with st.expander(f"{course['title']} · up to {course['max_points']} points"):
            st.text(course["brief"])
            st.caption("Rubric")
            for criterion in course["rubric"]:
                st.write(f"{criterion['criterion']}: {criterion['max_points']} points")
            prior = submissions.get(course["id"])
            if prior and prior.get("assessment") is not None:
                st.success("Challenge submitted — see your repository for feedback.")
                continue
            if prior:
                st.info("Assessment pending. Retry the saved evidence below; points are awarded only once.")
            with st.form("learn_" + str(course["id"])):
                title = st.text_input("Your project title", value=prior["title"] if prior else "",
                                      max_chars=200, disabled=bool(prior))
                description = st.text_area("Written project evidence",
                                          help="Describe what you built, decisions, outcomes and evidence for each rubric item.",
                                          value=prior["description"] if prior else "",
                                          max_chars=10000, disabled=bool(prior))
                artifact = st.text_input("Project / repository URL (https://…)",
                                         value=prior["artifact_url"] if prior else "",
                                         disabled=bool(prior))
                st.caption("AI assesses written evidence only; it cannot inspect linked files or videos. "
                           "Do not submit confidential or personal data.")
                if demo:
                    st.info("Demo: a simulated rubric result is used, not an AI assessment.")
                if st.form_submit_button("Submit project for assessment"):
                    if not title.strip() or not description.strip():
                        st.error("Add a title and written evidence.")
                        continue
                    try:
                        if demo:
                            result = {
                                "scores": [{"criterion": c["criterion"], "score": c["max_points"] // 2,
                                            "feedback": "Simulated demo score; not AI-reviewed."}
                                           for c in course["rubric"]],
                                "feedback": "Demo assessment only. Configure AI for real rubric feedback.",
                            }
                            result["points"] = sum(s["score"] for s in result["scores"])
                        else:
                            if not setting("SUPABASE_SERVICE_ROLE_KEY"):
                                raise AssessmentError("Trusted grading is not configured by the operator.")
                            with st.spinner("Assessing against the rubric…"):
                                result = assess_submission(course, description, artifact, setting("OPENAI_API_KEY"))
                        act(store, "submit_learning", course_id=course["id"], title=title,
                            description=description, artifact_url=artifact, assessment=result)
                    except AssessmentError as exc:
                        st.error(str(exc))


def repository(store):
    st.subheader("Your work and feedback")
    submissions = store.rows("submissions", applicant_id=store.profile["id"])
    if not submissions:
        st.info("Complete a learning challenge to start your project repository.")
    for submission in submissions:
        learning = bool(submission.get("course_id"))
        with st.expander(("Learning · " if learning else "NGO · ") + submission["title"]):
            st.text(submission["description"])
            link("Open project", submission.get("artifact_url"))
            if not learning:
                st.caption("Real-world NGO project delivery.")
                continue
            st.write(f"{submission.get('points', 0)} points")
            result = submission.get("assessment") or {}
            st.text(result.get("feedback", "Assessment pending."))
            for score in result.get("scores", []):
                st.write(f"{score['criterion']}: {score['score']}")
                st.text(score["feedback"])
    for project in store.rows("projects", assigned_to=store.profile["id"]):
        st.write(f"NGO project: {project['title']} · {project['status']}")
        link("Delivered artifact", project.get("delivery_url") or project.get("artifact_url"))
    for review in store.rows("reviews", applicant_id=store.profile["id"]):
        st.write(f"NGO review: {review['rating']}/5")
        st.text(review["body"])


def opportunities(store):
    st.subheader("Make a difference")
    p = store.profile
    projects = store.rows("projects")
    for project in projects:
        if project["status"] not in ("open", "assigned", "delivered", "complete"):
            continue
        with st.expander(f"{project['title']} · R{float(project['budget']):,.2f} · {project['status']}"):
            st.text(project["brief"])
            st.write(f"{project['field']} · {project['area']} · minimum {project['min_points']} points")
            if project["status"] == "open":
                if p["points"] < project["min_points"]:
                    st.info(f"Earn {project['min_points'] - p['points']} more points to pitch.")
                else:
                    with st.form("pitch_" + str(project["id"])):
                        message = st.text_area("Why are you right for this project?", max_chars=5000)
                        media = st.text_input("Your video or presentation URL (https://…)")
                        if st.form_submit_button("Send pitch"):
                            if not media.strip():
                                st.error("Add a video or presentation link to your pitch.")
                            else:
                                act(store, "pitch", project_id=project["id"], message=message, media_url=media)
            if project.get("assigned_to") == p["id"] and project["status"] == "assigned":
                with st.form("deliver_" + str(project["id"])):
                    description = st.text_area("Delivery summary", max_chars=10000)
                    artifact = st.text_input("Delivered project URL")
                    if st.form_submit_button("Submit completed work"):
                        act(store, "deliver_project", project_id=project["id"],
                            description=description, artifact_url=artifact)


def ngo_projects(store):
    st.subheader("Affordable help. Real impact.")
    st.info("Amounts are in ZAR. Platform fee: 10% of the project budget, paid separately. "
            "This app records manual payment references; it does not charge cards, hold escrow, or verify transfers.")
    with st.expander("Post a project"):
        with st.form("new_project"):
            title = st.text_input("Project title", max_chars=200)
            field = st.text_input("Industry / field", value=store.profile["field"], max_chars=100)
            area = st.text_input("Area / city", value=store.profile["area"], max_chars=100)
            brief = st.text_area("Project brief and acceptance criteria", max_chars=10000)
            budget = st.number_input("Applicant payment (ZAR)", min_value=1.0, max_value=1000000.0, value=500.0)
            minimum = st.number_input("Minimum experience points to pitch", min_value=0, max_value=100000, step=10)
            if st.form_submit_button("Create project"):
                act(store, "create_project", title=title, field=field, area=area, brief=brief,
                    budget=budget, min_points=minimum)
    for project in store.rows("projects", ngo_id=store.profile["id"]):
        with st.expander(f"{project['title']} · {project['status']}"):
            st.text(project["brief"])
            st.write(f"Applicant budget: R{float(project['budget']):,.2f}")
            st.write(f"Platform fee: R{float(project['platform_fee']):,.2f}")
            if project["status"] == "draft":
                with st.form("fee_" + str(project["id"])):
                    reference = st.text_input("Manual platform fee payment reference")
                    confirmed = st.checkbox("I have paid the platform fee outside this app.")
                    if st.form_submit_button("Record fee payment and publish"):
                        if confirmed:
                            act(store, "record_platform_fee", project_id=project["id"], reference=reference)
                        else:
                            st.error("Confirm the external platform fee payment before publishing.")
            if project["status"] == "open":
                pitches = store.rows("pitches", project_id=project["id"])
                if not pitches:
                    st.caption("No pitches yet.")
                for pitch in pitches:
                    st.text(pitch["message"])
                    st.caption("Applicant: " + str(pitch["applicant_id"]))
                    link("View video / presentation pitch", pitch["media_url"])
                    if st.button("Assign this applicant", key="assign_" + str(pitch["id"])):
                        act(store, "assign_project", project_id=project["id"], applicant_id=pitch["applicant_id"])
            if project["status"] == "delivered":
                st.text(project.get("delivery_description", ""))
                link("Review delivered work", project.get("delivery_url") or project.get("artifact_url"))
                with st.form("complete_" + str(project["id"])):
                    payment = st.text_input("Manual applicant payment reference")
                    rating = st.slider("Review rating", 1, 5, 5)
                    body = st.text_area("Your review", max_chars=5000)
                    paid = st.checkbox("I accepted the work and paid the applicant outside this app.")
                    if st.form_submit_button("Record payment, complete and review"):
                        if paid:
                            act(store, "complete_project", project_id=project["id"],
                                payment_reference=payment, rating=rating, body=body)
                        else:
                            st.error("Confirm acceptance and external applicant payment before completing.")


def talent(store):
    st.subheader("Find your next junior hire")
    st.caption("Subscribe to weekly in-app runner-up lists by field and area. "
               "Only applicants who opt into public sharing appear. Lists refresh each UTC week.")
    with st.form("subscribe"):
        field = st.text_input("Industry / field", value=store.profile["field"], max_chars=100)
        area = st.text_input("Area / city", value=store.profile["area"], max_chars=100)
        if st.form_submit_button("Subscribe to weekly list"):
            act(store, "subscribe", field=field, area=area)
    for subscription in store.weekly_digest():
        with st.container(border=True):
            st.write(f"{subscription['field']} · {subscription['area']}")
            st.caption("Week: " + str(subscription.get("week", subscription.get("week_start", ""))))
            candidates = subscription.get("talent", [])
            if not candidates:
                st.caption("No matching public applicants this week.")
            for index, candidate in enumerate(candidates, 1):
                st.write(f"{index}. {candidate['name']} · {candidate['points']} points")
                if st.button("View portfolio", key=f"talent_{subscription['id']}_{candidate['id']}"):
                    data = store.public_profile(candidate["public_token"])
                    if data:
                        show_portfolio(data)
                    else:
                        st.info("This applicant no longer shares a public portfolio.")
            if st.button("Unsubscribe", key="unsubscribe_" + str(subscription["id"])):
                act(store, "unsubscribe", subscription_id=subscription["id"])


def authenticate(client):
    st.subheader("Welcome to Letsema")
    st.write("Learn by building. Help an NGO. Get discovered.")
    with st.form("auth"):
        mode = st.radio("Account", ["Sign in", "Create account"], horizontal=True)
        email = st.text_input("Email", max_chars=254)
        password = st.text_input("Password", type="password", help="Use at least 12 characters.")
        if st.form_submit_button("Continue"):
            try:
                if mode == "Create account":
                    if len(password) < 12:
                        st.error("Use a password of at least 12 characters.")
                        return
                    response = client.auth.sign_up({"email": email, "password": password})
                else:
                    response = client.auth.sign_in_with_password({"email": email, "password": password})
                if response.session:
                    st.session_state["signed_in"] = True
                    st.rerun()
                st.success("Check your email to confirm your account, then sign in.")
            except Exception:
                st.error("Authentication failed. Check your details and email confirmation.")


def main():
    st.title("🌱 Letsema")
    st.caption("Learn. Build. Belong.")
    url, key = setting("SUPABASE_URL"), setting("SUPABASE_ANON_KEY")
    configured = bool(url and key)
    if not configured:
        st.warning("Interactive demo — data is local to this browser session, not saved to Supabase. "
                   "Payments and assessments are simulated. Configure Supabase for real accounts.")
        if "demo_store" not in st.session_state:
            st.session_state["demo_store"] = DemoBackend()
        store = st.session_state["demo_store"]
        if not st.query_params.get("profile"):
            role = st.selectbox("Explore a demo profile", ["individual", "ngo", "company"],
                                format_func=lambda r: {"individual": "Individual / applicant", "ngo": "NGO",
                                                      "company": "Company"}[r])
            store.switch_role(role)
    else:
        if "client" not in st.session_state:
            st.session_state["client"] = create_client(url, key)
        client = st.session_state["client"]
        grading_client = None
        if setting("SUPABASE_SERVICE_ROLE_KEY"):
            # Never authenticate this client or share it through Streamlit's global cache.
            grading_client = create_client(url, setting("SUPABASE_SERVICE_ROLE_KEY"))
        store = Backend(client, grading_client=grading_client)
    token = st.query_params.get("profile")
    if token:
        data = store.public_profile(token)
        if data:
            show_portfolio(data)
        else:
            st.info("This portfolio is unavailable or sharing has been disabled.")
        if st.button("Go to Letsema"):
            st.query_params.clear()
            st.rerun()
        return
    if configured and not st.session_state.get("signed_in"):
        authenticate(client)
        return
    if configured and st.button("Sign out"):
        client.auth.sign_out()
        st.session_state.clear()
        st.rerun()
    if store.profile is None:
        st.subheader("Choose your profile")
        with st.form("onboard"):
            role = st.selectbox("I am an", ["individual", "ngo", "company"])
            name = st.text_input("Display name", max_chars=120)
            field = st.text_input("Industry / field", max_chars=100)
            area = st.text_input("Area / city", max_chars=100)
            st.caption("Choose carefully: your account role cannot be changed after registration.")
            if st.form_submit_button("Create profile"):
                act(store, "create_profile", role=role, name=name, field=field, area=area)
        return
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    p = store.profile
    st.write(f"Welcome, {p['name']}")
    if p["role"] == "individual":
        st.metric("Experience points", p["points"])
        st.progress(min((p["points"] % 100) / 100, 1.0),
                    text=f"Level {p['points'] // 100 + 1} · {100 - p['points'] % 100} points to next level")
        page = st.selectbox("Navigate", ["Learn", "NGO opportunities", "My repository", "My profile"])
        {"Learn": lambda: learn(store, not configured),
         "NGO opportunities": lambda: opportunities(store),
         "My repository": lambda: repository(store),
         "My profile": lambda: edit_profile(store)}[page]()
    elif p["role"] == "ngo":
        page = st.selectbox("Navigate", ["My projects", "My profile"])
        ngo_projects(store) if page == "My projects" else edit_profile(store)
    else:
        page = st.selectbox("Navigate", ["Weekly talent", "My profile"])
        talent(store) if page == "Weekly talent" else edit_profile(store)
    st.caption("Mobile-friendly web app · Open this URL in your phone's browser.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("Letsema could not load this page. Check the service configuration or try again later.")
