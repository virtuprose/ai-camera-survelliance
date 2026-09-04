-- Enterprise demonstration domain. Additive and safe for the existing pilot schema.
create type public.workspace_mode as enum ('live', 'simulated', 'planned');
create type public.incident_priority as enum ('low', 'medium', 'high', 'critical');
create type public.incident_status as enum ('open', 'investigating', 'action_required', 'resolved', 'closed');

create table public.sites (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  code text not null,
  name text not null,
  timezone text not null default 'Asia/Kuwait',
  mode public.workspace_mode not null,
  created_at timestamptz not null default now(),
  unique (organization_id, code)
);

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  site_id uuid not null references public.sites(id) on delete cascade,
  code text not null,
  name text not null,
  department_type text not null,
  mode public.workspace_mode not null,
  device_id uuid references public.devices(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (site_id, code)
);

create table public.shifts (
  id uuid primary key default gen_random_uuid(),
  site_id uuid not null references public.sites(id) on delete cascade,
  name text not null,
  starts_at time not null,
  ends_at time not null,
  created_at timestamptz not null default now()
);

-- Deterministic demo parent records are created here because Supabase applies seed.sql
-- after every migration. seed.sql uses ON CONFLICT and remains idempotent.
insert into public.organizations (id, name) values
  ('10000000-0000-0000-0000-000000000001', 'ORVIA AI Surveillance Demo')
on conflict (id) do nothing;

insert into public.devices (id, organization_id, code, label, source_type) values
  ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'CAM-01', 'Kitchen 01 camera', 'avfoundation')
on conflict (id) do nothing;

insert into public.sites (id, organization_id, code, name, timezone, mode) values
  ('11000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'SITE-01', 'Main Production Facility', 'Asia/Kuwait', 'live'),
  ('11000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'SITE-02', 'Secondary Facility', 'Asia/Kuwait', 'planned')
on conflict (id) do nothing;

insert into public.workspaces (id, site_id, code, name, department_type, mode, device_id) values
  ('12000000-0000-0000-0000-000000000001', '11000000-0000-0000-0000-000000000001', 'KIT-01', 'Kitchen 01', 'production', 'live', '20000000-0000-0000-0000-000000000001'),
  ('12000000-0000-0000-0000-000000000002', '11000000-0000-0000-0000-000000000001', 'RCV-01', 'Receiving', 'receiving', 'simulated', null),
  ('12000000-0000-0000-0000-000000000003', '11000000-0000-0000-0000-000000000001', 'CLD-01', 'Cold Storage', 'cold_chain', 'simulated', null),
  ('12000000-0000-0000-0000-000000000004', '11000000-0000-0000-0000-000000000001', 'INV-01', 'Inventory Store', 'inventory', 'simulated', null)
on conflict (id) do nothing;

insert into public.shifts (id, site_id, name, starts_at, ends_at) values
  ('13000000-0000-0000-0000-000000000001', '11000000-0000-0000-0000-000000000001', 'Day Shift', '06:00', '18:00')
on conflict (id) do nothing;

alter table public.events add column site_id uuid references public.sites(id) on delete restrict;
alter table public.events add column workspace_id uuid references public.workspaces(id) on delete restrict;
alter table public.events add column shift_id uuid references public.shifts(id) on delete restrict;
alter table public.process_runs add column site_id uuid references public.sites(id) on delete restrict;
alter table public.process_runs add column workspace_id uuid references public.workspaces(id) on delete restrict;
alter table public.process_runs add column shift_id uuid references public.shifts(id) on delete restrict;
alter table public.temperature_readings add column site_id uuid references public.sites(id) on delete restrict;
alter table public.temperature_readings add column workspace_id uuid references public.workspaces(id) on delete restrict;
alter table public.temperature_readings add column shift_id uuid references public.shifts(id) on delete restrict;
alter table public.inventory_transactions add column site_id uuid references public.sites(id) on delete restrict;
alter table public.inventory_transactions add column workspace_id uuid references public.workspaces(id) on delete restrict;
alter table public.inventory_transactions add column shift_id uuid references public.shifts(id) on delete restrict;

update public.events set site_id='11000000-0000-0000-0000-000000000001', workspace_id='12000000-0000-0000-0000-000000000001', shift_id='13000000-0000-0000-0000-000000000001' where site_id is null;
update public.process_runs set site_id='11000000-0000-0000-0000-000000000001', workspace_id='12000000-0000-0000-0000-000000000001', shift_id='13000000-0000-0000-0000-000000000001' where site_id is null;
update public.temperature_readings set site_id='11000000-0000-0000-0000-000000000001', workspace_id='12000000-0000-0000-0000-000000000003', shift_id='13000000-0000-0000-0000-000000000001' where site_id is null;
update public.inventory_transactions set site_id='11000000-0000-0000-0000-000000000001', workspace_id='12000000-0000-0000-0000-000000000004', shift_id='13000000-0000-0000-0000-000000000001' where site_id is null;

create table public.ppe_observations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  site_id uuid not null references public.sites(id) on delete restrict,
  workspace_id uuid not null references public.workspaces(id) on delete restrict,
  shift_id uuid not null references public.shifts(id) on delete restrict,
  employee_id uuid references public.employees(id) on delete set null,
  item text not null check (item in ('mask','gloves','hairnet','apron')),
  result boolean,
  confidence numeric check (confidence is null or confidence between 0 and 1),
  source_mode public.source_mode not null,
  observed_at timestamptz not null,
  retention_until timestamptz not null check (retention_until >= observed_at + interval '365 days')
);

create table public.sop_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  site_id uuid not null references public.sites(id) on delete restrict,
  workspace_id uuid not null references public.workspaces(id) on delete restrict,
  code text not null,
  name text not null,
  version text not null,
  source_mode public.source_mode not null,
  active boolean not null default true,
  unique (organization_id, code, version)
);

