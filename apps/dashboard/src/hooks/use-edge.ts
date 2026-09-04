"use client";

import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fallbackState, seedEvents } from "@/lib/demo-state";
import type { CameraCatalog, DemoEvent, DetectionState, EventStatus, LiveState } from "@/lib/types";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/supabase/client";

const STATE_POLL_MS = 1_000;
const EVENT_POLL_MS = 2_000;

interface CloudEventRow {
  id: string; device_id: string; track_id: number | null; occurred_at: string; type: string;
  title: string; detail: string; severity: DemoEvent["severity"]; source_mode: DemoEvent["sourceMode"];
  review_status: DemoEvent["status"]; employee_id: string | null; zone: string | null;
  confidence: number | null; retention_until: string; metadata: Record<string, unknown> | null;
  employees: { display_name: string } | { display_name: string }[] | null;
  evidence: { snapshot_path: string | null } | { snapshot_path: string | null }[] | null;
}

interface OperationsContextValue {
  state: LiveState;
  stateConnected: boolean;
  stateError: string | null;
  refreshState: () => Promise<void>;
  events: DemoEvent[];
  eventsConnected: boolean;
  eventsError: string | null;
  refreshEvents: () => Promise<void>;
  updateStatus: (id: string, status: EventStatus) => Promise<void>;
}

const OperationsContext = createContext<OperationsContextValue | null>(null);

function firstRelation<T>(value: T | T[] | null): T | null {
  return Array.isArray(value) ? value[0] ?? null : value;
}

async function cloudEvents(): Promise<DemoEvent[]> {
  const client = getSupabaseBrowserClient();
  if (!client) throw new Error("Supabase is not configured");
  const { data, error } = await client
    .from("events")
    .select("id,device_id,track_id,occurred_at,type,title,detail,severity,source_mode,review_status,employee_id,zone,confidence,retention_until,metadata,employees(display_name),evidence(snapshot_path)")
    .order("occurred_at", { ascending: false })
    .limit(250);
  if (error) throw error;
  return Promise.all(((data ?? []) as unknown as CloudEventRow[]).map(async (row) => {
    const employee = firstRelation(row.employees);
    const evidence = firstRelation(row.evidence);
    let evidenceUrl: string | null = null;
    if (evidence?.snapshot_path) {
      const signed = await client.storage.from("evidence").createSignedUrl(evidence.snapshot_path, 300);
      evidenceUrl = signed.data?.signedUrl ?? null;
    }
    return {
      id: row.id, deviceId: row.device_id, trackId: row.track_id, occurredAt: row.occurred_at,
      type: row.type, title: row.title, detail: row.detail, severity: row.severity,
      sourceMode: row.source_mode, status: row.review_status, employeeId: row.employee_id,
      employeeName: employee?.display_name ?? null, zone: row.zone, confidence: row.confidence,
      evidenceUrl, retentionUntil: row.retention_until, metadata: row.metadata ?? {},
    };
  }));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/edge${path}`, {
    ...init,
    cache: "no-store",
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(error?.detail ?? `Edge request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function OperationsDataProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<LiveState>(fallbackState);
  const [stateConnected, setStateConnected] = useState(false);
  const [stateError, setStateError] = useState<string | null>(null);
  const [events, setEvents] = useState<DemoEvent[]>(seedEvents);
  const [eventsConnected, setEventsConnected] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    try {
      setState(await request<LiveState>("/api/state"));
      setStateConnected(true);
      setStateError(null);
    } catch (reason) {
      setStateConnected(false);
      setStateError(reason instanceof Error ? reason.message : "Edge agent unavailable");
    }
  }, []);

  const refreshEvents = useCallback(async () => {
    try {
      const next = isSupabaseConfigured() ? await cloudEvents() : (await request<{ items: DemoEvent[] }>("/api/events")).items;
      setEvents(next);
      setEventsConnected(true);
      setEventsError(null);
    } catch (reason) {
      setEventsConnected(false);
      setEventsError(reason instanceof Error ? reason.message : "Event store unavailable");
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refreshState(), 0);
    const timer = window.setInterval(refreshState, STATE_POLL_MS);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refreshState]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refreshEvents(), 0);
    if (isSupabaseConfigured()) {
      const client = getSupabaseBrowserClient();
      let channel: ReturnType<NonNullable<typeof client>["channel"]> | null = null;
      let cancelled = false;
      void (async () => {
        if (!client) return;
        const { data: sessionData } = await client.auth.getSession();
        if (!sessionData.session || cancelled) return;
        client.realtime.setAuth(sessionData.session.access_token);
        const { data: profile } = await client.from("profiles").select("organization_id").maybeSingle();
        if (!profile?.organization_id || cancelled) return;
        channel = client.channel(`org:${profile.organization_id}:events`, { config: { private: true } })
          .on("postgres_changes", { event: "*", schema: "public", table: "events" }, () => void refreshEvents())
          .subscribe();
      })();
      return () => {
        cancelled = true;
        window.clearTimeout(initial);
        if (client && channel) void client.removeChannel(channel);
      };
    }
    const timer = window.setInterval(refreshEvents, EVENT_POLL_MS);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refreshEvents]);

  const updateStatus = useCallback(async (id: string, status: EventStatus) => {
    const client = getSupabaseBrowserClient();
    if (isSupabaseConfigured() && client) {
      const { error } = await client.from("events").update({ review_status: status, updated_at: new Date().toISOString() }).eq("id", id);
      if (error) throw error;
    } else {
      await request(`/api/events/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    }
    await refreshEvents();
  }, [refreshEvents]);

  const value = useMemo<OperationsContextValue>(() => ({
    state, stateConnected, stateError, refreshState, events, eventsConnected, eventsError, refreshEvents, updateStatus,
  }), [state, stateConnected, stateError, refreshState, events, eventsConnected, eventsError, refreshEvents, updateStatus]);

  return createElement(OperationsContext.Provider, { value }, children);
}

function useOperations() {
  const context = useContext(OperationsContext);
  if (!context) throw new Error("Operations hooks must be used within OperationsDataProvider");
  return context;
}

export function useEdgeState() {
  const value = useOperations();
  return { state: value.state, connected: value.stateConnected, error: value.stateError, refresh: value.refreshState };
}

export function useEvents() {
  const value = useOperations();
  return { events: value.events, connected: value.eventsConnected, error: value.eventsError, refresh: value.refreshEvents, updateStatus: value.updateStatus };
}

export async function runDemoAction(action: string, payload?: Record<string, unknown>) {
  return request<{ ok: boolean }>(`/api/demo/${action}`, { method: "POST", body: JSON.stringify(payload ?? {}) });
}

export async function getCameraCatalog() {
  return request<CameraCatalog>("/api/cameras");
}

export async function selectCamera(cameraId: string) {
  return request<CameraCatalog>("/api/cameras/active", {
    method: "PATCH",
    body: JSON.stringify({ cameraId }),
  });
}

export async function resetDetection() {
  return request<{ ok: true; detection: DetectionState }>("/api/detection/reset", { method: "POST" });
}
