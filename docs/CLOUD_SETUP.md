# Optional cloud activation

The local demo does not require cloud credentials. Activate this only after receiving client-owned accounts.

## Supabase

1. Create a client-owned Supabase project and install/authenticate the Supabase CLI.
2. Link this repository and apply all migrations in timestamp order, including `202608270001_evidence_integrity.sql`, then apply `supabase/seed.sql`.
3. Create the supervisor Auth user, then insert its UUID into `public.profiles` using the commented seed statement.
4. Generate a 32-byte device token. Store only its SHA-256 digest in `public.device_credentials`.
5. Deploy `ingest-event` and `upload-evidence` with JWT verification disabled; both authenticate the custom device token.
6. Put function URLs and the raw device token only in `services/edge/.env`.
7. Put the project URL and anon key in the dashboard environment. Keep the Supabase service-role key only in Supabase function secrets.

## LiveKit Cloud

1. Create a client-owned LiveKit Cloud project and room credentials.
2. Put URL/key/secret in the edge environment so Camera 01 can publish the silent annotated track.
3. Put URL/key/secret in Vercel server environment. The browser token route first validates the user's Supabase session and issues a 10-minute subscribe-only token.
4. Never expose `LIVEKIT_API_SECRET` through a `NEXT_PUBLIC_` variable.

## Vercel

1. Deploy `apps/dashboard` as the project root or use the repository root with the dashboard build script.
2. Add Supabase and LiveKit environment variables for Preview and Production.
3. Verify auth, private evidence access, LiveKit recovery, and all dashboard routes in the deployed domain.

## Required acceptance evidence

- Supabase migration output with no errors.
- RLS test using two organizations.
- Private evidence URL denied when signed out and allowed when signed in.
- Device token rejection/acceptance tests.
- Offline event created locally, then synchronized exactly once after reconnection.
- Uploaded snapshot and clip retain separate SHA-256 digests and byte counts in the evidence row.
- LiveKit annotated video visible to a signed-in dashboard user.
