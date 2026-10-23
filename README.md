# Letsema

A mobile-friendly Streamlit web app connecting students and industry novices with
NGOs and companies. It runs in a phone's browser; it is not a native Android/iOS app.

## Run

Requires Python 3.12+:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Without Supabase settings, the app opens an **isolated, session-only demo**. Switch
between Individual, NGO and Company to explore the workflows. Demo assessments
are explicitly simulated; no real accounts or payments are created. Demo links
only work within that session.

## Supabase setup

1. Create a Supabase project and run `supabase/schema.sql` in its SQL editor.
2. Enable email/password authentication and email confirmation in Supabase Auth.
3. Set these environment variables (or use `.streamlit/secrets.toml`, which is
   ignored by Git):
   - `SUPABASE_URL`: your project's HTTPS API URL.
   - `SUPABASE_ANON_KEY`: its public/anon API key.
   - `APP_BASE_URL`: the deployed Streamlit URL, used for full portfolio links.
4. For real AI assessment, also set `OPENAI_API_KEY` and
   `SUPABASE_SERVICE_ROLE_KEY` **on the Streamlit server only**. Never put the
   service-role key in a client, repository, URL, or public deployment settings.
   `OPENAI_MODEL` optionally selects a model; the default is `gpt-4o-mini`.
5. Restart Streamlit, register, confirm your email, sign in, and choose a role.
   A role is fixed at onboarding. Create separate accounts for each real role.

Database row-level security restricts reads, and database actions check ownership,
roles and state transitions. Experience points cannot be written by applicants:
only the server's grading client can persist rubric-constrained AI scores.
Keep service credentials private and restrict who can modify the deployed app.

## Profiles and workflows

### Individuals / applicants

- Complete industry-specific project briefs rather than academic tests.
- Submit an original project, its written evidence and an artifact/repository URL.
  AI returns feedback against the displayed rubric and awards bounded points.
  Each challenge can earn points once, preventing repeat-submission point farming.
- Track points and levels, then pitch eligible NGO projects with a video or
  presentation URL. Host media yourself; the app does not upload or transcode it.
- Deliver assigned work and retain learning projects, NGO work and NGO reviews.
- Edit a resume and explicitly opt into public sharing. A random portfolio link
  works without a viewer account; disabling sharing revokes it and removes the
  applicant from talent lists. Shared content should never contain private data.

### NGOs

- Set the brief, field, area, affordable applicant budget and minimum pitch points.
- Pay a separate platform fee of **10% of the applicant budget** and record the
  manual payment reference to publish a project.
- Review pitches, select an applicant, inspect their delivery, pay the applicant
  outside the app, and record payment plus a rating/review to complete the project.

**Payment boundary:** amounts are ZAR. Payment references are NGO declarations,
not verified transactions. This app does not process charges, verify transfers,
hold escrow, or send payouts. A production payment provider with authenticated
webhooks, reconciliation and dispute handling is needed before collecting money
through the platform. The fee percentage and currency are MVP policy choices.

### Companies

- Open an applicant's opt-in portfolio link without creating an account.
- With an account, subscribe to runner-up lists for a field and area.
- View ranked weekly snapshots in the app, ordered by experience points. Matching
  uses field and area; use consistent industry/city names across profiles.
- Unsubscribe at any time. Delivery is **in-app**, not email; snapshots are created
  on access for the UTC week. No external scheduler or mailing service is required.
  Subscription billing is not implemented.

## AI and deployment boundaries

Only written evidence and the project rubric are sent to OpenAI. The model cannot
inspect linked repositories, presentations or videos, and no submitted URL is
fetched by the server. Feedback is AI-generated, not professional certification;
the model may still be wrong or susceptible to deceptive evidence. Human review
and abuse controls are recommended before relying on points for paid hiring.
Missing configuration or invalid AI responses do not silently grant points.

Deploy the Streamlit app behind HTTPS, configure the above server secrets, and
share its URL with mobile users. Sessions are kept per browser, not globally
cached. A browser refresh may require signing in again.

## Verification

The repository uses Python's standard-library test runner, with Streamlit's
built-in app testing support:

```sh
python -m unittest discover -s tests -v
```

For a manual walkthrough, use the demo profile switcher: complete a challenge,
pitch an open NGO project, switch to the NGO and assign it, switch back to deliver,
then complete and review as the NGO. Opt into portfolio sharing and use a Company
profile to view a matching weekly list.
