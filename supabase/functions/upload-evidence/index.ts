import { createClient } from "https://esm.sh/@supabase/supabase-js@2.112.3";

const responseHeaders = { "content-type": "application/json" };

async function sha256(value: string | ArrayBuffer) {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (request) => {
  if (request.method !== "POST") return new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers: responseHeaders });
  const token = request.headers.get("x-device-token");
  if (!token) return new Response(JSON.stringify({ error: "Device token required" }), { status: 401, headers: responseHeaders });

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });
  const { data: credential } = await supabase.from("device_credentials")
    .select("device_id,devices!inner(organization_id)")
    .eq("token_hash", await sha256(token)).eq("enabled", true).maybeSingle();
  if (!credential) return new Response(JSON.stringify({ error: "Invalid device token" }), { status: 401, headers: responseHeaders });

  const form = await request.formData();
  const file = form.get("file");
  const eventId = String(form.get("event_id") ?? "");
  const kind = String(form.get("kind") ?? "");
  const retentionUntil = String(form.get("retention_until") ?? "");
  if (!(file instanceof File) || !eventId || !["snapshot", "clip"].includes(kind)) {
    return new Response(JSON.stringify({ error: "Invalid evidence payload" }), { status: 422, headers: responseHeaders });
  }

  const device = credential.devices as unknown as { organization_id: string };
  const extension = kind === "snapshot" ? "jpg" : "mp4";
  const path = `${device.organization_id}/${credential.device_id}/${eventId}/${kind}.${extension}`;
  const { error: uploadError } = await supabase.storage.from("evidence").upload(path, file, {
    contentType: kind === "snapshot" ? "image/jpeg" : "video/mp4",
    upsert: true,
  });
  if (uploadError) return new Response(JSON.stringify({ error: uploadError.message }), { status: 422, headers: responseHeaders });

  const fileDigest = await sha256(await file.arrayBuffer());
  const { data: existing, error: lookupError } = await supabase.from("evidence")
    .select("snapshot_path,clip_path,snapshot_sha256,clip_sha256,snapshot_bytes,clip_bytes")
    .eq("event_id", eventId).maybeSingle();
  if (lookupError) return new Response(JSON.stringify({ error: lookupError.message }), { status: 422, headers: responseHeaders });

  const evidenceRow = {
    organization_id: device.organization_id,
    event_id: eventId,
    retention_until: retentionUntil,
    snapshot_path: kind === "snapshot" ? path : existing?.snapshot_path ?? null,
    clip_path: kind === "clip" ? path : existing?.clip_path ?? null,
    snapshot_sha256: kind === "snapshot" ? fileDigest : existing?.snapshot_sha256 ?? null,
    clip_sha256: kind === "clip" ? fileDigest : existing?.clip_sha256 ?? null,
    snapshot_bytes: kind === "snapshot" ? file.size : existing?.snapshot_bytes ?? null,
    clip_bytes: kind === "clip" ? file.size : existing?.clip_bytes ?? null,
    updated_at: new Date().toISOString(),
  };
  const { error } = await supabase.from("evidence").upsert(evidenceRow, { onConflict: "event_id" });
  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 422, headers: responseHeaders });
  return new Response(JSON.stringify({ ok: true, path }), { headers: responseHeaders });
});
