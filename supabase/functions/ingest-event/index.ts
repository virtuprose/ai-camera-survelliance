import { createClient } from "https://esm.sh/@supabase/supabase-js@2.112.3";

const headers = { "content-type": "application/json" };
const mainSiteId = "11000000-0000-0000-0000-000000000001";
const kitchenWorkspaceId = "12000000-0000-0000-0000-000000000001";
const coldWorkspaceId = "12000000-0000-0000-0000-000000000003";
const inventoryWorkspaceId = "12000000-0000-0000-0000-000000000004";
const dayShiftId = "13000000-0000-0000-0000-000000000001";

async function sha256(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (request) => {
  if (request.method !== "POST") return new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers });
  const token = request.headers.get("x-device-token");
  if (!token) return new Response(JSON.stringify({ error: "Device token required" }), { status: 401, headers });

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });
  const tokenHash = await sha256(token);
  const { data: credential } = await supabase
    .from("device_credentials")
    .select("device_id,devices!inner(organization_id,code)")
    .eq("token_hash", tokenHash)
    .eq("enabled", true)
    .maybeSingle();
  if (!credential) return new Response(JSON.stringify({ error: "Invalid device token" }), { status: 401, headers });

  const body = await request.json();
  const device = credential.devices as unknown as { organization_id: string; code: string };
  await supabase.from("devices").update({ last_seen_at: new Date().toISOString() })
    .eq("id", credential.device_id);
  let employeeId: string | null = null;
  if (body.employeeId) {
    const { data: employee } = await supabase
      .from("employees")
      .select("id")
      .eq("organization_id", device.organization_id)
      .eq("employee_code", body.employeeId)
      .maybeSingle();
    employeeId = employee?.id ?? null;
  }
  const row = {
    id: body.id,
    organization_id: device.organization_id,
    device_id: credential.device_id,
    employee_id: employeeId,
    track_id: body.trackId,
    occurred_at: body.occurredAt,
    type: body.type,
    title: body.title,
    detail: body.detail,
    severity: body.severity,
    source_mode: body.sourceMode,
    review_status: body.status,
    zone: body.zone,
    confidence: body.confidence,
    evidence_path: body.evidenceUrl,
    retention_until: body.retentionUntil,
    metadata: body.metadata ?? {},
    updated_at: new Date().toISOString(),
    site_id: body.siteId ?? mainSiteId,
    workspace_id: body.workspaceId ?? (body.type?.startsWith("temperature") ? coldWorkspaceId : body.type?.startsWith("inventory") ? inventoryWorkspaceId : kitchenWorkspaceId),
    shift_id: body.shiftId ?? dayShiftId,
  };
  const { error } = await supabase.from("events").upsert(row, { onConflict: "id" });
  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 422, headers });

  if (body.type === "process_started" && body.metadata?.run_id) {
    await supabase.from("process_runs").upsert({
      id: body.metadata.run_id,
      organization_id: device.organization_id,
      device_id: credential.device_id,
      employee_id: employeeId,
      label: body.metadata.label ?? body.title,
      source_mode: body.sourceMode,
      started_at: body.occurredAt,
      status: "running",
      retention_until: body.retentionUntil,
      site_id: body.siteId ?? mainSiteId,
      workspace_id: body.workspaceId ?? kitchenWorkspaceId,
      shift_id: body.shiftId ?? dayShiftId,
    }, { onConflict: "id" });
  }
  if (body.type === "process_complete" && body.metadata?.run_id) {
    await supabase.from("process_runs").update({
      completed_at: body.occurredAt,
      elapsed_seconds: body.metadata.elapsed_seconds,
      status: "complete",
    }).eq("id", body.metadata.run_id);
  }
  if (["temperature_alert", "temperature_recovered"].includes(body.type) && body.metadata?.sensor_id) {
    await supabase.from("temperature_readings").upsert({
      id: body.id,
      organization_id: device.organization_id,
      device_id: credential.device_id,
      sensor_code: body.metadata.sensor_id,
      value_c: body.metadata.value_c,
      min_c: body.metadata.min_c,
      max_c: body.metadata.max_c,
      source_mode: body.sourceMode,
      sampled_at: body.occurredAt,
      retention_until: body.retentionUntil,
      site_id: body.siteId ?? mainSiteId,
      workspace_id: body.workspaceId ?? coldWorkspaceId,
      shift_id: body.shiftId ?? dayShiftId,
    }, { onConflict: "id" });
  }
  if (body.type === "inventory_movement" && body.metadata?.sku) {
    const { data: item } = await supabase.from("inventory_items").select("id")
      .eq("organization_id", device.organization_id).eq("sku", body.metadata.sku).maybeSingle();
    if (item) {
      await supabase.from("inventory_transactions").upsert({
        id: body.id,
        organization_id: device.organization_id,
        device_id: credential.device_id,
        inventory_item_id: item.id,
        employee_id: employeeId,
        direction: body.metadata.direction,
        quantity: body.metadata.quantity,
        source_mode: body.sourceMode,
        confidence: body.confidence,
        occurred_at: body.occurredAt,
        retention_until: body.retentionUntil,
        site_id: body.siteId ?? mainSiteId,
        workspace_id: body.workspaceId ?? inventoryWorkspaceId,
        shift_id: body.shiftId ?? dayShiftId,
      }, { onConflict: "id" });
      await supabase.from("inventory_items").update({ quantity: body.metadata.resulting_quantity }).eq("id", item.id);
    }
  }
  return new Response(JSON.stringify({ ok: true, id: body.id }), { status: 200, headers });
});
