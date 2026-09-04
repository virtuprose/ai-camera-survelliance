"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type {
  DemoPersona,
  EnterpriseContext,
  EnterpriseIncident,
  EnterpriseOverview,
  EnterpriseProcessRun,
  IncidentStatus,
  OracleReadiness,
  SopTemplate,
} from "@/lib/types";

const MAIN_SITE = "11000000-0000-0000-0000-000000000001";
const KITCHEN = "12000000-0000-0000-0000-000000000001";

const fallbackContext: EnterpriseContext = {
  organization: { id: "10000000-0000-0000-0000-000000000001", name: "ORVIA AI Surveillance Demo" },
  sites: [
    { id: MAIN_SITE, code: "SITE-01", name: "Main Production Facility", timezone: "Asia/Kuwait", mode: "live" },
    { id: "11000000-0000-0000-0000-000000000002", code: "SITE-02", name: "Secondary Facility", timezone: "Asia/Kuwait", mode: "planned" },
  ],
  workspaces: [
    { id: KITCHEN, siteId: MAIN_SITE, code: "KIT-01", name: "Kitchen 01", departmentType: "production", mode: "live", deviceCode: "CAM-01" },
    { id: "12000000-0000-0000-0000-000000000002", siteId: MAIN_SITE, code: "RCV-01", name: "Receiving", departmentType: "receiving", mode: "simulated", deviceCode: null },
    { id: "12000000-0000-0000-0000-000000000003", siteId: MAIN_SITE, code: "CLD-01", name: "Cold Storage", departmentType: "cold_chain", mode: "simulated", deviceCode: null },
    { id: "12000000-0000-0000-0000-000000000004", siteId: MAIN_SITE, code: "INV-01", name: "Inventory Store", departmentType: "inventory", mode: "simulated", deviceCode: null },
  ],
  activeShift: { id: "13000000-0000-0000-0000-000000000001", name: "Day Shift", startsAt: "06:00", endsAt: "18:00" },
  personas: ["executive", "qa_supervisor", "operations", "it"],
  updatedAt: new Date(0).toISOString(),
};

const fallbackOverview: EnterpriseOverview = {
  metrics: { openCriticalIncidents: 0, ppeCompliance: 89, ppeDeterminateChecks: 18, processOnTime: null, completedProcesses: 0, activeTemperatureExcursions: 0, systemAvailability: 100 },
  priorityIncidents: [],
  siteHealth: [
    { siteId: MAIN_SITE, name: "Main Production Facility", mode: "live", status: "operational", openIncidents: 0 },
    { siteId: "11000000-0000-0000-0000-000000000002", name: "Secondary Facility", mode: "planned", status: "planned", openIncidents: 0 },
  ],
  updatedAt: new Date(0).toISOString(),
};

interface EnterpriseValue {
  context: EnterpriseContext;
  overview: EnterpriseOverview;
  incidents: EnterpriseIncident[];
  sops: SopTemplate[];
  processRuns: EnterpriseProcessRun[];
  oracle: OracleReadiness | null;
  persona: DemoPersona;
  workspaceId: string;
  connected: boolean;
  error: string | null;
  setPersona: (persona: DemoPersona) => void;
  setWorkspaceId: (id: string) => void;
  refresh: () => Promise<void>;
  getIncident: (id: string) => Promise<EnterpriseIncident>;
  updateIncident: (id: string, changes: Partial<EnterpriseIncident>) => Promise<EnterpriseIncident>;
  addIncidentNote: (id: string, detail: string) => Promise<EnterpriseIncident>;
  resetSimulated: () => Promise<{ events: number; incidents: number }>;
}

const EnterpriseContextState = createContext<EnterpriseValue | null>(null);

function initialPersona(): DemoPersona {
  if (typeof window === "undefined") return "qa_supervisor";
  const stored = window.localStorage.getItem("orvia.enterprise.persona.v1") as DemoPersona | null;
  return stored && fallbackContext.personas.includes(stored) ? stored : "qa_supervisor";
}

