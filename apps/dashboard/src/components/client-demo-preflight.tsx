"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleDashed, RefreshCw, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { getClientDemoPreflight } from "@/hooks/use-edge";
import type { ClientDemoPreflight, PreflightCheck } from "@/lib/types";

const SOUND_KEY = "safeguard.alert-sound.enabled.v1";

function CheckIcon({ status }: { status: PreflightCheck["status"] }) {
  return status === "passed" ? <CheckCircle2 /> : status === "failed" ? <XCircle /> : <CircleDashed />;
}

export function ClientDemoPreflightView() {
  const [data, setData] = useState<ClientDemoPreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true);
    try { setData(await getClientDemoPreflight()); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Preflight service unavailable"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initial);
  }, [refresh]);

  const checks = useMemo(() => {
    if (!data) return [];
    const soundEnabled = typeof window !== "undefined" && window.localStorage.getItem(SOUND_KEY) === "true";
    return data.checks.map((item) => item.id === "alert_sound" ? {
      ...item,
      status: soundEnabled ? "passed" as const : "pending" as const,
      detail: soundEnabled ? "Alert sound is enabled in this browser." : item.detail,
    } : item);
  }, [data]);
  const passed = checks.filter((item) => item.status === "passed").length;
  const progress = checks.length ? Math.round(passed / checks.length * 100) : 0;

  return <div className="page-shell enterprise-page preflight-page">
    <PageHeader eyebrow="Client demonstration control" title="Client demo preflight" description="A fail-closed readiness check for the exact camera, AI, evidence, network, and recovery setup used in the meeting." actions={<Button variant="outline" onClick={() => void refresh()} disabled={loading}><RefreshCw className={loading ? "spin" : undefined} />Run checks</Button>} />
    {error && <div className="connection-alert" role="alert"><TriangleAlert /><span><strong>Preflight unavailable</strong>{error}</span></div>}
    {loading && !data ? <div className="preflight-loading"><Skeleton /><Skeleton /><Skeleton /></div> : data && <>
      <section className={`panel preflight-summary is-${data.status}`}><span className="preflight-summary-icon">{data.status === "ready" ? <ShieldCheck /> : <TriangleAlert />}</span><div><span className="eyebrow">Presentation release status</span><h2>{data.status === "ready" ? "Ready for controlled demonstration" : "Client mode remains blocked"}</h2><p>{data.clientBoundary}</p></div><div className="preflight-score"><strong className="mono">{passed}/{checks.length}</strong><span>checks passed</span><Progress value={progress} aria-label={`${progress}% of preflight checks passed`} /></div></section>
      <section className="preflight-layout">
        <article className="panel preflight-checklist"><div className="ai-panel-heading"><div><span className="eyebrow">Runtime and rehearsal evidence</span><h2>Readiness checks</h2></div><StatusBadge tone={data.status === "ready" ? "safe" : "warning"} label={data.status} /></div><Separator /><div className="preflight-check-list">{checks.map((check) => <article className={`preflight-check is-${check.status}`} key={check.id}><span className="preflight-check-icon"><CheckIcon status={check.status} /></span><div><strong>{check.label}</strong><p>{check.detail}</p>{check.status !== "passed" && <small>{check.recovery}</small>}</div><StatusBadge tone={check.status === "passed" ? "safe" : check.status === "failed" ? "critical" : "warning"} label={check.status} /></article>)}</div></article>
        <aside className="panel preflight-ai"><div className="ai-panel-heading"><div><span className="eyebrow">Release-controlled AI</span><h2>Action readiness</h2></div><span className="mono">{data.summary.readyAiActions}/{data.summary.totalAiActions}</span></div><Separator /><div>{data.aiFeatures.map((feature) => <article key={feature.action}><span className={feature.ready ? "is-ready" : "is-pending"}>{feature.ready ? <CheckCircle2 /> : <CircleDashed />}</span><div><strong>{feature.label}</strong><small>{feature.ready ? "All gates current" : feature.recovery}</small></div></article>)}</div><p className="preflight-footnote">Unverified actions remain disabled. Provider stubs are never shown as live AI.</p></aside>
      </section>
    </>}
  </div>;
}
