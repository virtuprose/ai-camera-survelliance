"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Building2, CheckCircle2, Clock3, Radio, ShieldCheck, Thermometer } from "lucide-react";
import { DataBoundary, IncidentStatusBadge, MetricStrip, PriorityBadge, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnterprise } from "@/hooks/use-enterprise";
import { formatDateTime } from "@/lib/format";

export function CommandCenter() {
  const { overview, connected, context } = useEnterprise();
  const metrics = overview.metrics;
  return <div className="page-shell enterprise-page command-center-page">
    <PageHeader eyebrow="Enterprise operational assurance" title="Command center" description="A single exception-first view of food safety, process performance, cold-chain risk, and site readiness." actions={<><StatusBadge tone={connected ? "safe" : "warning"} label={connected ? "Enterprise data current" : "Local fallback"} /><Button asChild><Link href="/incidents">Open incident center <ArrowRight /></Link></Button></>} />
    {!connected && <DataBoundary mode="simulated">The enterprise service is reconnecting. Clearly marked local preview values remain visible without implying live production status.</DataBoundary>}
    <MetricStrip items={[
      { label: "Open critical incidents", value: String(metrics.openCriticalIncidents), note: "Requires QA review", tone: metrics.openCriticalIncidents ? "critical" : "safe", icon: <AlertTriangle /> },
      { label: "PPE compliance", value: metrics.ppeCompliance === null ? "—" : `${metrics.ppeCompliance}%`, note: `${metrics.ppeDeterminateChecks} determinate checks`, tone: (metrics.ppeCompliance ?? 100) < 95 ? "warning" : "safe", icon: <ShieldCheck /> },
      { label: "Process on time", value: metrics.processOnTime === null ? "—" : `${metrics.processOnTime}%`, note: `${metrics.completedProcesses} completed runs`, icon: <Clock3 /> },
      { label: "Active excursions", value: String(metrics.activeTemperatureExcursions), note: "Temperature outside limits", tone: metrics.activeTemperatureExcursions ? "critical" : "safe", icon: <Thermometer /> },
      { label: "Platform availability", value: `${metrics.systemAvailability}%`, note: "Local demo services", tone: "safe", icon: <Radio /> },
    ]} />

    <section className="command-main-grid">
      <article className="panel enterprise-table-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Exceptions requiring action</span><h2>Priority incident queue</h2><p>Critical and high-priority records are ordered by SLA due time.</p></div><Button variant="ghost" size="sm" asChild><Link href="/incidents">View all <ArrowRight /></Link></Button></div><Separator />
        <Table><TableHeader><TableRow><TableHead>Incident</TableHead><TableHead>Priority</TableHead><TableHead>Status</TableHead><TableHead>Owner</TableHead><TableHead>SLA due</TableHead><TableHead>Source</TableHead></TableRow></TableHeader><TableBody>{overview.priorityIncidents.length ? overview.priorityIncidents.map((incident) => <TableRow key={incident.id}><TableCell><Link className="record-link" href={`/incidents?id=${incident.id}`}><strong>{incident.title}</strong><small>{incident.zone ?? "Operational zone"}</small></Link></TableCell><TableCell><PriorityBadge priority={incident.priority} /></TableCell><TableCell><IncidentStatusBadge status={incident.status} /></TableCell><TableCell>{incident.owner ?? <span className="muted-copy">Unassigned</span>}</TableCell><TableCell><time className="mono" dateTime={incident.dueAt}>{formatDateTime(incident.dueAt)}</time></TableCell><TableCell><SourceBadge mode={incident.sourceMode} /></TableCell></TableRow>) : <TableRow><TableCell colSpan={6}><div className="enterprise-empty"><CheckCircle2 /><strong>No qualifying incidents</strong><span>New PPE, temperature, process, or inventory exceptions will appear here automatically.</span></div></TableCell></TableRow>}</TableBody></Table>
      </article>
      <aside className="panel site-health-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Network scope</span><h2>Facility readiness</h2><p>Live and planned locations are never combined.</p></div></div><Separator /><div className="site-health-list">{overview.siteHealth.map((site) => <article key={site.siteId}><span className={`site-health-icon tone-${site.mode}`}><Building2 /></span><div><strong>{site.name}</strong><small>{site.status === "planned" ? "Commissioning not started" : `${context.workspaces.filter((workspace) => workspace.siteId === site.siteId).length} configured workspaces`}</small></div><SourceBadge mode={site.mode} /><div className="site-health-progress"><span>{site.mode === "planned" ? "Planned" : "Operational coverage"}</span><Progress value={site.mode === "planned" ? 0 : 75} aria-label={`${site.name} readiness`} /></div><span className="site-incident-count mono">{site.openIncidents} open incidents</span></article>)}</div></aside>
    </section>

    <section className="command-module-row" aria-label="Department assurance modules">
      {[
        { href: "/food-safety", label: "Food safety & PPE", detail: "Determinate compliance, unknown checks, and staff observations", value: metrics.ppeCompliance === null ? "No data" : `${metrics.ppeCompliance}%`, icon: ShieldCheck },
        { href: "/processes", label: "Process assurance", detail: "SOP stages, target ranges, and timing exceptions", value: `${metrics.completedProcesses} complete`, icon: Clock3 },
        { href: "/cold-chain", label: "Cold chain", detail: "Continuous readings and excursion response", value: `${metrics.activeTemperatureExcursions} active`, icon: Thermometer },
      ].map(({ href, label, detail, value, icon: Icon }) => <Link className="command-module-card panel" href={href} key={href}><span><Icon /></span><div><strong>{label}</strong><p>{detail}</p></div><b className="mono">{value}</b><ArrowRight /></Link>)}
    </section>
  </div>;
}
