create extension if not exists pgcrypto;

create type public.app_role as enum ('admin', 'supervisor', 'reviewer');
create type public.source_mode as enum ('real', 'simulated');
create type public.review_status as enum ('new', 'acknowledged', 'dismissed');
create type public.event_severity as enum ('info', 'warning', 'critical');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  organization_id uuid not null references public.organizations(id) on delete restrict,
  display_name text not null,
  role public.app_role not null default 'reviewer',
  created_at timestamptz not null default now()
);

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  code text not null,
  label text not null,
  source_type text not null check (source_type in ('avfoundation', 'rtsp', 'file')),
  camera_uri text,
  last_seen_at timestamptz,
  model_version text,
  created_at timestamptz not null default now(),
  unique (organization_id, code)
);

create table public.device_credentials (
  device_id uuid primary key references public.devices(id) on delete cascade,
  token_hash text not null,
  enabled boolean not null default true,
  rotated_at timestamptz not null default now()
);

create table public.employees (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  employee_code text not null,
  display_name text not null,
  badge_marker_id integer,
  photo_url text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (organization_id, employee_code),
  unique (organization_id, badge_marker_id)
);

create table public.zones (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.devices(id) on delete cascade,
  name text not null,
  normalized_polygon jsonb not null,
  created_at timestamptz not null default now(),
  unique (device_id, name)
);

create table public.events (
  id uuid primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  device_id uuid not null references public.devices(id) on delete cascade,
  employee_id uuid references public.employees(id) on delete set null,
  track_id integer,
  occurred_at timestamptz not null,
  type text not null,
  title text not null,
  detail text not null,
  severity public.event_severity not null,
  source_mode public.source_mode not null,
  review_status public.review_status not null default 'new',
  zone text,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  evidence_path text,
  retention_until timestamptz not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (retention_until >= occurred_at + interval '365 days')
);

create table public.process_runs (
  id uuid primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  device_id uuid not null references public.devices(id) on delete cascade,
  employee_id uuid references public.employees(id) on delete set null,
  label text not null,
  source_mode public.source_mode not null,
  started_at timestamptz not null,
  completed_at timestamptz,
  elapsed_seconds integer,
  status text not null check (status in ('running', 'complete', 'exception')),
  retention_until timestamptz not null
);

create table public.temperature_readings (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  device_id uuid not null references public.devices(id) on delete cascade,
  sensor_code text not null,
  value_c numeric not null,
  min_c numeric not null,
  max_c numeric not null,
  source_mode public.source_mode not null,
  sampled_at timestamptz not null,
  retention_until timestamptz not null
);

create table public.inventory_items (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  sku text not null,
  label text not null,
  marker_id integer,
  quantity integer not null default 0 check (quantity >= 0),
  unit text not null default 'items',
  unique (organization_id, sku),
  unique (organization_id, marker_id)
);

create table public.inventory_transactions (
  id uuid primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  device_id uuid not null references public.devices(id) on delete cascade,
  inventory_item_id uuid not null references public.inventory_items(id) on delete restrict,
  employee_id uuid references public.employees(id) on delete set null,
  direction text not null check (direction in ('in', 'out')),
  quantity integer not null check (quantity > 0),
  source_mode public.source_mode not null,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  occurred_at timestamptz not null,
  retention_until timestamptz not null
);

create table public.evidence (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  snapshot_path text,
  clip_path text,
  sha256 text,
  created_at timestamptz not null default now(),
  retention_until timestamptz not null,
  unique (event_id)
);

create or replace function public.current_organization_id()
returns uuid language sql stable security definer set search_path = public
as $$ select organization_id from public.profiles where id = auth.uid() $$;

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.devices enable row level security;
alter table public.device_credentials enable row level security;
alter table public.employees enable row level security;
alter table public.zones enable row level security;
alter table public.events enable row level security;
alter table public.process_runs enable row level security;
alter table public.temperature_readings enable row level security;
alter table public.inventory_items enable row level security;
alter table public.inventory_transactions enable row level security;
alter table public.evidence enable row level security;

create policy "organization members read organization" on public.organizations for select
using (id = public.current_organization_id());
create policy "users read own profile" on public.profiles for select using (id = auth.uid());
create policy "organization reads devices" on public.devices for select using (organization_id = public.current_organization_id());
create policy "organization reads employees" on public.employees for select using (organization_id = public.current_organization_id());
create policy "organization reads events" on public.events for select using (organization_id = public.current_organization_id());
create policy "organization reads process runs" on public.process_runs for select using (organization_id = public.current_organization_id());
create policy "organization reads temperatures" on public.temperature_readings for select using (organization_id = public.current_organization_id());
create policy "organization reads inventory" on public.inventory_items for select using (organization_id = public.current_organization_id());
create policy "organization reads inventory transactions" on public.inventory_transactions for select using (organization_id = public.current_organization_id());
create policy "organization reads evidence records" on public.evidence for select using (organization_id = public.current_organization_id());
create policy "organization reads zones" on public.zones for select using (
  exists (select 1 from public.devices d where d.id = zones.device_id and d.organization_id = public.current_organization_id())
);
create policy "supervisors review events" on public.events for update using (
  organization_id = public.current_organization_id()
  and exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('admin','supervisor'))
) with check (organization_id = public.current_organization_id());

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('evidence', 'evidence', false, 52428800, array['image/jpeg','video/mp4'])
on conflict (id) do nothing;

create policy "organization reads private evidence" on storage.objects for select to authenticated
using (bucket_id = 'evidence' and (storage.foldername(name))[1] = public.current_organization_id()::text);

create policy "organization receives private realtime" on realtime.messages for select to authenticated
using (realtime.topic() like ('org:' || public.current_organization_id()::text || ':%'));
create policy "organization sends private realtime" on realtime.messages for insert to authenticated
with check (realtime.topic() like ('org:' || public.current_organization_id()::text || ':%'));

alter publication supabase_realtime add table public.events;
alter publication supabase_realtime add table public.process_runs;
alter publication supabase_realtime add table public.temperature_readings;
alter publication supabase_realtime add table public.inventory_transactions;

create index events_org_time_idx on public.events(organization_id, occurred_at desc);
create index events_review_idx on public.events(organization_id, review_status, occurred_at desc);
create index temperature_org_time_idx on public.temperature_readings(organization_id, sampled_at desc);
