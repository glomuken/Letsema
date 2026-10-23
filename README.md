# Letsema

Letsema is a native iOS and Android app for students and industry novices to build
skills through projects, help NGOs, and share an opt-in portfolio with companies.
The mobile app is built with Expo and React Native and uses Supabase for auth and
data.

## Run the mobile app

Requires Node.js and npm:

```sh
npm install
cp .env.example .env
# Set your Supabase URL and anon key in .env
npm start
```

Open the project with Expo Go on a device or launch an iOS/Android simulator.
The app uses native secure storage for the Supabase auth session.

## Supabase setup

1. Create a Supabase project and run `supabase/schema.sql` in its SQL editor.
2. Enable email/password authentication and email confirmation in Supabase Auth.
3. Set `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_ANON_KEY` in `.env`.
   The anon key is intended for client apps; never put a service-role key in the
   mobile app or any `EXPO_PUBLIC_*` variable.
4. Link the Supabase CLI to the project and deploy trusted grading:

   ```sh
   supabase functions deploy grade-submission
   supabase secrets set OPENAI_API_KEY=your-openai-api-key
   ```

   `SUPABASE_SERVICE_ROLE_KEY` is provided to deployed Edge Functions by Supabase.
   `OPENAI_MODEL` optionally selects a model; the default is `gpt-4o-mini`.
5. Run the app, register, confirm your email, sign in, and choose a role. A role
   is fixed at onboarding; create separate accounts for each role.

Database row-level security restricts reads and all app writes use the
permission-checked `letsema_action` RPC. The grading Edge Function authenticates
the user, sends only written evidence and the rubric to OpenAI, validates the
result, then uses the service role to award rubric-bounded points. Keep service
credentials private and restrict who can modify the deployed function.

## Legacy Streamlit configuration

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
   A role is fixed at onboarding. Create separate accounts for each role.

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
  opens in Letsema without a viewer account; the recipient needs the app
  installed. Disabling sharing revokes the link and removes the applicant from
  talent lists. Shared content should never contain private data.

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

The former Streamlit interface remains available as a legacy web/demo client:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Without Supabase settings, it provides an isolated, session-only demo. Demo
assessments are simulated; no real accounts or payments are created. Native
clients require Supabase configuration.

## Verification

Verify the native app build and the legacy Python app with:

```sh
npm run typecheck
npx expo export --platform android
```

The legacy web tests use Python's standard-library runner and Streamlit app testing:

```sh
python -m unittest discover -s tests -v
```

For a manual walkthrough of the legacy web demo, use the demo profile switcher:
complete a challenge, pitch an open NGO project, switch to the NGO and assign it,
switch back to deliver, then complete and review as the NGO. Opt into portfolio
sharing and use a Company profile to view a matching weekly list.
