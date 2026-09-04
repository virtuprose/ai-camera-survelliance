import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const EDGE_URL = process.env.EDGE_API_URL ?? "http://127.0.0.1:8787";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const upstreamUrl = new URL(path.join("/"), `${EDGE_URL}/`);
  upstreamUrl.search = request.nextUrl.search;

  try {
    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    const token = process.env.EDGE_DEVICE_TOKEN;
    if (token) headers.set("authorization", `Bearer ${token}`);
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
    const response = await fetch(upstreamUrl, { method: request.method, headers, body, cache: "no-store", signal: request.signal });
    return new NextResponse(response.body, { status: response.status, headers: response.headers });
  } catch {
    return NextResponse.json({ detail: "Local edge agent unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
