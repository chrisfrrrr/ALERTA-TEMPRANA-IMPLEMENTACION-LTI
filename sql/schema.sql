-- AVE | Sistema de alerta temprana y seguimiento académico
-- Ejecute este archivo completo en Supabase > SQL Editor.
-- La aplicación del servidor debe usar SUPABASE_SERVICE_ROLE_KEY en Streamlit Secrets.

create extension if not exists pgcrypto;

create table if not exists public.authorized_users (
    id uuid primary key default gen_random_uuid(),
    canvas_user_id text unique,
    email text unique,
    full_name text not null,
    role text not null default 'asesor_academico'
        check (role in ('admin', 'administrador', 'asesor_academico', 'asesor_bienestar', 'consulta')),
    is_active boolean not null default true,
    allowed_course_ids jsonb not null default '[]'::jsonb,
    allowed_advisor_names jsonb not null default '[]'::jsonb,
    last_login_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint authorized_user_identifier check (canvas_user_id is not null or email is not null)
);
create index if not exists idx_authorized_users_email on public.authorized_users(email);
create index if not exists idx_authorized_users_role on public.authorized_users(role, is_active);

create table if not exists public.wellbeing_advisors (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    email text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.students (
    id uuid primary key default gen_random_uuid(),
    carne text not null unique,
    full_name text not null,
    email text,
    career text,
    canvas_user_id text,
    wellbeing_status text,
    wellbeing_stage text,
    special_requests text,
    regular_cycle_risk text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_students_canvas_user on public.students(canvas_user_id);
create index if not exists idx_students_name on public.students(full_name);

create table if not exists public.student_wellbeing_assignments (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.students(id) on delete cascade,
    advisor_id uuid not null references public.wellbeing_advisors(id) on delete restrict,
    active boolean not null default true,
    assigned_at date not null default current_date,
    ended_at date,
    created_at timestamptz not null default now(),
    unique(student_id, advisor_id)
);
create index if not exists idx_student_advisor_active on public.student_wellbeing_assignments(student_id, active);

create table if not exists public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    canvas_course_id text not null,
    course_name text not null,
    canvas_section_id text,
    section_name text,
    week_number integer not null check (week_number between 1 and 5),
    total_weeks integer not null default 5,
    analysis_cutoff timestamptz not null,
    mode text not null default 'canvas',
    student_count integer not null default 0,
    activity_count integer not null default 0,
    created_by_name text,
    created_by_canvas_user_id text,
    created_by_email text,
    created_at timestamptz not null default now()
);
create index if not exists idx_analysis_runs_course_date on public.analysis_runs(canvas_course_id, analysis_cutoff desc);

create table if not exists public.student_snapshots (
    id uuid primary key default gen_random_uuid(),
    analysis_run_id uuid not null references public.analysis_runs(id) on delete cascade,
    student_id uuid references public.students(id) on delete set null,
    canvas_user_id text,
    carne text not null,
    student_name text not null,
    email text,
    career text,
    course_id text not null,
    course_name text not null,
    section_id text,
    section_name text,
    week_number integer not null check (week_number between 1 and 5),
    total_weeks integer not null default 5,
    total_activities integer not null default 0,
    expected_activities integer not null default 0,
    completed_activities integer not null default 0,
    completed_expected integer not null default 0,
    pending_count integer not null default 0,
    late_count integer not null default 0,
    early_count integer not null default 0,
    completion_percentage numeric(7,2),
    average_grade numeric(7,2),
    weekly_sessions integer,
    inactivity_hours numeric(10,2),
    activity_risk text,
    grade_risk text,
    punctuality_risk text,
    access_risk text,
    communication_risk text,
    overall_risk text not null,
    intervention_priority text,
    pending_assignments jsonb not null default '[]'::jsonb,
    reasons jsonb not null default '[]'::jsonb,
    advisor_name text,
    analysis_cutoff timestamptz not null,
    created_at timestamptz not null default now(),
    unique(analysis_run_id, carne, course_id, section_id)
);
create index if not exists idx_snapshots_student_course on public.student_snapshots(carne, course_id, created_at desc);
create index if not exists idx_snapshots_risk on public.student_snapshots(overall_risk, created_at desc);
create index if not exists idx_snapshots_advisor on public.student_snapshots(advisor_name, created_at desc);

create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    canvas_user_id text not null,
    carne text,
    student_name text,
    advisor_name text,
    course_id text,
    course_name text,
    risk_level text,
    subject text not null,
    body text not null,
    sent_at timestamptz not null default now(),
    status text not null default 'sent',
    canvas_conversation_id text,
    responded_at timestamptz,
    response_hours numeric(10,2),
    response_excerpt text,
    created_at timestamptz not null default now()
);
create index if not exists idx_messages_student_course on public.messages(canvas_user_id, course_id, sent_at desc);
create index if not exists idx_messages_pending on public.messages(status, sent_at desc);

