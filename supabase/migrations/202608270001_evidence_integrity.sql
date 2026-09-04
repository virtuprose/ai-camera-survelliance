alter table public.evidence
  add column if not exists snapshot_sha256 text,
  add column if not exists clip_sha256 text,
  add column if not exists snapshot_bytes bigint,
  add column if not exists clip_bytes bigint,
  add column if not exists updated_at timestamptz not null default now();

alter table public.evidence
  add constraint evidence_snapshot_sha256_format
    check (snapshot_sha256 is null or snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  add constraint evidence_clip_sha256_format
    check (clip_sha256 is null or clip_sha256 ~ '^[0-9a-f]{64}$'),
  add constraint evidence_snapshot_bytes_positive
    check (snapshot_bytes is null or snapshot_bytes > 0),
  add constraint evidence_clip_bytes_positive
    check (clip_bytes is null or clip_bytes > 0);
