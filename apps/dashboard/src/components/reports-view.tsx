"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Clock3, Download, ShieldCheck, Thermometer, UsersRound } from "lucide-react";
import { useEvents } from "@/hooks/use-edge";
import { useEnterprise } from "@/hooks/use-enterprise";
import { formatDateTime } from "@/lib/format";
import type { DemoEvent } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Period = "24h" | "7d" | "30d";
const periodDays: Record<Period, number> = { "24h": 1, "7d": 7, "30d": 30 };
const categories = [
  { type: "ppe_violation", label: "PPE violations" },
  { type: "temperature_alert", label: "Temperature" },
  { type: "process_complete", label: "Processes" },
  { type: "inventory_movement", label: "Inventory" },
  { type: "employee_entry", label: "Attendance" },
];
const chartConfig = { count: { label: "Events", color: "var(--chart-1)" } } satisfies ChartConfig;

export function ReportsView() {
  const { events, connected } = useEvents();
  const { overview, context } = useEnterprise();
  const [period, setPeriod] = useState<Period>("24h");
  const [referenceTime] = useState(() => Date.now());
  const filtered = useMemo(() => {
    const cutoff = referenceTime - periodDays[period] * 86_400_000;
    return events.filter((event) => new Date(event.occurredAt).getTime() >= cutoff);
  }, [events, period, referenceTime]);

  const tempAlerts = filtered.filter((event) => event.type === "temperature_alert").length;
  const reviewed = filtered.filter((event) => event.status !== "new").length;
  const reviewRate = filtered.length ? Math.round((reviewed / filtered.length) * 100) : 0;
  const compliance = overview.metrics.ppeCompliance;
  const chartData = categories.map(({ type, label }) => ({ label, count: filtered.filter((event) => event.type === type).length }));
  const simulatedCount = filtered.filter((event) => event.sourceMode === "simulated").length;
  const recent = filtered.slice(0, 8);
  const periodLabel = period === "24h" ? "Last 24 hours" : `Last ${periodDays[period]} days`;

  const metrics = [
    { label: "PPE compliance", value: compliance === null ? "—" : `${compliance}%`, note: `${overview.metrics.ppeDeterminateChecks} determinate checks`, icon: ShieldCheck, tone: compliance !== null && compliance < 95 ? "warning" : "safe" },
    { label: "Process on time", value: overview.metrics.processOnTime === null ? "—" : `${overview.metrics.processOnTime}%`, note: `${overview.metrics.completedProcesses} completed runs`, icon: Clock3, tone: overview.metrics.processOnTime !== null && overview.metrics.processOnTime < 90 ? "warning" : "neutral" },
    { label: "Temperature excursions", value: String(tempAlerts), note: "Real and simulated", icon: Thermometer, tone: tempAlerts ? "warning" : "safe" },
    { label: "Events reviewed", value: `${reviewRate}%`, note: `${reviewed} of ${filtered.length}`, icon: UsersRound, tone: reviewRate === 100 ? "safe" : "neutral" },
  ] as const;

  function exportCsv() {
    const fields: (keyof DemoEvent)[] = ["id", "occurredAt", "type", "title", "severity", "sourceMode", "status", "employeeName", "zone", "confidence"];
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const csv = [fields.join(","), ...filtered.map((event) => fields.map((field) => escape(event[field])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `food-safety-report-${period}.csv`; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="page-shell reports-page">
    <PageHeader eyebrow={`${context.sites[0]?.name ?? "Main facility"} · ${context.activeShift.name}`} title="Reports & audit" description="Review compliance, process performance, and exceptions with explicit denominator and source boundaries from the retained operational ledger." actions={<><StatusBadge tone={connected ? "safe" : "warning"} label={connected ? "Current" : "Fallback preview"} /><Button variant="outline" asChild><a href="/api/edge/api/enterprise/reports/audit-pack" download><Download />Audit PDF</a></Button><Button variant="outline" onClick={exportCsv}><Download />CSV ledger</Button></>} />
    <div className="report-period-bar"><div><span>Reporting period</span><strong>{periodLabel}</strong></div><Tabs value={period} onValueChange={(value) => setPeriod(value as Period)}><TabsList><TabsTrigger value="24h">24 hours</TabsTrigger><TabsTrigger value="7d">7 days</TabsTrigger><TabsTrigger value="30d">30 days</TabsTrigger></TabsList><TabsContent className="sr-only" value="24h">Showing the last 24 hours.</TabsContent><TabsContent className="sr-only" value="7d">Showing the last 7 days.</TabsContent><TabsContent className="sr-only" value="30d">Showing the last 30 days.</TabsContent></Tabs></div>
    <section className="metric-band panel" aria-label="Report summary">{metrics.map(({ label, value, note, icon: Icon, tone }) => <article key={label} className={`report-metric tone-${tone}`}><span className="report-metric-icon"><Icon /></span><div><span>{label}</span><strong className="mono">{value}</strong><small>{note}</small></div></article>)}</section>
    <section className="report-main-grid">
      <article className="report-chart-panel panel"><div className="section-heading"><div><span className="eyebrow">Activity mix</span><h2>Events by operational category</h2><p>Counts reflect the selected period and loaded event ledger.</p></div><StatusBadge tone={simulatedCount ? "simulated" : "neutral"} label={`${simulatedCount} simulated`} /></div><Separator /><ChartContainer config={chartConfig} className="report-chart"><BarChart accessibilityLayer data={chartData} margin={{ left: 6, right: 10, top: 20 }}><CartesianGrid vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={10} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} /><ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} /><Bar dataKey="count" fill="var(--color-count)" radius={[7, 7, 0, 0]} /></BarChart></ChartContainer><table className="sr-only"><caption>Event counts by category</caption><tbody>{chartData.map((item) => <tr key={item.label}><th>{item.label}</th><td>{item.count}</td></tr>)}</tbody></table></article>
      <aside className="report-context panel"><span className="eyebrow">Reading the report</span><h2>Data context</h2><p>PPE percentages use determinate item observations only. Unknown checks are retained but excluded. Process rates remain blank until completed-run data exists.</p><dl><div><dt>Loaded records</dt><dd className="mono">{filtered.length}</dd></div><div><dt>Real sources</dt><dd className="mono">{filtered.length - simulatedCount}</dd></div><div><dt>Simulated sources</dt><dd className="mono">{simulatedCount}</dd></div><div><dt>Unreviewed</dt><dd className="mono">{filtered.length - reviewed}</dd></div></dl>{!connected && <div className="inline-note">Fallback records are displayed. Start the edge agent before presenting report totals.</div>}</aside>
    </section>
    <section className="recent-records panel"><div className="section-heading"><div><span className="eyebrow">Recent records</span><h2>Operational ledger</h2></div><span className="mono record-count">{recent.length} shown</span></div><Table><TableHeader><TableRow><TableHead>Record</TableHead><TableHead>Employee / zone</TableHead><TableHead>Source</TableHead><TableHead>Status</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{recent.length ? recent.map((event) => <TableRow key={event.id}><TableCell><strong>{event.title}</strong><small>{event.type.replaceAll("_", " ")}</small></TableCell><TableCell>{event.employeeName ?? "System"}<small>{event.zone ?? "No zone"}</small></TableCell><TableCell><StatusBadge tone={event.sourceMode === "simulated" ? "simulated" : "neutral"} label={event.sourceMode} /></TableCell><TableCell><StatusBadge tone={event.status === "new" ? "warning" : "neutral"} label={event.status} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={5}><div className="empty-state"><Clock3 /><strong>No records in this period</strong><span>Select a wider period or create a controlled demonstration event.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
