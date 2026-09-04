"use client";
/* Evidence can use signed local/cloud URLs and intentionally bypasses Next image optimization. */
/* eslint-disable @next/next/no-img-element */

import { useMemo, useState } from "react";
import { Archive, Check, Download, Eye, Filter, RotateCcw, Search, X } from "lucide-react";
import { toast } from "sonner";
import { useEvents } from "@/hooks/use-edge";
import { formatDateTime } from "@/lib/format";
import type { DemoEvent, EventStatus, Severity, SourceMode } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { SeverityBadge, StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Period = "24h" | "7d" | "30d" | "all";

function EvidenceDetails({ selected, busy, onReview }: { selected: DemoEvent | null; busy: boolean; onReview: (status: EventStatus) => Promise<void> }) {
  if (!selected) return <div className="evidence-empty"><Eye /><strong>Select an event</strong><span>Evidence, confidence, retention, and review actions will appear here.</span></div>;
  return <div className="evidence-details">
    <div className="evidence-preview">{selected.evidenceUrl ? <img src={selected.evidenceUrl} alt={`Evidence for ${selected.title}`} /> : <div><Eye /><strong>Evidence pending</strong><span>No snapshot is attached to this demonstration event.</span></div>}<StatusBadge tone={selected.sourceMode === "simulated" ? "simulated" : "neutral"} label={selected.sourceMode} /></div>
    <div className="evidence-content"><div className="evidence-heading"><span className="eyebrow">{selected.type.replaceAll("_", " ")}</span><SeverityBadge severity={selected.severity} /></div><h2>{selected.title}</h2><p>{selected.detail}</p><Separator /><dl className="detail-list"><div><dt>Occurred</dt><dd>{formatDateTime(selected.occurredAt)}</dd></div><div><dt>Device</dt><dd>{selected.deviceId}</dd></div><div><dt>Employee</dt><dd>{selected.employeeName ?? "Not assigned"}</dd></div><div><dt>Track</dt><dd>{selected.trackId === null ? "Not assigned" : `Track ${selected.trackId}`}</dd></div><div><dt>Zone</dt><dd>{selected.zone ?? "System"}</dd></div><div><dt>Confidence</dt><dd>{selected.confidence === null ? "Not available" : `${Math.round(selected.confidence * 100)}%`}</dd></div><div><dt>Retained until</dt><dd>{formatDateTime(selected.retentionUntil)}</dd></div></dl><div className="review-actions"><Button disabled={busy || selected.status === "acknowledged"} onClick={() => void onReview("acknowledged")}><Check />Acknowledge</Button><Button variant="outline" disabled={busy || selected.status === "dismissed"} onClick={() => void onReview("dismissed")}><X />Dismiss false alert</Button></div><p className="review-note">The original detection remains in the audit trail when review status changes.</p></div>
  </div>;
}

export function EventExplorer() {
  const { events, connected, error, updateStatus } = useEvents();
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [source, setSource] = useState<SourceMode | "all">("all");
  const [reviewStatus, setReviewStatus] = useState<EventStatus | "all">("all");
  const [employee, setEmployee] = useState("all");
  const [period, setPeriod] = useState<Period>("all");
  const [selected, setSelected] = useState<DemoEvent | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [referenceTime] = useState(() => Date.now());

  const employees = useMemo(() => Array.from(new Set(events.map((event) => event.employeeName).filter((value): value is string => Boolean(value)))).sort(), [events]);
  const filtered = useMemo(() => {
    const cutoff = period === "all" ? 0 : referenceTime - ({ "24h": 1, "7d": 7, "30d": 30 }[period] * 86_400_000);
    return events.filter((event) => {
      const haystack = `${event.title} ${event.detail} ${event.employeeName ?? ""} ${event.zone ?? ""}`.toLowerCase();
      return haystack.includes(query.toLowerCase()) && (severity === "all" || event.severity === severity) && (source === "all" || event.sourceMode === source) && (reviewStatus === "all" || event.status === reviewStatus) && (employee === "all" || event.employeeName === employee) && new Date(event.occurredAt).getTime() >= cutoff;
    });
  }, [employee, events, period, query, referenceTime, reviewStatus, severity, source]);
  const activeFilterCount = [severity, source, reviewStatus, employee, period].filter((value) => value !== "all").length + (query ? 1 : 0);

  async function review(status: EventStatus) {
    if (!selected) return;
    const previous = selected.status;
    setBusy(true);
    try {
      await updateStatus(selected.id, status);
      setSelected({ ...selected, status });
      toast.success(status === "acknowledged" ? "Event acknowledged" : "Marked as false alert", { description: "The original detection remains retained.", action: { label: "Undo", onClick: () => void updateStatus(selected.id, previous) } });
    } catch { toast.error("Review status was not saved", { description: "Check the event store connection and try again." }); }
    finally { setBusy(false); }
  }

  function inspect(event: DemoEvent) {
    setSelected(event);
    if (window.matchMedia("(max-width: 1050px)").matches) setMobileOpen(true);
  }

  function clearFilters() { setQuery(""); setSeverity("all"); setSource("all"); setReviewStatus("all"); setEmployee("all"); setPeriod("all"); }

  function exportCsv() {
    const fields: (keyof DemoEvent)[] = ["id", "deviceId", "trackId", "occurredAt", "type", "title", "severity", "sourceMode", "status", "employeeName", "zone", "confidence", "retentionUntil"];
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const csv = [fields.join(","), ...filtered.map((event) => fields.map((field) => escape(event[field])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "food-safety-events.csv"; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="page-shell events-page">
    <PageHeader eyebrow="Compliance history" title="Events & evidence" description="Inspect detections, review supporting evidence, and record an operator decision without changing the original audit record." actions={<><StatusBadge tone={connected ? "safe" : "warning"} label={connected ? "Live event store" : "Fallback preview"} /><Button variant="outline" onClick={exportCsv}><Download />Export CSV</Button></>} />
    {!connected && <div className="connection-alert is-warning" role="status"><Archive /><span><strong>Event store is not current.</strong>{error ?? "Showing fallback preview records until the connection recovers."}</span></div>}
    <section className="filter-panel panel" aria-label="Event filters"><div className="search-control"><Search /><Input aria-label="Search events" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search employee, zone, or event" /></div><Select value={severity} onValueChange={(value) => setSeverity(value as Severity | "all")}><SelectTrigger aria-label="Filter severity"><Filter /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All severity</SelectItem><SelectItem value="critical">Critical</SelectItem><SelectItem value="warning">Warning</SelectItem><SelectItem value="info">Information</SelectItem></SelectContent></Select><Select value={source} onValueChange={(value) => setSource(value as SourceMode | "all")}><SelectTrigger aria-label="Filter source"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All sources</SelectItem><SelectItem value="real">Real</SelectItem><SelectItem value="simulated">Simulated</SelectItem></SelectContent></Select><Select value={reviewStatus} onValueChange={(value) => setReviewStatus(value as EventStatus | "all")}><SelectTrigger aria-label="Filter review status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All review states</SelectItem><SelectItem value="new">New</SelectItem><SelectItem value="acknowledged">Acknowledged</SelectItem><SelectItem value="dismissed">Dismissed</SelectItem></SelectContent></Select><Select value={employee} onValueChange={setEmployee}><SelectTrigger aria-label="Filter employee"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All employees</SelectItem>{employees.map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}</SelectContent></Select><Select value={period} onValueChange={(value) => setPeriod(value as Period)}><SelectTrigger aria-label="Filter date"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All dates</SelectItem><SelectItem value="24h">Last 24 hours</SelectItem><SelectItem value="7d">Last 7 days</SelectItem><SelectItem value="30d">Last 30 days</SelectItem></SelectContent></Select><div className="filter-summary"><span className="mono">{filtered.length} records</span>{activeFilterCount > 0 && <Button variant="ghost" size="sm" onClick={clearFilters}><RotateCcw />Clear {activeFilterCount}</Button>}</div></section>

    <div className="events-layout"><section className="event-table-panel panel" aria-label="Events"><ScrollArea className="event-scroll"><Table><TableHeader><TableRow><TableHead>Event</TableHead><TableHead>Severity</TableHead><TableHead>Source</TableHead><TableHead>Status</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{filtered.length ? filtered.map((event) => <TableRow key={event.id} data-state={selected?.id === event.id ? "selected" : undefined}><TableCell><button className="event-inspect-button" onClick={() => inspect(event)}><span className={`severity-dot ${event.severity}`} /><span><strong>{event.title}</strong><small>{event.employeeName ?? "System"} · {event.zone ?? "No zone"}</small></span></button></TableCell><TableCell><SeverityBadge severity={event.severity} /></TableCell><TableCell><StatusBadge tone={event.sourceMode === "simulated" ? "simulated" : "neutral"} label={event.sourceMode} /></TableCell><TableCell><StatusBadge tone={event.status === "new" ? "warning" : "neutral"} label={event.status} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={5}><div className="empty-state"><Archive /><strong>No matching events</strong><span>Change or clear the active filters, or wait for a new event.</span>{activeFilterCount > 0 && <Button variant="outline" size="sm" onClick={clearFilters}>Clear filters</Button>}</div></TableCell></TableRow>}</TableBody></Table></ScrollArea></section><aside className="evidence-panel panel" aria-label="Selected event evidence"><EvidenceDetails selected={selected} busy={busy} onReview={review} /></aside></div>

    <Sheet open={mobileOpen} onOpenChange={setMobileOpen}><SheetContent side="bottom" className="mobile-evidence-sheet"><SheetHeader><SheetTitle>Event evidence</SheetTitle><SheetDescription>Review the selected detection and record a decision.</SheetDescription></SheetHeader><ScrollArea className="mobile-evidence-scroll"><EvidenceDetails selected={selected} busy={busy} onReview={review} /></ScrollArea></SheetContent></Sheet>
  </div>;
}
