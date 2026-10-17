"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BrainCircuit, CheckCircle2, Database, FileSearch, LoaderCircle, LockKeyhole, RefreshCw, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { getAIFeatures, getAIJob, runAIOperation, setAIFeatureEnabled } from "@/hooks/use-edge";
import { useEnterprise } from "@/hooks/use-enterprise";
import type { AIFeatureReadiness, AIOperationsAction, AIJob } from "@/lib/types";
import { cn } from "@/lib/utils";

const TERMINAL = new Set(["completed", "needs_review", "unavailable", "failed"]);

function Result({ job }: { job: AIJob | null }) {
  if (!job) return <div className="ai-result-empty"><BrainCircuit /><strong>Select a verified action</strong><span>The supervisor will explain exact local records without changing them.</span></div>;
  if (!TERMINAL.has(job.status)) return <div className="ai-result-empty" aria-live="polite"><LoaderCircle className="spin" /><strong>Analyzing selected records</strong><span>Local monitoring continues while the bounded AI job runs.</span></div>;
  if (job.failure) return <div className="ai-result-empty tone-warning" role="status"><ShieldAlert /><strong>AI review unavailable</strong><span>{job.failure.detail}</span></div>;
  const result = job.result;
  return <div className="ai-result-content" aria-live="polite">
    <div className="ai-result-status"><StatusBadge tone={job.status === "needs_review" ? "warning" : "info"} label="AI-assisted" /><span className="mono">{job.latencyMs ?? 0} ms</span></div>
    <h2>{result?.summary ?? "Insufficient operational evidence"}</h2>
    <p>{result?.rationale ?? "No qualifying local source record is available for this action."}</p>
    <div className="ai-authority-note"><LockKeyhole /><span><strong>Read-only interpretation</strong>Local measurements, event status, and operator review remain authoritative.</span></div>
    <Separator />
    <div className="ai-source-section"><span className="eyebrow">Source records</span>{job.sourceRecordIds.length ? <ul>{job.sourceRecordIds.map((id) => <li className="mono" key={id}>{id}</li>)}</ul> : <p>No source records were available.</p>}</div>
    {result?.exactFacts && <details className="ai-facts"><summary>View exact local facts</summary><pre>{JSON.stringify(result.exactFacts, null, 2)}</pre></details>}
  </div>;
}

export function AIOperationsSupervisorView() {
  const { persona } = useEnterprise();
  const [features, setFeatures] = useState<AIFeatureReadiness[]>([]);
  const [selected, setSelected] = useState<AIOperationsAction | null>(null);
  const [job, setJob] = useState<AIJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const catalog = await getAIFeatures();
      setFeatures(catalog.items); setError(null);
      if (catalog.items.length) setSelected((current) => current ?? catalog.items[0].action);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI readiness is unavailable");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initial);
  }, [refresh]);
  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const timer = window.setInterval(async () => {
      try { setJob(await getAIJob(job.id)); } catch { /* retain the last known safe state */ }
    }, 500);
    return () => window.clearInterval(timer);
  }, [job]);

  const active = useMemo(() => features.find((item) => item.action === selected) ?? null, [features, selected]);
  const run = async () => {
    if (!active?.ready) return;
    setError(null); setJob(null);
    try { setJob(await runAIOperation(active.action)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The AI action could not start"); }
  };
  const toggle = async (feature: AIFeatureReadiness, enabled: boolean) => {
    try { await setAIFeatureEnabled(feature.action, enabled); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The kill switch could not be changed"); }
  };

  return <div className="page-shell enterprise-page ai-supervisor-page">
    <PageHeader eyebrow="Read-only operational intelligence" title="AI operations supervisor" description="Grounded explanations from exact event, process, inventory, temperature, and SOP records. AI never changes measurements or resolves incidents." actions={<><StatusBadge tone="info" label="AI-assisted" /><Button variant="outline" onClick={() => void refresh()}><RefreshCw />Refresh readiness</Button></>} />
    <div className="ai-boundary-strip"><Database /><div><strong>Local records remain authoritative</strong><span>No facial identification, employee evaluation, equipment control, Oracle write, or automatic incident resolution.</span></div></div>
    {error && <div className="connection-alert is-warning" role="alert"><ShieldAlert /><span><strong>Action unavailable</strong>{error}</span></div>}
    <section className="ai-supervisor-layout">
      <aside className="panel ai-action-panel" aria-label="AI supervisor actions">
        <div className="ai-panel-heading"><div><span className="eyebrow">Verified actions</span><h2>Choose an interpretation</h2></div><span className="mono">{features.filter((item) => item.ready).length}/{features.length}</span></div>
        <Separator />
        {loading ? <div className="ai-action-skeleton"><Skeleton /><Skeleton /><Skeleton /></div> : <div className="ai-action-list">{features.map((feature) => <button type="button" className={cn("ai-action-row", selected === feature.action && "is-selected")} onClick={() => setSelected(feature.action)} key={feature.action}><span className={cn("ai-action-state", feature.ready ? "is-ready" : "is-pending")}>{feature.ready ? <CheckCircle2 /> : <LockKeyhole />}</span><span><strong>{feature.label}</strong><small>{feature.description}</small></span><StatusBadge tone={feature.ready ? "safe" : feature.enabled ? "warning" : "critical"} label={feature.ready ? "Ready" : feature.enabled ? "Pending" : "Disabled"} /></button>)}</div>}
      </aside>
      <article className="panel ai-workspace-panel">
        <div className="ai-workspace-header"><div><span className="eyebrow">Selected action</span><h2>{active?.label ?? "Operations supervisor"}</h2><p>{active?.ready ? "The action passed every current release gate." : active?.recovery ?? "Loading readiness."}</p></div><Button disabled={!active?.ready || Boolean(job && !TERMINAL.has(job.status))} onClick={() => void run()}><FileSearch />{job && !TERMINAL.has(job.status) ? "Analyzing…" : "Run analysis"}</Button></div>
        {active && <div className="ai-gate-row" aria-label="Action release gates">{Object.entries(active.gates).map(([name, passed]) => <span className={passed ? "is-passed" : "is-pending"} key={name}>{passed ? <CheckCircle2 /> : <LockKeyhole />}{name.replace(/([A-Z])/g, " $1")}</span>)}</div>}
        <Separator />
        <Result job={job} />
      </article>
    </section>
    {persona === "it" && features.length > 0 && <section className="panel ai-kill-switches"><div><span className="eyebrow">Independent controls</span><h2>AI action kill switches</h2><p>Disabling one action does not interrupt local monitoring or any other AI action.</p></div><div>{features.map((feature) => <label key={feature.action}><span><strong>{feature.label}</strong><small>{feature.enabled ? "Enabled subject to readiness" : "Disabled"}</small></span><Switch checked={feature.enabled} onCheckedChange={(value) => void toggle(feature, value)} aria-label={`${feature.enabled ? "Disable" : "Enable"} ${feature.label}`} /></label>)}</div></section>}
  </div>;
}
