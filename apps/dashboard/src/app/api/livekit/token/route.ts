import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { AccessToken } from "livekit-server-sdk";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const serverUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!apiKey || !apiSecret || !serverUrl || !supabaseUrl || !supabaseAnonKey) {
    return NextResponse.json({ detail: "Cloud video is not configured" }, { status: 503 });
  }

  const bearer = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!bearer) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  const supabase = createClient(supabaseUrl, supabaseAnonKey, { auth: { persistSession: false } });
  const { data, error } = await supabase.auth.getUser(bearer);
  if (error || !data.user) return NextResponse.json({ detail: "Invalid cloud session" }, { status: 401 });

  const room = process.env.LIVEKIT_ROOM ?? "foodsafe-kitchen-01";
  const token = new AccessToken(apiKey, apiSecret, {
    identity: `dashboard-${data.user.id}`,
    name: data.user.email ?? "ORVIA AI Surveillance operator",
    ttl: "10m",
  });
  token.addGrant({ roomJoin: true, room, canPublish: false, canSubscribe: true });
  return NextResponse.json({ token: await token.toJwt(), serverUrl, room });
}
