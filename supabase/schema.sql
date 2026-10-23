-- Run once in a new Supabase project's SQL editor. All writes go through RPCs.
create extension if not exists pgcrypto;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  role text not null check (role in ('individual','ngo','company')),
  name text not null check (length(trim(name)) between 1 and 10000),
  field text not null check (length(trim(field)) between 1 and 10000),
  area text not null check (length(trim(area)) between 1 and 10000),
  resume text not null default '' check (length(resume) <= 10000),
  public_token text not null unique default encode(gen_random_bytes(32),'hex'),
  public_enabled boolean not null default false,
  points integer not null default 0 check (points >= 0)
);
create table public.courses (
  id uuid primary key default gen_random_uuid(),
  title text not null, field text not null, brief text not null,
  rubric jsonb not null check (jsonb_typeof(rubric) = 'array'),
  max_points integer not null check (max_points > 0)
);
create table public.projects (
  id uuid primary key default gen_random_uuid(),
  ngo_id uuid not null references public.profiles(id),
  title text not null, field text not null, area text not null, brief text not null,
  budget numeric(12,2) not null check (budget between 0 and 100000000),
  min_points integer not null check (min_points between 0 and 1000000),
  platform_fee numeric(12,2) generated always as (round(budget * 0.10,2)) stored,
  fee_status text not null default 'unpaid' check (fee_status in ('unpaid','manually_declared')),
  fee_reference text,
  status text not null default 'draft' check (status in ('draft','open','assigned','delivered','complete')),
  assigned_to uuid references public.profiles(id),
  payment_reference text,
  created_at timestamptz not null default now()
);
create table public.submissions (
  id uuid primary key default gen_random_uuid(),
  applicant_id uuid not null references public.profiles(id),
  course_id uuid references public.courses(id),
  project_id uuid unique references public.projects(id),
  title text not null, description text not null, artifact_url text not null default '',
  assessment jsonb,
  points integer not null default 0 check (points >= 0),
  created_at timestamptz not null default now(),
  check ((course_id is null) <> (project_id is null)),
  unique (applicant_id,course_id)
);
create table public.pitches (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id),
  applicant_id uuid not null references public.profiles(id),
  message text not null, media_url text not null default '',
  unique(project_id,applicant_id)
);
create table public.reviews (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references public.projects(id),
  applicant_id uuid not null references public.profiles(id),
  ngo_id uuid not null references public.profiles(id),
  rating integer not null check (rating between 1 and 5),
  body text not null, created_at timestamptz not null default now()
);
create table public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.profiles(id),
  field text not null, area text not null, active boolean not null default true,
  unique(company_id,field,area)
);
create table public.digest_snapshots (
  subscription_id uuid not null references public.subscriptions(id),
  company_id uuid not null references public.profiles(id),
  week_start date not null,
  talent jsonb not null,
  primary key(subscription_id,week_start)
);

alter table public.profiles enable row level security;
alter table public.courses enable row level security;
alter table public.projects enable row level security;
alter table public.submissions enable row level security;
alter table public.pitches enable row level security;
alter table public.reviews enable row level security;
alter table public.subscriptions enable row level security;
alter table public.digest_snapshots enable row level security;

-- Profile tokens stay private except for explicit public portfolio/digest RPCs.
create policy own_profile on public.profiles for select to authenticated using (id = auth.uid());
create policy courses_read on public.courses for select to anon, authenticated using (true);
create policy projects_read on public.projects for select to authenticated
  using (ngo_id = auth.uid() or status <> 'draft');
create policy submissions_read on public.submissions for select to authenticated
  using (applicant_id = auth.uid() or exists (
    select 1 from public.projects p where p.id = project_id and p.ngo_id = auth.uid()));
create policy pitches_read on public.pitches for select to authenticated
  using (applicant_id = auth.uid() or exists (
    select 1 from public.projects p where p.id = project_id and p.ngo_id = auth.uid()));
create policy reviews_read on public.reviews for select to authenticated using (true);
create policy subscriptions_read on public.subscriptions for select to authenticated
  using (company_id = auth.uid());
create policy snapshots_read on public.digest_snapshots for select to authenticated
  using (company_id = auth.uid());

revoke all on public.profiles, public.courses, public.projects, public.submissions,
  public.pitches, public.reviews, public.subscriptions, public.digest_snapshots from anon, authenticated;
grant select on public.profiles, public.courses, public.submissions, public.pitches,
  public.reviews, public.subscriptions to authenticated;
-- Manual payment declarations are visible only to the NGO through action results.
-- Clients can read non-private project columns; never payment/fee reference columns.
grant select (id,ngo_id,title,field,area,brief,budget,min_points,platform_fee,fee_status,
  status,assigned_to,created_at) on public.projects to authenticated;
grant select on public.courses to anon;

