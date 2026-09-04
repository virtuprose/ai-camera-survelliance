"use client";

import Link from "next/link";
import { AlertTriangle, BadgeCheck, CheckCircle2, CircleHelp, ShieldCheck, UserRound } from "lucide-react";
import { DataBoundary, MetricStrip, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnterprise } from "@/hooks/use-enterprise";
import { useEdgeState } from "@/hooks/use-edge";
import { formatDateTime } from "@/lib/format";
import type { PpeAssessmentState, PpeStatus } from "@/lib/types";

const ITEM_LABELS: Record<string, string> = {
  mask: "Mask",
  gloves: "Gloves",
  left_glove: "Left glove",
  right_glove: "Right glove",
  hairnet: "Hairnet",
  apron: "Apron",
};

function ppeRows(ppe: PpeStatus) {
  if (ppe.items) {
    return Object.entries(ppe.items).map(([key, item]) => ({
      key,
      label: ITEM_LABELS[key] ?? key.replaceAll("_", " "),
      state: item.state,
      required: item.required !== false,
    }));
  }
  return (["mask", "gloves", "hairnet", "apron"] as const).map((key) => ({
    key,
    label: ITEM_LABELS[key],
    state: (ppe[key] === true ? "detected" : ppe[key] === false ? "missing" : "checking") as PpeAssessmentState,
    required: true,
  }));
}

function assessmentCopy(state: PpeAssessmentState, required: boolean) {
  if (state === "detected") return { className: "is-safe", detail: "Controlled signal verified", verdict: "Verified" };
  if (state === "missing" && required) return { className: "is-critical", detail: "Stable missing state", verdict: "Violation" };
  if (state === "missing") return { className: "is-unknown", detail: "Missing · monitor only", verdict: "Not scored" };
  if (state === "not_visible") return { className: "is-unknown", detail: "Required region not visible", verdict: "Not scored" };
  if (state === "unavailable") return { className: "is-unknown", detail: "Assessment unavailable", verdict: "Not scored" };
  return { className: "is-unknown", detail: "Stability window in progress", verdict: "Checking" };
}

export function FoodSafetyView() {
  const { overview, workspaceId, context } = useEnterprise();
  const { state } = useEdgeState();
  const workspace = context.workspaces.find((item) => item.id === workspaceId) ?? context.workspaces[0];
  const ppeEvents = state.recentEvents.filter((event) => event.type === "ppe_violation");
  const employee = state.activeEmployee;
  const unknownCount = Math.max(0, 20 - overview.metrics.ppeDeterminateChecks);
  return <div className="page-shell enterprise-page">
    <PageHeader eyebrow="QA assurance · Hygiene" title="Food safety & PPE" description="Review personal protective equipment observations with clear confidence, identity method, and determinate-data boundaries." actions={<><SourceBadge mode={workspace.mode} /><Button asChild><Link href="/incidents">Review PPE incidents</Link></Button></>} />
    {workspace.mode !== "live" && <DataBoundary mode={workspace.mode} />}
    <MetricStrip items={[
      { label: "Determinate compliance", value: overview.metrics.ppeCompliance === null ? "—" : `${overview.metrics.ppeCompliance}%`, note: "Unknown results excluded", tone: (overview.metrics.ppeCompliance ?? 100) < 95 ? "warning" : "safe", icon: <ShieldCheck /> },
      { label: "Determinate checks", value: String(overview.metrics.ppeDeterminateChecks), note: "Included in denominator", icon: <CheckCircle2 /> },
      { label: "Unknown checks", value: String(unknownCount), note: "Retained, not scored", tone: unknownCount ? "warning" : "safe", icon: <CircleHelp /> },
      { label: "Open PPE events", value: String(ppeEvents.filter((event) => event.status === "new").length), note: "Current loaded ledger", tone: ppeEvents.some((event) => event.status === "new") ? "critical" : "safe", icon: <AlertTriangle /> },
    ]} />
    <section className="assurance-grid">
      <article className="panel assurance-subject-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Current observation</span><h2>Staff PPE observation</h2><p>PPE assessment begins from a person track; an optional badge can add identity later.</p></div>{employee && <StatusBadge tone={employee.employeeId ? "safe" : "info"} label={employee.employeeId ? "Badge identified" : "Identity optional"} />}</div><Separator />{employee ? <div className="assurance-employee"><div className="assurance-identity"><Avatar><AvatarImage src={employee.photoUrl ?? undefined} alt="" /><AvatarFallback>{employee.employeeId ? employee.displayName.slice(0, 2).toUpperCase() : "US"}</AvatarFallback></Avatar><div><strong>{employee.displayName}</strong><span>{employee.employeeId ?? `Track ${employee.trackId ?? "—"}`} · {employee.zone}</span><small>{employee.employeeId ? <><BadgeCheck /> Badge {employee.badgeMarkerId ?? "—"}; profile image is operator reference only</> : <><ShieldCheck /> PPE monitoring active without identity</>}</small></div></div><div className="assurance-ppe-list">{ppeRows(employee.ppe).map((item) => { const copy = assessmentCopy(item.state, item.required); return <div className={copy.className} key={item.key}><span>{item.state === "detected" ? <CheckCircle2 /> : item.state === "missing" && item.required ? <AlertTriangle /> : <CircleHelp />}</span><div><strong>{item.label}</strong><small>{copy.detail}</small></div><b>{copy.verdict}</b></div>; })}</div></div> : <div className="enterprise-empty"><UserRound /><strong>No staff member in camera view</strong><span>PPE monitoring starts automatically when a person enters the configured area. A badge is optional.</span></div>}</article>
      <aside className="panel policy-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Policy logic</span><h2>Scoring controls</h2><p>Conservative rules prevent uncertain images from being counted as failures.</p></div></div><Separator /><ol><li><span>1</span><div><strong>Detect and track the person</strong><p>The person track starts PPE assessment; identity is not required.</p></div></li><li><span>2</span><div><strong>Observe each visible PPE region</strong><p>Face and left/right hands are evaluated independently.</p></div></li><li><span>3</span><div><strong>Require persistence</strong><p>A stable missing state must persist before one deduplicated event is raised.</p></div></li><li><span>4</span><div><strong>Retain unknown results</strong><p>Occluded regions stay not scored; a badge or access-control signal may associate identity.</p></div></li></ol></aside>
    </section>
    <section className="panel enterprise-table-panel department-ledger"><div className="enterprise-panel-heading"><div><span className="eyebrow">Observation ledger</span><h2>Recent PPE exceptions</h2></div></div><Table><TableHeader><TableRow><TableHead>Observation</TableHead><TableHead>Employee</TableHead><TableHead>Zone</TableHead><TableHead>Confidence</TableHead><TableHead>Source</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{ppeEvents.length ? ppeEvents.map((event) => <TableRow key={event.id}><TableCell><strong>{event.title}</strong><small>{event.detail}</small></TableCell><TableCell>{event.employeeName ?? "Unresolved track"}</TableCell><TableCell>{event.zone ?? "—"}</TableCell><TableCell className="mono">{event.confidence ? `${Math.round(event.confidence * 100)}%` : "Unknown"}</TableCell><TableCell><SourceBadge mode={event.sourceMode} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={6}><div className="enterprise-empty"><CheckCircle2 /><strong>No PPE exceptions in the loaded ledger</strong><span>Controlled violations created from Tools will appear here and in the incident center.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