create table if not exists public.interventions (
    id uuid primary key default gen_random_uuid(),
    carne text not null,
    canvas_user_id text,
    course_id text,
    intervention_type text not null,
    channel text,
    notes text,
    scheduled_at timestamptz,
    completed_at timestamptz,
    created_by_name text,
    created_by_canvas_user_id text,
    created_by_email text,
    created_at timestamptz not null default now()
);
create index if not exists idx_interventions_carne on public.interventions(carne, created_at desc);

create table if not exists public.referral_batches (
    id uuid primary key default gen_random_uuid(),
    analysis_run_id uuid references public.analysis_runs(id) on delete set null,
    created_by_name text,
    student_count integer not null default 0,
    advisor_count integer not null default 0,
    notes text,
    created_at timestamptz not null default now()
);

create table if not exists public.referrals (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid references public.referral_batches(id) on delete set null,
    carne text not null,
    canvas_user_id text,
    student_name text,
    email text,
    course_id text,
    course_name text,
    section_name text,
    week_number integer,
    average_grade numeric(7,2),
    completion_percentage numeric(7,2),
    advisor_name text,
    risk_level text,
    priority text,
    reason text not null,
    status text not null default 'generated',
    followup_at timestamptz,
    closed_at timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists idx_referrals_student_open on public.referrals(carne, status, created_at desc);
create index if not exists idx_referrals_advisor on public.referrals(advisor_name, created_at desc);

create table if not exists public.risk_configuration (
    id bigint generated by default as identity primary key,
    config_name text not null unique default 'default',
    course_weeks integer not null default 5,
    activity_low_min numeric(7,2) not null default 80,
    activity_moderate_min numeric(7,2) not null default 50,
    grade_low_min numeric(7,2) not null default 70,
    grade_moderate_min numeric(7,2) not null default 60,
    access_low_min integer not null default 3,
    access_moderate_min integer not null default 1,
    inactivity_moderate_hours numeric(10,2) not null default 48,
    inactivity_high_hours numeric(10,2) not null default 96,
    response_low_hours numeric(10,2) not null default 48,
    response_moderate_hours numeric(10,2) not null default 72,
    response_high_hours numeric(10,2) not null default 120,
    late_moderate_min integer not null default 1,
    late_high_min integer not null default 4,
    no_submission_high_weeks integer not null default 2,
    referral_cooldown_days integer not null default 14,
    updated_at timestamptz not null default now()
);

alter table public.risk_configuration add column if not exists late_moderate_min integer not null default 1;
alter table public.risk_configuration add column if not exists late_high_min integer not null default 4;
alter table public.risk_configuration add column if not exists no_submission_high_weeks integer not null default 2;

insert into public.risk_configuration (config_name)
values ('default')
on conflict (config_name) do nothing;

create table if not exists public.audit_log (
    id bigint generated always as identity primary key,
    action text not null,
    entity_type text,
    entity_id text,
    actor_canvas_user_id text,
    actor_email text,
    actor_name text,
    actor_role text,
    payload jsonb,
    created_at timestamptz not null default now()
);
create index if not exists idx_audit_action_time on public.audit_log(action, created_at desc);
create index if not exists idx_audit_actor_time on public.audit_log(actor_canvas_user_id, created_at desc);

-- Migraciones seguras para proyectos creados con una versión anterior.
alter table public.analysis_runs add column if not exists created_by_canvas_user_id text;
alter table public.analysis_runs add column if not exists created_by_email text;
alter table public.audit_log add column if not exists actor_canvas_user_id text;
alter table public.audit_log add column if not exists actor_email text;
alter table public.audit_log add column if not exists actor_role text;
alter table public.messages add column if not exists student_name text;
alter table public.messages add column if not exists advisor_name text;
alter table public.referrals add column if not exists student_name text;
alter table public.referrals add column if not exists email text;
alter table public.referrals add column if not exists section_name text;
alter table public.referrals add column if not exists week_number integer;
alter table public.referrals add column if not exists average_grade numeric(7,2);
alter table public.referrals add column if not exists completion_percentage numeric(7,2);

-- La service_role key omite RLS. Se habilita RLS para impedir acceso con la anon key.
alter table public.authorized_users enable row level security;
alter table public.wellbeing_advisors enable row level security;
alter table public.students enable row level security;
alter table public.student_wellbeing_assignments enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.student_snapshots enable row level security;
alter table public.messages enable row level security;
alter table public.interventions enable row level security;
alter table public.referral_batches enable row level security;
alter table public.referrals enable row level security;
alter table public.risk_configuration enable row level security;
alter table public.audit_log enable row level security;

-- No se crean políticas públicas. La app debe ejecutar las operaciones desde el servidor con service_role.
