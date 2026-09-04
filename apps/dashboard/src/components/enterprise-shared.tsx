import type { ReactNode } from "react";
import { AlertTriangle, CircleHelp, Database, Radio } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import type { IncidentPriority, IncidentStatus, SourceMode, WorkspaceMode } from "@/lib/types";

export function SourceBadge({ mode }: { mode: SourceMode | WorkspaceMode }) {
  if (mode === "live" || mode === "real") return <StatusBadge tone="safe" label={mode === "live" ? "Live" : "Real"} />;
  if (mode === "simulated") return <StatusBadge tone="simulated" label="Simulated" />;
  return <StatusBadge tone="neutral" label="Planned" />;
}

export function PriorityBadge({ priority }: { priority: IncidentPriority }) {
  const tone = priority === "critical" ? "critical" : priority === "high" ? "warning" : "neutral";
  return <StatusBadge tone={tone} label={priority} />;
}

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const tone = status === "open" ? "critical" : status === "investigating" || status === "action_required" ? "warning" : status === "resolved" || status === "closed" ? "safe" : "neutral";
  return <StatusBadge tone={tone} label={status.replaceAll("_", " ")} />;
}

export function MetricStrip({ items }: { items: Array<{ label: string; value: string; note: string; tone?: "safe" | "warning" | "critical" | "neutral"; icon: ReactNode }> }) {
  return <section className="enterprise-metric-strip panel" aria-label="Operational summary">{items.map((item) => <article className={`enterprise-metric tone-${item.tone ?? "neutral"}`} key={item.label}><span className="enterprise-metric-icon">{item.icon}</span><div><span>{item.label}</span><strong className="mono">{item.value}</strong><small>{item.note}</small></div></article>)}</section>;
}

export function DataBoundary({ mode = "simulated", children }: { mode?: SourceMode | WorkspaceMode; children?: ReactNode }) {
  return <div className={`data-boundary tone-${mode}`}><span>{mode === "simulated" ? <Database /> : mode === "planned" ? <CircleHelp /> : <Radio />}</span><div><strong>{mode === "simulated" ? "Simulated workspace" : mode === "planned" ? "Planned workspace" : "Live operational data"}</strong><p>{children ?? (mode === "simulated" ? "Records are interactive for the presentation and remain explicitly labelled in events, reports, and exports." : mode === "planned" ? "No operational data is available until this facility is commissioned." : "This workspace is receiving data from the local edge service.")}</p></div></div>;
}

export function EmptyModuleState({ title, detail }: { title: string; detail: string }) {
  return <div className="enterprise-empty"><AlertTriangle /><strong>{title}</strong><span>{detail}</span></div>;
}
