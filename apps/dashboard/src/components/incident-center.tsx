"use client";
/* Evidence URLs are served by the local edge service and rendered as native images. */
/* eslint-disable @next/next/no-img-element */

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, FileImage, MessageSquarePlus, Search, ShieldAlert, UserRound } from "lucide-react";
import { toast } from "sonner";
import { IncidentStatusBadge, PriorityBadge, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useEnterprise } from "@/hooks/use-enterprise";
import { formatDateTime } from "@/lib/format";
import type { EnterpriseIncident, IncidentStatus } from "@/lib/types";

const owners = ["QA Supervisor", "Operations Lead", "Cold Chain Lead", "Inventory Controller"];
const statuses: Array<{ value: "all" | IncidentStatus; label: string }> = [{ value: "all", label: "All statuses" }, { value: "open", label: "Open" }, { value: "investigating", label: "Investigating" }, { value: "action_required", label: "Action required" }, { value: "resolved", label: "Resolved" }, { value: "closed", label: "Closed" }];

export function IncidentCenter() {
  const { incidents, getIncident, updateIncident, addIncidentNote } = useEnterprise();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EnterpriseIncident | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | IncidentStatus>("all");
  const [owner, setOwner] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [correctiveAction, setCorrectiveAction] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const filtered = useMemo(() => incidents.filter((item) => (status === "all" || item.status === status) && `${item.title} ${item.detail} ${item.owner ?? ""}`.toLowerCase().includes(query.toLowerCase())), [incidents, query, status]);
  const selected = detail?.id === selectedId ? detail : incidents.find((item) => item.id === selectedId) ?? filtered[0] ?? null;

  async function inspect(item: EnterpriseIncident) {
    setSelectedId(item.id); setOwner(item.owner ?? ""); setRootCause(item.rootCause ?? ""); setCorrectiveAction(item.correctiveAction ?? "");
    try { setDetail(await getIncident(item.id)); } catch (reason) { toast.error(reason instanceof Error ? reason.message : "Incident detail could not be loaded."); }
  }

  async function transition(nextStatus: IncidentStatus) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await updateIncident(selected.id, { status: nextStatus, owner: owner || selected.owner, rootCause: rootCause || selected.rootCause, correctiveAction: correctiveAction || selected.correctiveAction, resolutionNote: nextStatus === "resolved" ? "Corrective action recorded in controlled demo." : selected.resolutionNote, resolutionType: nextStatus === "resolved" ? "corrective_action" : selected.resolutionType });
      setDetail(updated); setSelectedId(updated.id); toast.success(`Incident moved to ${nextStatus.replaceAll("_", " ")}.`);
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : "Incident could not be updated."); }
    finally { setBusy(false); }
  }

  async function addNote() {
    if (!selected || !note.trim()) return;
    setBusy(true);
    try { const updated = await addIncidentNote(selected.id, note); setDetail(updated); setNote(""); toast.success("Audit note added."); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "Note could not be added."); }
    finally { setBusy(false); }
  }

  return <div className="page-shell enterprise-page incident-page">
    <PageHeader eyebrow="QA assurance · Corrective action" title="Incidents & evidence" description="Investigate qualifying exceptions through a controlled lifecycle with ownership, SLA due times, evidence, and immutable activity history." actions={<Button variant="outline" asChild><a href="/api/edge/api/enterprise/reports/audit-pack" download>Download audit pack</a></Button>} />
    <section className="incident-workbench">
      <article className="panel incident-queue"><div className="incident-filters"><div className="search-control"><Search /><Input aria-label="Search incidents" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, detail, or owner" /></div><Select value={status} onValueChange={(value) => setStatus(value as typeof status)}><SelectTrigger aria-label="Filter incident status"><SelectValue /></SelectTrigger><SelectContent>{statuses.map((item) => <SelectItem value={item.value} key={item.value}>{item.label}</SelectItem>)}</SelectContent></Select><span className="mono">{filtered.length} incidents</span></div><Separator /><div className="incident-list" aria-label="Incident queue">{filtered.length ? filtered.map((incident) => <button type="button" className={selected?.id === incident.id ? "is-selected" : ""} key={incident.id} onClick={() => void inspect(incident)}><span className={`incident-priority-marker tone-${incident.priority}`} /><div><span><PriorityBadge priority={incident.priority} /><IncidentStatusBadge status={incident.status} /></span><strong>{incident.title}</strong><small>{incident.detail}</small><footer><span><UserRound />{incident.owner ?? "Unassigned"}</span><time className="mono" dateTime={incident.dueAt}><Clock3 />{formatDateTime(incident.dueAt)}</time></footer></div></button>) : <div className="enterprise-empty"><CheckCircle2 /><strong>No incidents match these filters</strong><span>Clear the search or select another lifecycle status.</span></div>}</div></article>
      <aside className="panel incident-inspector">{selected ? <><div className="incident-inspector-head"><div><span className="eyebrow">Incident {selected.id.slice(0, 8)}</span><h2>{selected.title}</h2><p>{selected.detail}</p></div><div><PriorityBadge priority={selected.priority} /><IncidentStatusBadge status={selected.status} /><SourceBadge mode={selected.sourceMode} /></div></div><Separator /><div className="incident-inspector-scroll"><section className="incident-evidence"><div>{selected.evidenceUrl ? <img src={selected.evidenceUrl} alt={`Evidence for ${selected.title}`} /> : <><FileImage /><strong>Evidence snapshot unavailable</strong><span>The source event remains retained and reviewable.</span></>}</div><dl><div><dt>Employee</dt><dd>{selected.employeeName ?? "Unresolved"}</dd></div><div><dt>Zone</dt><dd>{selected.zone ?? "Operational zone"}</dd></div><div><dt>Confidence</dt><dd className="mono">{selected.confidence ? `${Math.round(selected.confidence * 100)}%` : "Unknown"}</dd></div><div><dt>Retention until</dt><dd className="mono">{formatDateTime(selected.retentionUntil)}</dd></div></dl></section><section className="incident-form"><h3>Ownership and corrective action</h3><label>Owner<Select value={owner || selected.owner || "unassigned"} onValueChange={(value) => setOwner(value === "unassigned" ? "" : value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="unassigned">Unassigned</SelectItem>{owners.map((item) => <SelectItem value={item} key={item}>{item}</SelectItem>)}</SelectContent></Select></label><label>Root cause<textarea value={rootCause} onChange={(event) => setRootCause(event.target.value)} placeholder="Required before resolution" /></label><label>Corrective action<textarea value={correctiveAction} onChange={(event) => setCorrectiveAction(event.target.value)} placeholder="Required before resolution" /></label><div className="incident-actions"><Button disabled={busy || !owner} variant="outline" onClick={() => void transition("investigating")}>Start investigation</Button><Button disabled={busy || !owner} variant="outline" onClick={() => void transition("action_required")}>Require action</Button><Button disabled={busy || !rootCause.trim() || !correctiveAction.trim()} onClick={() => void transition("resolved")}>Resolve incident</Button>{selected.status === "resolved" && <Button disabled={busy} variant="outline" onClick={() => void transition("closed")}>Close</Button>}</div></section><section className="incident-activity"><h3>Audit activity</h3><div className="activity-compose"><Input aria-label="Add incident activity note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add an investigation note" /><Button size="sm" disabled={busy || !note.trim()} onClick={() => void addNote()}><MessageSquarePlus />Add note</Button></div><ol>{selected.activity?.length ? selected.activity.map((item) => <li key={item.id}><span>{item.action === "created" ? <ShieldAlert /> : <MessageSquarePlus />}</span><div><strong>{item.actor}</strong><p>{item.detail}</p><time className="mono" dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time></div></li>) : <li className="activity-empty"><AlertTriangle /><span>Select this incident again to load its complete audit history.</span></li>}</ol></section></div></> : <div className="enterprise-empty"><ShieldAlert /><strong>No incident selected</strong><span>Select an incident from the queue to review evidence and corrective action.</span></div>}</aside>
    </section>
  </div>;
}