function initialWorkspace(): string {
  if (typeof window === "undefined") return KITCHEN;
  const stored = window.localStorage.getItem("orvia.enterprise.workspace.v1");
  return stored && fallbackContext.workspaces.some((item) => item.id === stored && item.mode !== "planned") ? stored : KITCHEN;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/edge${path}`, {
    ...init,
    cache: "no-store",
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Enterprise service failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function EnterpriseDataProvider({ children }: { children: React.ReactNode }) {
  const [context, setContext] = useState(fallbackContext);
  const [overview, setOverview] = useState(fallbackOverview);
  const [incidents, setIncidents] = useState<EnterpriseIncident[]>([]);
  const [sops, setSops] = useState<SopTemplate[]>([]);
  const [processRuns, setProcessRuns] = useState<EnterpriseProcessRun[]>([]);
  const [oracle, setOracle] = useState<OracleReadiness | null>(null);
  const [persona, setPersonaState] = useState<DemoPersona>(initialPersona);
  const [workspaceId, setWorkspaceIdState] = useState(initialWorkspace);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextContext, nextOverview, nextIncidents, nextSops, nextRuns, nextOracle] = await Promise.all([
        request<EnterpriseContext>("/api/enterprise/context"),
        request<EnterpriseOverview>("/api/enterprise/overview"),
        request<{ items: EnterpriseIncident[] }>("/api/enterprise/incidents?limit=100"),
        request<{ items: SopTemplate[] }>("/api/enterprise/sops"),
        request<{ items: EnterpriseProcessRun[] }>("/api/enterprise/process-runs?limit=50"),
        request<OracleReadiness>("/api/enterprise/integrations/oracle"),
      ]);
      setContext(nextContext); setOverview(nextOverview); setIncidents(nextIncidents.items);
      setSops(nextSops.items); setProcessRuns(nextRuns.items); setOracle(nextOracle);
      setConnected(true); setError(null);
    } catch (reason) {
      setConnected(false);
      setError(reason instanceof Error ? reason.message : "Enterprise service unavailable");
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);

  const setPersona = useCallback((next: DemoPersona) => {
    setPersonaState(next); localStorage.setItem("orvia.enterprise.persona.v1", next);
  }, []);
  const setWorkspaceId = useCallback((next: string) => {
    if (!context.workspaces.some((item) => item.id === next && item.mode !== "planned")) return;
    setWorkspaceIdState(next); localStorage.setItem("orvia.enterprise.workspace.v1", next);
  }, [context.workspaces]);

  const getIncident = useCallback((id: string) => request<EnterpriseIncident>(`/api/enterprise/incidents/${id}`), []);
  const actor = `${persona.replaceAll("_", " ")} (Demo View)`;
  const updateIncident = useCallback(async (id: string, changes: Partial<EnterpriseIncident>) => {
    const updated = await request<EnterpriseIncident>(`/api/enterprise/incidents/${id}`, { method: "PATCH", body: JSON.stringify({ ...changes, actor }) });
    await refresh(); return updated;
  }, [actor, refresh]);
  const addIncidentNote = useCallback(async (id: string, detail: string) => {
    const updated = await request<EnterpriseIncident>(`/api/enterprise/incidents/${id}/activity`, { method: "POST", body: JSON.stringify({ detail, actor }) });
    await refresh(); return updated;
  }, [actor, refresh]);
  const resetSimulated = useCallback(async () => {
    const result = await request<{ removed: { events: number; incidents: number } }>("/api/demo/reset", { method: "POST", body: JSON.stringify({ confirmation: "RESET SIMULATED DATA" }) });
    await refresh(); return result.removed;
  }, [refresh]);

  const value = useMemo<EnterpriseValue>(() => ({ context, overview, incidents, sops, processRuns, oracle, persona, workspaceId, connected, error, setPersona, setWorkspaceId, refresh, getIncident, updateIncident, addIncidentNote, resetSimulated }), [context, overview, incidents, sops, processRuns, oracle, persona, workspaceId, connected, error, setPersona, setWorkspaceId, refresh, getIncident, updateIncident, addIncidentNote, resetSimulated]);
  return <EnterpriseContextState.Provider value={value}>{children}</EnterpriseContextState.Provider>;
}

export function useEnterprise() {
  const value = useContext(EnterpriseContextState);
  if (!value) throw new Error("Enterprise hooks must be used within EnterpriseDataProvider");
  return value;
}

export function incidentStatusLabel(status: IncidentStatus) {
  return status.replaceAll("_", " ");
}
