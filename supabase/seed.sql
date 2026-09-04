insert into public.organizations (id, name)
values ('10000000-0000-0000-0000-000000000001', 'ORVIA AI Surveillance Demo')
on conflict (id) do nothing;

insert into public.devices (id, organization_id, code, label, source_type)
values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'CAM-01',
  'Kitchen 01 camera',
  'avfoundation'
)
on conflict (id) do nothing;

insert into public.employees (id, organization_id, employee_code, display_name, badge_marker_id, photo_url)
values
(
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'EMP-001',
  'Demo Operator A',
  101,
  null
),
(
  '30000000-0000-0000-0000-000000000002',
  '10000000-0000-0000-0000-000000000001',
  'EMP-002',
  'Demo Operator B',
  102,
  null
)
on conflict (id) do nothing;

insert into public.inventory_items (organization_id, sku, label, marker_id, quantity)
values
  ('10000000-0000-0000-0000-000000000001', 'SKU-001', 'Product A', 301, 5),
  ('10000000-0000-0000-0000-000000000001', 'SKU-002', 'Product B', 302, 8),
  ('10000000-0000-0000-0000-000000000001', 'SKU-003', 'Product C', 303, 3),
  ('10000000-0000-0000-0000-000000000001', 'SKU-004', 'Product D', 304, 6),
  ('10000000-0000-0000-0000-000000000001', 'SKU-005', 'Product E', 305, 4)
on conflict (organization_id, sku) do nothing;

-- After creating the first Auth user, attach it to the demo organization:
-- insert into public.profiles(id, organization_id, display_name, role)
-- values ('AUTH_USER_UUID', '10000000-0000-0000-0000-000000000001', 'Demo Supervisor', 'admin');

-- Generate a 32+ byte device token and store only its SHA-256 digest:
-- insert into public.device_credentials(device_id, token_hash)
-- values ('20000000-0000-0000-0000-000000000001', encode(digest('DEVICE_TOKEN', 'sha256'), 'hex'));