create table public.sop_stages (
  id uuid primary key default gen_random_uuid(),
  sop_id uuid not null references public.sop_templates(id) on delete cascade,
  sequence integer not null check (sequence > 0),
  name text not null,
  trigger_name text not null,
  target_min_seconds integer not null check (target_min_seconds >= 0),
  target_max_seconds integer not null check (target_max_seconds >= target_min_seconds),
  unique (sop_id, sequence)
);

create table public.incidents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  source_event_id uuid unique references public.events(id) on delete restrict,
  site_id uuid not null references public.sites(id) on delete restrict,
  workspace_id uuid not null references public.workspaces(id) on delete restrict,
  shift_id uuid not null references public.shifts(id) on delete restrict,
  title text not null,
  detail text not null,
  priority public.incident_priority not null,
  status public.incident_status not null default 'open',
  source_mode public.source_mode not null,
  owner text,
  due_at timestamptz not null,
  root_cause text,
  corrective_action text,
  resolution_note text,
  resolution_type text,
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  retention_until timestamptz not null
);

create table public.incident_activity (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents(id) on delete restrict,
  actor text not null,
  action text not null,
  detail text not null,
  created_at timestamptz not null default now()
);

create table public.alert_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  event_type text not null,
  severity public.event_severity not null,
  browser_enabled boolean not null default false,
  email_status text not null default 'not_configured',
  sms_status text not null default 'not_configured'
);

create table public.integration_configurations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  system_name text not null,
  status text not null check (status in ('not_connected','configured','connected','error')),
  mappings jsonb not null default '[]'::jsonb,
  external_requests_enabled boolean not null default false,
  updated_at timestamptz not null default now(),
  unique (organization_id, system_name)
);

create table public.audit_log (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  entity_type text not null,
  entity_id uuid not null,
  actor text not null,
  action text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  retention_until timestamptz not null
);

create index incidents_org_status_due_idx on public.incidents(organization_id, status, due_at);
create index ppe_observations_org_time_idx on public.ppe_observations(organization_id, observed_at desc);
create index audit_log_org_time_idx on public.audit_log(organization_id, created_at desc);

alter table public.sites enable row level security;
alter table public.workspaces enable row level security;
alter table public.shifts enable row level security;
alter table public.ppe_observations enable row level security;
alter table public.sop_templates enable row level security;
alter table public.sop_stages enable row level security;
alter table public.incidents enable row level security;
alter table public.incident_activity enable row level security;
alter table public.alert_rules enable row level security;
alter table public.integration_configurations enable row level security;
alter table public.audit_log enable row level security;

create policy "organization reads sites" on public.sites for select using (organization_id = public.current_organization_id());
create policy "organization reads workspaces" on public.workspaces for select using (exists (select 1 from public.sites s where s.id=workspaces.site_id and s.organization_id=public.current_organization_id()));
create policy "organization reads shifts" on public.shifts for select using (exists (select 1 from public.sites s where s.id=shifts.site_id and s.organization_id=public.current_organization_id()));
create policy "organization reads ppe observations" on public.ppe_observations for select using (organization_id = public.current_organization_id());
create policy "organization reads sop templates" on public.sop_templates for select using (organization_id = public.current_organization_id());
create policy "organization reads sop stages" on public.sop_stages for select using (exists (select 1 from public.sop_templates s where s.id=sop_stages.sop_id and s.organization_id=public.current_organization_id()));
create policy "organization reads incidents" on public.incidents for select using (organization_id = public.current_organization_id());
create policy "supervisors update incidents" on public.incidents for update using (organization_id = public.current_organization_id() and exists (select 1 from public.profiles p where p.id=auth.uid() and p.role in ('admin','supervisor'))) with check (organization_id = public.current_organization_id());
create policy "organization reads incident activity" on public.incident_activity for select using (exists (select 1 from public.incidents i where i.id=incident_activity.incident_id and i.organization_id=public.current_organization_id()));
create policy "organization reads alert rules" on public.alert_rules for select using (organization_id = public.current_organization_id());
create policy "organization reads integrations" on public.integration_configurations for select using (organization_id = public.current_organization_id());
create policy "organization reads audit log" on public.audit_log for select using (organization_id = public.current_organization_id());

alter publication supabase_realtime add table public.incidents;
alter publication supabase_realtime add table public.incident_activity;
