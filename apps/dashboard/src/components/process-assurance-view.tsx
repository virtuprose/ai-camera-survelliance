"use client";

import { AlertTriangle, Check, Clock3, Play, ScrollText } from "lucide-react";
import { DataBoundary, MetricStrip, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnterprise } from "@/hooks/use-enterprise";
import { useEdgeState } from "@/hooks/use-edge";
import { formatDateTime, formatDuration } from "@/lib/format";

export function ProcessAssuranceView() {
  const { sops, processRuns, overview, workspaceId, context } = useEnterprise();
  const { state } = useEdgeState();
  const workspace = context.workspaces.find((item) => item.id === workspaceId) ?? context.workspaces[0];
  const sop = sops[0];
  const running = state.process.status === "running";
  const progress = Math.min(100, state.process.targetMaxSeconds ? state.process.elapsedSeconds / state.process.targetMaxSeconds * 100 : 0);
  return <div className="page-shell enterprise-page">
    <PageHeader eyebrow="Operations assurance · SOP timing" title="Process assurance" description="Track repeatable food-preparation stages against approved time windows and retain every exception for review." actions={<><SourceBadge mode={workspace.mode} /><StatusBadge tone={running ? "warning" : "neutral"} label={running ? "Process active" : "No active run"} /></>} />
    {workspace.mode !== "live" && <DataBoundary mode={workspace.mode} />}
    <MetricStrip items={[
      { label: "On-time completion", value: overview.metrics.processOnTime === null ? "—" : `${overview.metrics.processOnTime}%`, note: overview.metrics.completedProcesses ? "Completed controlled runs" : "Insufficient completed data", tone: overview.metrics.processOnTime !== null && overview.metrics.processOnTime < 90 ? "warning" : "safe", icon: <Clock3 /> },
      { label: "Completed runs", value: String(overview.metrics.completedProcesses), note: "Current retained ledger", icon: <Check /> },
      { label: "Active runs", value: running ? "1" : "0", note: state.process.label, tone: running ? "warning" : "neutral", icon: <Play /> },
      { label: "Timing exceptions", value: String(processRuns.filter((item) => item.status === "exception").length), note: "Requires QA review", tone: processRuns.some((item) => item.status === "exception") ? "critical" : "safe", icon: <AlertTriangle /> },
    ]} />
    <section className="process-assurance-grid">
      <article className="panel active-run-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Current process</span><h2>{state.process.label}</h2><p>Camera zones provide stage transition evidence; the timer is recorded by the edge service.</p></div><StatusBadge tone={running ? "warning" : "neutral"} label={state.process.status} /></div><Separator /><div className="active-run-clock"><span>Elapsed time</span><strong className="mono">{formatDuration(state.process.elapsedSeconds)}</strong><small>Target {formatDuration(state.process.targetMinSeconds)}–{formatDuration(state.process.targetMaxSeconds)}</small></div><Progress value={progress} aria-label="Current process timing progress" /><div className="sop-stage-rail">{(sop?.stages ?? []).map((stage, index) => <article className={index === 0 || state.process.status !== "idle" ? "is-reached" : ""} key={stage.id}><span>{index === 0 ? <Check /> : index + 1}</span><div><strong>{stage.name}</strong><small>{stage.trigger}</small></div><b className="mono">{stage.targetMaxSeconds ? `≤ ${formatDuration(stage.targetMaxSeconds)}` : "Event"}</b></article>)}</div></article>
      <aside className="panel sop-card"><div className="enterprise-panel-heading"><div><span className="eyebrow">Active procedure</span><h2>{sop?.name ?? "No SOP configured"}</h2><p>Version-controlled procedure definition for this workspace.</p></div><ScrollText /></div><Separator />{sop ? <dl><div><dt>Procedure code</dt><dd className="mono">{sop.code}</dd></div><div><dt>Version</dt><dd className="mono">{sop.version}</dd></div><div><dt>Stages</dt><dd>{sop.stages.length}</dd></div><div><dt>Data source</dt><dd><SourceBadge mode={sop.sourceMode} /></dd></div><div><dt>Review boundary</dt><dd>Controlled demo</dd></div></dl> : <DataBoundary mode="planned" />}</aside>
    </section>
    <section className="panel enterprise-table-panel department-ledger"><div className="enterprise-panel-heading"><div><span className="eyebrow">Retained history</span><h2>Process run ledger</h2><p>No rate is calculated when completed-run data is insufficient.</p></div></div><Table><TableHeader><TableRow><TableHead>Process</TableHead><TableHead>Status</TableHead><TableHead>Duration</TableHead><TableHead>Target</TableHead><TableHead>Source</TableHead><TableHead>Started</TableHead></TableRow></TableHeader><TableBody>{processRuns.length ? processRuns.map((run) => <TableRow key={run.id}><TableCell><strong>{run.label}</strong><small className="mono">{run.id.slice(0, 8)}</small></TableCell><TableCell><StatusBadge tone={run.status === "exception" ? "critical" : run.status === "running" ? "warning" : "safe"} label={run.status} /></TableCell><TableCell className="mono">{run.elapsedSeconds === null ? "Running" : formatDuration(run.elapsedSeconds)}</TableCell><TableCell className="mono">{formatDuration(run.targetMinSeconds)}–{formatDuration(run.targetMaxSeconds)}</TableCell><TableCell><SourceBadge mode={run.sourceMode} /></TableCell><TableCell><time className="mono" dateTime={run.startedAt}>{formatDateTime(run.startedAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={6}><div className="enterprise-empty"><Clock3 /><strong>No process runs recorded</strong><span>Use the physical tray tag or Tools to start the controlled Chicken Washing procedure.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