create function public.required_text(value text, label text) returns text
language plpgsql immutable set search_path = '' as $$
begin
  if value is null or length(trim(value)) not between 1 and 10000 then
    raise exception 'Invalid %', label;
  end if;
  return trim(value);
end $$;
create function public.safe_url(value text) returns text
language plpgsql immutable set search_path = '' as $$
begin
  if value is null or value = '' then return ''; end if;
  if length(value) > 2000 or value !~ '^https?://' then raise exception 'Use an http(s) URL'; end if;
  return value;
end $$;
revoke all on function public.required_text(text,text), public.safe_url(text) from public;

create function public.letsema_action(action_name text, payload jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  me public.profiles;
  proj public.projects;
  result jsonb;
  sid uuid;
  target uuid;
  text_value text;
  rating_value integer;
  existing_submission public.submissions;
begin
  if uid is null then raise exception 'Authentication required'; end if;
  select * into me from public.profiles where id = uid;
  if action_name = 'create_profile' then
    if me.id is not null then raise exception 'Profile already exists; role is immutable'; end if;
    if payload->>'role' not in ('individual','ngo','company') or payload->>'role' is null then
      raise exception 'Invalid role';
    end if;
    insert into public.profiles(id,role,name,field,area) values (
      uid,payload->>'role',public.required_text(payload->>'name','name'),
      public.required_text(payload->>'field','field'),public.required_text(payload->>'area','area'))
      returning to_jsonb(profiles.*) into result;
    return result;
  end if;
  if me.id is null then raise exception 'Create a profile first'; end if;
  if action_name = 'update_profile' then
    text_value := coalesce(payload->>'resume',me.resume);
    if length(text_value) > 10000 then raise exception 'Resume too long'; end if;
    if payload ? 'public_enabled' and jsonb_typeof(payload->'public_enabled') <> 'boolean' then
      raise exception 'Invalid public_enabled';
    end if;
    update public.profiles set
      name = public.required_text(coalesce(payload->>'name',me.name),'name'),
      field = public.required_text(coalesce(payload->>'field',me.field),'field'),
      area = public.required_text(coalesce(payload->>'area',me.area),'area'),
      resume = text_value,
      public_enabled = coalesce((payload->>'public_enabled')::boolean,me.public_enabled)
      where id = uid returning to_jsonb(profiles.*) into result;
  elsif action_name = 'submit_learning' then
    if me.role <> 'individual' then raise exception 'Requires individual role'; end if;
    -- assessment and points in payload are deliberately ignored.
    insert into public.submissions(applicant_id,course_id,title,description,artifact_url)
      values (uid,(payload->>'course_id')::uuid,public.required_text(payload->>'title','title'),
        public.required_text(payload->>'description','description'),public.safe_url(payload->>'artifact_url'))
      on conflict (applicant_id,course_id) do nothing
      returning to_jsonb(submissions.*) into result;
    if result is null then
      select * into existing_submission from public.submissions
        where applicant_id = uid and course_id = (payload->>'course_id')::uuid for update;
      if existing_submission.assessment is not null or
        existing_submission.title <> trim(payload->>'title') or
        existing_submission.description <> trim(payload->>'description') or
        existing_submission.artifact_url <> public.safe_url(payload->>'artifact_url') then
        raise exception 'This course has already been submitted';
      end if;
      -- A grading/network failure can retry the identical pending submission, never award twice.
      result := to_jsonb(existing_submission);
    end if;
  elsif action_name = 'create_project' then
    if me.role <> 'ngo' then raise exception 'Requires ngo role'; end if;
    if jsonb_typeof(payload->'min_points') <> 'number' or
      (payload->>'min_points') !~ '^[0-9]+$' then raise exception 'Invalid minimum points'; end if;
    insert into public.projects(ngo_id,title,field,area,brief,budget,min_points) values (
      uid,public.required_text(payload->>'title','title'),public.required_text(payload->>'field','field'),
      public.required_text(payload->>'area','area'),public.required_text(payload->>'brief','brief'),
      (payload->>'budget')::numeric,(payload->>'min_points')::integer)
      returning to_jsonb(projects.*) into result;
  elsif action_name in ('record_platform_fee','pitch','assign_project','deliver_project','complete_project') then
    select * into proj from public.projects where id = (payload->>'project_id')::uuid for update;
    if proj.id is null then raise exception 'Project not found'; end if;
    if action_name in ('record_platform_fee','assign_project','complete_project') and
      (me.role <> 'ngo' or proj.ngo_id <> uid) then raise exception 'Requires project owner'; end if;
    if action_name = 'record_platform_fee' then
      if proj.status <> 'draft' then raise exception 'Project must be draft'; end if;
      update public.projects set fee_reference = public.required_text(payload->>'reference','manual fee reference'),
        fee_status = 'manually_declared', status = 'open' where id = proj.id
        returning to_jsonb(projects.*) into result;
    elsif action_name = 'pitch' then
      if me.role <> 'individual' or proj.status <> 'open' or me.points < proj.min_points then
        raise exception 'Requires individual with sufficient points and open project';
      end if;
      insert into public.pitches(project_id,applicant_id,message,media_url)
        values(proj.id,uid,public.required_text(payload->>'message','message'),
          public.safe_url(payload->>'media_url'))
        returning to_jsonb(pitches.*) into result;
    elsif action_name = 'assign_project' then
      target := (payload->>'applicant_id')::uuid;
      if proj.status <> 'open' or not exists (
        select 1 from public.pitches pi join public.profiles pr on pi.applicant_id = pr.id
        where pi.project_id = proj.id and pi.applicant_id = target and pr.role = 'individual'
      ) then raise exception 'Assign a pitched individual to an open project'; end if;
      update public.projects set assigned_to = target,status = 'assigned' where id = proj.id
        returning to_jsonb(projects.*) into result;
    elsif action_name = 'deliver_project' then
      if me.role <> 'individual' or proj.assigned_to is distinct from uid or proj.status <> 'assigned' then
        raise exception 'Requires assigned individual and assigned project';
      end if;
      text_value := public.safe_url(payload->>'artifact_url');
      if text_value = '' then raise exception 'Delivery artifact URL required'; end if;
      insert into public.submissions(applicant_id,project_id,title,description,artifact_url)
        values(uid,proj.id,proj.title,public.required_text(payload->>'description','description'),text_value)
        returning to_jsonb(submissions.*) into result;
      update public.projects set status = 'delivered' where id = proj.id;
    else
      if proj.status <> 'delivered' then raise exception 'Project must be delivered'; end if;
      if jsonb_typeof(payload->'rating') <> 'number' or
        (payload->>'rating') !~ '^[1-5]$' then raise exception 'Rating must be 1-5'; end if;
      rating_value := (payload->>'rating')::integer;
      text_value := public.required_text(payload->>'payment_reference','manual payment reference');
      update public.projects set status = 'complete',payment_reference = text_value where id = proj.id;
      insert into public.reviews(project_id,applicant_id,ngo_id,rating,body)
        values(proj.id,proj.assigned_to,uid,rating_value,public.required_text(payload->>'body','review'))
        returning to_jsonb(reviews.*) into result;
    end if;
  elsif action_name = 'subscribe' then
    if me.role <> 'company' then raise exception 'Requires company role'; end if;
    insert into public.subscriptions(company_id,field,area) values (
      uid,public.required_text(payload->>'field','field'),public.required_text(payload->>'area','area'))
      on conflict(company_id,field,area) do update set active = true
      returning to_jsonb(subscriptions.*) into result;
  elsif action_name = 'unsubscribe' then
    if me.role <> 'company' then raise exception 'Requires company role'; end if;
    update public.subscriptions set active = false
      where id = (payload->>'subscription_id')::uuid and company_id = uid
      returning to_jsonb(subscriptions.*) into result;
    if result is null then raise exception 'Subscription not found'; end if;
  else
    raise exception 'Unknown action';
  end if;
  return result;
end $$;
revoke all on function public.letsema_action(text,jsonb) from public;
grant execute on function public.letsema_action(text,jsonb) to authenticated;

-- Only a trusted server can call this, after independently grading the stored artifact.
-- Never accept a browser-provided assessment in a service-role forwarding endpoint.
create function public.grade_submission(submission_id uuid, applicant_id uuid, assessment jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  submission public.submissions;
  course public.courses;
  criterion jsonb;
  score_item jsonb;
  score_value integer;
  total integer := 0;
  clean_scores jsonb := '[]'::jsonb;
  clean_assessment jsonb;
  result jsonb;
begin
  if auth.role() is distinct from 'service_role' then raise exception 'Trusted grader only'; end if;
  select * into submission from public.submissions s where s.id = submission_id for update;
  if submission.id is null or submission.applicant_id is distinct from applicant_id
    or submission.course_id is null or submission.assessment is not null then
    raise exception 'Submission cannot be graded';
  end if;
  select * into course from public.courses where id = submission.course_id;
  if jsonb_typeof(assessment->'scores') is distinct from 'array' then raise exception 'Invalid scores'; end if;
  if jsonb_array_length(assessment->'scores') <> jsonb_array_length(course.rubric) then
    raise exception 'Every rubric criterion must be graded exactly once';
  end if;
  for criterion in select value from jsonb_array_elements(course.rubric) loop
    if (select count(*) from jsonb_array_elements(assessment->'scores') s
        where s->>'criterion' = criterion->>'criterion') <> 1 then raise exception 'Invalid criterion'; end if;
    select value into score_item from jsonb_array_elements(assessment->'scores')
      where value->>'criterion' = criterion->>'criterion';
    if jsonb_typeof(score_item->'score') is distinct from 'number' or
      (score_item->>'score') !~ '^[0-9]+$' then raise exception 'Invalid score'; end if;
    score_value := (score_item->>'score')::integer;
    if score_value > (criterion->>'max_points')::integer then raise exception 'Score exceeds rubric'; end if;
    total := total + score_value;
    clean_scores := clean_scores || jsonb_build_array(jsonb_build_object(
      'criterion',criterion->>'criterion','score',score_value,
      'feedback',left(coalesce(score_item->>'feedback',''),10000)));
  end loop;
  if total > course.max_points then raise exception 'Points exceed maximum'; end if;
  clean_assessment := jsonb_build_object('scores',clean_scores,'points',total,
    'feedback',left(coalesce(assessment->>'feedback',''),10000));
  update public.submissions set assessment = clean_assessment,points = total
    where id = submission_id returning to_jsonb(submissions.*) into result;
  update public.profiles set points = points + total where id = submission.applicant_id;
  return result;
end $$;
revoke all on function public.grade_submission(uuid,uuid,jsonb) from public, anon, authenticated;
grant execute on function public.grade_submission(uuid,uuid,jsonb) to service_role;

create function public.public_portfolio(token text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles; result jsonb;
begin
  select * into p from public.profiles pr
    where pr.public_token = token and pr.public_enabled and pr.role = 'individual';
  if p.id is null then return null; end if;
  select jsonb_build_object(
    'profile',jsonb_build_object('id',p.id,'name',p.name,'field',p.field,'area',p.area,'resume',p.resume,'points',p.points),
    'submissions',coalesce((select jsonb_agg(to_jsonb(s) order by s.created_at,s.id)
      from public.submissions s where s.applicant_id = p.id),'[]'::jsonb),
    'reviews',coalesce((select jsonb_agg(to_jsonb(r) order by r.created_at,r.id)
      from public.reviews r where r.applicant_id = p.id),'[]'::jsonb),
    'projects',coalesce((select jsonb_agg(jsonb_build_object('id',pr.id,'title',pr.title,'field',pr.field,
      'area',pr.area,'brief',pr.brief,'status',pr.status,'assigned_to',pr.assigned_to) order by pr.created_at,pr.id)
      from public.projects pr where pr.assigned_to = p.id),'[]'::jsonb)
  ) into result;
  return result;
end $$;
revoke all on function public.public_portfolio(text) from public;
grant execute on function public.public_portfolio(text) to anon,authenticated;

create function public.weekly_digest() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  week date := date_trunc('week',now() at time zone 'UTC')::date;
  sub public.subscriptions;
  talent jsonb;
  result jsonb := '[]'::jsonb;
begin
  if not exists(select 1 from public.profiles where id = uid and role = 'company') then
    raise exception 'Requires company role';
  end if;
  for sub in select * from public.subscriptions where company_id = uid and active order by id loop
    select coalesce(jsonb_agg(jsonb_build_object('id',p.id,'name',p.name,'field',p.field,
      'area',p.area,'points',p.points,'public_token',p.public_token) order by p.points desc,p.id),'[]'::jsonb)
      into talent from public.profiles p
      where p.role = 'individual' and p.public_enabled and p.field = sub.field and p.area = sub.area;
    insert into public.digest_snapshots(subscription_id,company_id,week_start,talent)
      values(sub.id,uid,week,talent) on conflict(subscription_id,week_start) do nothing;
    -- Snapshots keep scores and ordering, but opting out immediately removes the individual.
    select coalesce(jsonb_agg(t.value order by t.ordinality),'[]'::jsonb) into talent
      from public.digest_snapshots d, jsonb_array_elements(d.talent) with ordinality t(value,ordinality)
      join public.profiles p on p.id = (t.value->>'id')::uuid and p.public_enabled
      where d.subscription_id = sub.id and d.week_start = week and d.company_id = uid;
    result := result || jsonb_build_array(to_jsonb(sub) || jsonb_build_object('week_start',week,'talent',talent));
  end loop;
  return result;
end $$;
revoke all on function public.weekly_digest() from public;
grant execute on function public.weekly_digest() to authenticated;

insert into public.courses(title,field,brief,rubric,max_points) values
('Build a community campaign','Digital marketing','Design a practical outreach campaign for a local NGO.',
 '[{"criterion":"Clarity","max_points":40},{"criterion":"Impact","max_points":40},{"criterion":"Feasibility","max_points":20}]',100),
('Tell a story with data','Data analysis','Explain a community challenge using a small dataset and clear visualizations.',
 '[{"criterion":"Accuracy","max_points":50},{"criterion":"Communication","max_points":50}]',100);
