"use client";

import { AlertTriangle, CheckCircle2, Radio, Thermometer, TimerReset } from "lucide-react";
import { DataBoundary, MetricStrip, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnterprise } from "@/hooks/use-enterprise";
import { useEdgeState } from "@/hooks/use-edge";
import { formatDateTime } from "@/lib/format";

export function ColdChainView() {
  const { overview } = useEnterprise();
  const { state } = useEdgeState();
  const temperature = state.temperature;
  const events = state.recentEvents.filter((event) => event.type === "temperature_alert");
  const range = Math.max(1, temperature.maxC - temperature.minC);
  const position = Math.max(0, Math.min(100, (temperature.valueC - temperature.minC) / range * 100));
  return <div className="page-shell enterprise-page">
    <PageHeader eyebrow="Operations · Cold-chain assurance" title="Cold chain" description="Monitor safe temperature limits, escalation status, and retained excursion evidence for refrigerated operations." actions={<><SourceBadge mode="simulated" /><StatusBadge tone={temperature.status === "safe" ? "safe" : "critical"} label={temperature.status === "safe" ? "Within limits" : "Excursion active"} /></>} />
    <DataBoundary mode="simulated">The first demo uses a labelled software sensor. The production adapter boundary supports a later serial or MQTT temperature probe.</DataBoundary>
    <MetricStrip items={[
      { label: "Current temperature", value: `${temperature.valueC.toFixed(1)}°C`, note: `Safe ${temperature.minC}–${temperature.maxC}°C`, tone: temperature.status === "safe" ? "safe" : "critical", icon: <Thermometer /> },
      { label: "Active excursions", value: String(overview.metrics.activeTemperatureExcursions), note: "Unreviewed threshold events", tone: overview.metrics.activeTemperatureExcursions ? "critical" : "safe", icon: <AlertTriangle /> },
      { label: "Sensor freshness", value: "< 5s", note: "Local polling interval", tone: "safe", icon: <Radio /> },
      { label: "Alert target", value: "2 sec", note: "Controlled threshold test", icon: <TimerReset /> },
    ]} />
    <section className="cold-chain-grid">
      <article className={`panel temperature-hero tone-${temperature.status}`}><div className="enterprise-panel-heading"><div><span className="eyebrow">Cold Storage · Sensor TEMP-01</span><h2>Live threshold position</h2><p>Visible status and numerical readings are provided together; colour is never the only signal.</p></div><SourceBadge mode={temperature.sourceMode} /></div><Separator /><div className="temperature-dial"><span>Current</span><strong className="mono">{temperature.valueC.toFixed(1)}<small>°C</small></strong><StatusBadge tone={temperature.status === "safe" ? "safe" : "critical"} label={temperature.status === "safe" ? "Safe range" : "Outside safe range"} /></div><div className="temperature-range"><div><span>Minimum</span><b className="mono">{temperature.minC}°C</b></div><Progress value={position} aria-label="Temperature position within configured limits" /><div><span>Maximum</span><b className="mono">{temperature.maxC}°C</b></div></div><dl className="temperature-controls"><div><dt>Last sample</dt><dd className="mono">{formatDateTime(temperature.sampledAt)}</dd></div><div><dt>Control mode</dt><dd>Monitor and alert only</dd></div><div><dt>Automatic appliance control</dt><dd>Excluded</dd></div></dl></article>
      <aside className="panel escalation-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Escalation policy</span><h2>Threshold response</h2><p>Each step remains auditable even when an external channel is not configured.</p></div></div><Separator /><ol><li className={temperature.status !== "safe" ? "is-active" : "is-complete"}><span>{temperature.status === "safe" ? <CheckCircle2 /> : <AlertTriangle />}</span><div><strong>Detect threshold crossing</strong><small>Raise within two seconds of a qualifying sample.</small></div></li><li><span>2</span><div><strong>Browser alert</strong><small>Visible alert always; optional chime if explicitly enabled.</small></div></li><li><span>3</span><div><strong>Create incident</strong><small>Critical queue item receives an SLA due time.</small></div></li><li><span>4</span><div><strong>External notification</strong><small>Email and SMS are not configured in this demo.</small></div></li></ol></aside>
    </section>
    <section className="panel enterprise-table-panel department-ledger"><div className="enterprise-panel-heading"><div><span className="eyebrow">Excursion ledger</span><h2>Temperature alerts</h2></div></div><Table><TableHeader><TableRow><TableHead>Alert</TableHead><TableHead>Zone</TableHead><TableHead>Status</TableHead><TableHead>Source</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{events.length ? events.map((event) => <TableRow key={event.id}><TableCell><strong>{event.title}</strong><small>{event.detail}</small></TableCell><TableCell>{event.zone ?? "Cold Storage"}</TableCell><TableCell><StatusBadge tone={event.status === "new" ? "critical" : "safe"} label={event.status} /></TableCell><TableCell><SourceBadge mode={event.sourceMode} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={5}><div className="enterprise-empty"><CheckCircle2 /><strong>No temperature excursions recorded</strong><span>Use Tools to demonstrate threshold escalation and recovery.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
