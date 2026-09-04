"use client";
/* The local edge service publishes an MJPEG stream, which must use a native img element. */
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, BadgeCheck, Box, Camera, Check, CheckCircle2, CircleGauge, CircleX, Clock3, FileCheck2, MapPin, PackageCheck, Play, Radio, RotateCcw, ScanLine, ShieldAlert, ShieldCheck, Square, Thermometer, TimerOff, UserRound, WifiOff, X } from "lucide-react";
import { resetDetection, runDemoAction, useEdgeState } from "@/hooks/use-edge";
import { formatClock, formatDuration, formatRelative } from "@/lib/format";
import type { DetectionState, DeviceHealth, PpeAssessmentState, PpeItemAssessment, PpeStatus, Severity } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { LiveKitCamera } from "@/components/livekit-camera";
import { CameraSourceControl } from "@/components/camera-source-control";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

function PpeGrid({ ppe }: { ppe: PpeStatus }) {
  const detailed = ppe.items;
  const fields: Array<[string, PpeItemAssessment | boolean | null]> = detailed
    ? [["Mask", detailed.mask], ["Left glove", detailed.left_glove], ["Right glove", detailed.right_glove], ["Hairnet", detailed.hairnet], ["Apron", detailed.apron]]
    : [["Mask", ppe.mask], ["Gloves", ppe.gloves], ["Hairnet", ppe.hairnet], ["Apron", ppe.apron]];
  return <div className="ppe-grid" aria-label="Personal protective equipment state">{fields.map(([label, value]) => {
    const state: PpeAssessmentState = typeof value === "object" && value !== null ? value.state : value === true ? "detected" : value === false ? "missing" : "checking";
    const required = !(typeof value === "object" && value !== null) || value.required !== false;
    const stateLabel = state === "not_visible" ? "Not visible" : state === "unavailable" ? "Unavailable" : state === "detected" ? "Verified" : state === "missing" && !required ? "Missing · monitor only" : state[0].toUpperCase() + state.slice(1);
    return <div className={`ppe-item is-${state.replace("not_visible", "not-visible")} ${required ? "" : "is-monitor-only"}`} key={label}>{state === "detected" ? <CheckCircle2 /> : state === "missing" ? <AlertTriangle /> : <CircleGauge />}<span>{label}</span><strong>{stateLabel}</strong></div>;
  })}</div>;
}

function EventIcon({ severity }: { severity: Severity }) {
  if (severity === "critical") return <ShieldAlert />;
  if (severity === "warning") return <AlertTriangle />;
  return <Radio />;
}

function confidence(value: number | null | undefined) {
  return value == null ? "Checking" : `${Math.round(value * 100)}%`;
}

const PPE_ITEM_LABELS: Record<string, string> = { mask: "Mask", left_glove: "Left glove", right_glove: "Right glove", hairnet: "Hairnet", apron: "Apron" };
const PPE_ITEM_ORDER = ["mask", "left_glove", "right_glove", "hairnet", "apron"];

function assessmentText(item: string, assessment: PpeItemAssessment) {
  const label = PPE_ITEM_LABELS[item] ?? item;
  if (assessment.state === "missing") return `${label} not detected`;
  if (assessment.state === "not_visible") return item.endsWith("glove") ? `${label.replace("glove", "hand")} not visible` : `${label} not visible`;
  if (assessment.state === "detected") return `${label} verified`;
  if (assessment.state === "unavailable") return `${label} assessment unavailable`;
  return `${label} checking`;
}

function AutomaticMonitoringBar({ health, detection, connected, previewFailed }: { health: DeviceHealth; detection: DetectionState; connected: boolean; previewFailed: boolean }) {
  let tone: "safe" | "warning" | "critical" | "info" = "safe";
  let title = "Live demo systems ready";
  let detail = `Camera fresh at ${health.processedFps.toFixed(1)} FPS · PPE verifier self-test passed · ${health.temperatureSource?.sourceMode === "real" ? "live" : "simulated"} temperature source.`;
  let badge = "Ready";

  if (!connected || previewFailed || health.automaticMonitoring === "unavailable") {
    tone = "critical";
    title = "Automatic monitoring unavailable";
    detail = previewFailed ? "Reconnect the camera preview; detection will resume automatically." : health.monitoringMessage;
    badge = "Unavailable";
  } else if (health.automaticMonitoring === "warming_up") {
    tone = "info";
    title = "Automatic monitoring starting";
    detail = health.monitoringMessage;
    badge = "Starting";
  } else if (health.automaticMonitoring === "attention") {
    tone = "warning";
    title = "Automatic monitoring needs attention";
    detail = health.monitoringMessage;
    badge = "Check camera";
  } else if (health.sensor !== "online") {
    tone = "warning";
    title = "Temperature source needs attention";
    detail = health.temperatureSource?.error ?? "Reconnect the configured temperature source before demonstrating cold-chain alerts.";
    badge = "Sensor offline";
  } else if (detection.status === "attention") {
    tone = "critical";
    title = "PPE violation detected automatically";
    detail = detection.issues[0]?.title ?? "A required PPE item remained missing beyond the persistence period.";
    badge = "Action required";
  } else if (detection.status === "compliant") {
    title = "Controlled PPE signals verified";
    detail = "The visible mask and required hand signals passed the controlled-scene stability rules.";
    badge = "Verified";
  } else if (detection.status === "observing") {
    if (detection.proof?.assessmentAvailable === false) {
      tone = "warning";
      title = "Person tracking active; PPE unavailable";
      detail = "The current detector has no pose landmarks, so it will not create unsupported PPE findings.";
      badge = "Tracking only";
    } else if (detection.readiness?.guidance.length) {
      tone = "warning";
      title = "Automatic PPE check needs a clearer view";
      detail = detection.readiness.guidance[0];
      badge = "Adjust view";
    } else {
      tone = "info";
      title = "Automatic PPE assessment in progress";
      detail = "Visible body regions are being evaluated across the stability window.";
      badge = "Assessing";
    }
  }

  return <section className={`automatic-monitoring is-${tone}`} role={tone === "critical" ? "alert" : "status"} aria-live="polite">
    <span className="automatic-monitoring-icon">{tone === "critical" ? <CircleX /> : tone === "warning" ? <AlertTriangle /> : tone === "info" ? <Activity /> : <ShieldCheck />}</span>
    <span><strong>{title}</strong><small>{detail}</small></span>
    <StatusBadge tone={tone} label={badge} />
  </section>;
}

function DetectionRail({ detection, cleared, busy, message, onClear, onReset }: { detection: DetectionState; cleared: boolean; busy: boolean; message: string | null; onClear: () => void; onReset: () => void }) {
  if (detection.status === "idle") return message ? <div className="detection-reset-message" role="status"><CheckCircle2 />{message}</div> : null;
  const attention = detection.status === "attention";
  const observing = detection.status === "observing";
  const proof = detection.proof;
  const itemAssessments = PPE_ITEM_ORDER.flatMap((item) => detection.ppeItems[item] ? [[item, detection.ppeItems[item]] as const] : []);
  const heading = attention ? "PPE action required" : observing ? proof?.assessmentAvailable === false ? "PPE assessment unavailable" : "PPE assessment in progress" : "Controlled PPE signals verified";
  const description = attention ? "A visible PPE region remained unverified beyond the configured persistence period." : observing ? "Only visible body regions are assessed. Follow the camera guidance to complete the check." : "Mask and both visible hand signals passed the controlled-scene stability rules.";
  if (cleared) return <section className="detection-rail is-cleared" aria-label="Live detection status"><div><CheckCircle2 /><span><strong>Warnings cleared for Track {detection.trackId}</strong><small>Live tracking continues. A changed identity or PPE state will show a new warning.</small></span></div><Button variant="outline" size="sm" disabled={busy} onClick={onReset}><RotateCcw />{busy ? "Resetting…" : "Reset detection"}</Button></section>;
  return <section className={`detection-rail ${attention ? "is-attention" : observing ? "is-observing" : "is-compliant"}`} aria-label="Live detection status" role={attention ? "alert" : "status"}>
    <div className="detection-rail-heading"><span className="detection-state-icon">{attention ? <CircleX /> : observing ? <CircleGauge /> : <CheckCircle2 />}</span><div><span className="eyebrow">Live person tracking · Track {detection.trackId}</span><strong>{heading}</strong><small>{description}</small></div><StatusBadge tone={attention ? "critical" : observing ? "warning" : "safe"} label={attention ? "Live warning" : observing ? "Assessing" : "Compliant"} /></div>
    <div className="identity-association"><UserRound /><span><strong>{detection.identityStatus.label}</strong><small>{detection.identityStatus.detail}</small></span><StatusBadge tone="info" label="Optional identity" /></div>
    {attention && <ol className="detection-issues">{detection.issues.map((issue) => <li key={issue.code}><CircleX /><span><strong>{issue.title}</strong><small>{issue.detail}</small></span></li>)}</ol>}
    {itemAssessments.length > 0 && <ol className="detection-assessments" aria-label="Current PPE assessments">{itemAssessments.map(([item, assessment]) => <li className={`is-${assessment.state.replace("not_visible", "not-visible")} ${assessment.required === false ? "is-monitor-only" : ""}`} key={item}>{assessment.state === "detected" ? <CheckCircle2 /> : assessment.state === "missing" ? <CircleX /> : <CircleGauge />}<span><strong>{assessmentText(item, assessment)}{assessment.required === false ? " · monitor only" : ""}</strong><small>{assessment.required === false ? "Rule disabled for tomorrow’s mask-and-gloves acceptance" : assessment.state === "not_visible" ? "No violation recorded" : assessment.state === "checking" ? "Building a stable 15-frame decision" : assessment.state === "unavailable" ? "Pose landmarks are unavailable" : `Decision ${confidence(assessment.confidence)} · visibility ${confidence(assessment.visibilityConfidence)}`}</small></span></li>)}</ol>}
    {detection.readiness?.guidance.length ? <div className="camera-guidance" role="status"><AlertTriangle /><span><strong>Camera guidance</strong>{detection.readiness.guidance.map((guidance) => <small key={guidance}>{guidance}</small>)}</span></div> : null}
    {proof && <dl className="detection-proof" aria-label="Live detection proof"><div><dt><MapPin />Zone</dt><dd>{proof.zone}</dd></div><div><dt><ScanLine />Person confidence</dt><dd className="mono">{confidence(proof.personConfidence)}</dd></div><div><dt><ShieldCheck />Signal confidence</dt><dd className="mono">{confidence(proof.ppeConfidence)}</dd></div><div><dt><CircleGauge />Lighting</dt><dd className="mono">{proof.brightness == null ? "—" : `${Math.round(proof.brightness)}/255`}</dd></div><div><dt><Activity />Movement trail</dt><dd className="mono">{proof.movementSamples} samples</dd></div><div><dt><FileCheck2 />Event evidence</dt><dd>Snapshot + clip after persistence</dd></div></dl>}
    <div className="detection-rail-actions"><p>Clearing hides this live warning only. Stored events and evidence remain unchanged.</p>{message && <span role="status">{message}</span>}<div>{attention && <Button variant="outline" size="sm" onClick={onClear}><X />Clear warnings</Button>}<Button variant="outline" size="sm" disabled={busy} onClick={onReset}><RotateCcw />{busy ? "Resetting…" : "Reset detection"}</Button></div></div>
  </section>;
}

export function LiveWorkspace() {
  const { state, connected, error, refresh } = useEdgeState();
  const [previewFailed, setPreviewFailed] = useState(false);
  const [streamRevision, setStreamRevision] = useState(0);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [dismissedDetectionKey, setDismissedDetectionKey] = useState<string | null>(null);
  const [detectionMessage, setDetectionMessage] = useState<string | null>(null);
  const [resettingDetection, setResettingDetection] = useState(false);
  const [clock, setClock] = useState<Date | null>(null);

  useEffect(() => {
    const initial = window.setTimeout(() => setClock(new Date()), 0);
    const timer = window.setInterval(() => setClock(new Date()), 1_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, []);

  const referenceTime = clock?.getTime() ?? new Date("2026-08-22T00:00:00.000Z").getTime();
  const processElapsed = useMemo(() => {
    if (state.process.status !== "running" || !state.process.startedAt) return state.process.elapsedSeconds;
    return Math.max(state.process.elapsedSeconds, Math.floor((referenceTime - new Date(state.process.startedAt).getTime()) / 1_000));
  }, [referenceTime, state.process]);

  async function trigger(action: string, message: string, payload?: Record<string, unknown>) {
    setBusyAction(action); setActionMessage(null);
    try { await runDemoAction(action, payload); setActionMessage(message); await refresh(); }
    catch { setActionMessage("Action could not reach the local edge agent."); }
    finally { setBusyAction(null); }
  }

  async function guidedScenario() {
    setBusyAction("guided-scenario"); setActionMessage(null);
    try {
      for (const action of ["ppe-violation", "temperature-high", "inventory-variance"]) await runDemoAction(action);
      setActionMessage("Guided enterprise exception scenario created."); await refresh();
    } catch { setActionMessage("The guided scenario could not reach the local edge agent."); }
    finally { setBusyAction(null); }
  }

  const employee = state.activeEmployee;
  const detection = state.detection;
  const detectionKey = `${detection.resetGeneration}:${detection.trackId ?? "idle"}:${detection.status}:${detection.issues.map((issue) => issue.code).join(",")}`;
  const cloudVideoConfigured = Boolean(process.env.NEXT_PUBLIC_LIVEKIT_URL);
  const activeViolation = [...state.recentEvents].filter((event) => event.status === "new" && (event.type === "ppe_violation" || event.type === "temperature_alert")).sort((first, second) => {
    const priority = (event: typeof first) => {
      if (event.type === "temperature_alert") return 10;
      const item = String(event.metadata?.item ?? "");
      const index = PPE_ITEM_ORDER.indexOf(item);
      return index === -1 ? 9 : index;
    };
    return priority(first) - priority(second) || new Date(second.occurredAt).getTime() - new Date(first.occurredAt).getTime();
  })[0];
  const inventoryTotal = state.inventory.reduce((sum, item) => sum + item.quantity, 0);
  const progressValue = Math.min(100, (processElapsed / state.process.targetMaxSeconds) * 100);

  async function cameraSwitched() {
    setPreviewFailed(false);
    setStreamRevision((current) => current + 1);
    await refresh();
  }

  function clearDetectionWarnings() {
    setDismissedDetectionKey(detectionKey);
    setDetectionMessage("Current warning cleared. Live tracking is still active.");
  }

  async function restartDetection() {
    setResettingDetection(true);
    setDetectionMessage(null);
    try {
      await resetDetection();
      setDismissedDetectionKey(null);
      setDetectionMessage("Detection reset. A new observation cycle has started; retained events were not deleted.");
      await refresh();
    } catch {
      setDetectionMessage("Detection could not be reset. Confirm the local edge agent is online and try again.");
    } finally {
      setResettingDetection(false);
    }
  }

  return <div className="page-shell live-page">
    <PageHeader eyebrow="Kitchen 01 · operational view" title="Live operations" description="Monitor staff compliance, preparation timing, stock movement, and temperature from one controlled camera." actions={<><span className="live-clock"><span className="live-pulse" />Live</span><time className="mono" dateTime={clock?.toISOString()}>{clock ? formatClock(clock.toISOString()) : "—"}</time><Sheet><SheetTrigger asChild><Button variant="outline"><Play />Tools</Button></SheetTrigger><SheetContent className="demo-sheet"><SheetHeader><SheetTitle>Operational tools</SheetTitle><SheetDescription>Use only when a physical prop is unavailable. Every created record is permanently marked Simulated.</SheetDescription></SheetHeader><StatusBadge tone="simulated" label="Always simulated" /><div className="demo-control-list"><div><span><Play />Process stage</span><Button disabled={busyAction !== null} onClick={() => void trigger(state.process.status === "running" ? "process-complete" : "process-start", state.process.status === "running" ? "Process completed." : "Process started.")}>{state.process.status === "running" ? <Square /> : <Play />}{state.process.status === "running" ? "Complete process" : "Start process"}</Button><Button variant="outline" disabled={busyAction !== null} onClick={() => void trigger("process-overtime", "Simulated process timing exception added.")}><TimerOff />Add overtime exception</Button></div><div><span><ShieldAlert />PPE exception</span><Button disabled={busyAction !== null} onClick={() => void trigger("ppe-violation", "Simulated glove violation added.")}><ShieldAlert />Add missing-gloves event</Button></div><div><span><Thermometer />Temperature</span><Button disabled={busyAction !== null} onClick={() => void trigger(state.temperature.status === "safe" ? "temperature-high" : "temperature-safe", "Simulated temperature changed.")}><Thermometer />{state.temperature.status === "safe" ? "Raise above limit" : "Return to safe"}</Button></div><div><span><Box />Inventory</span><Button disabled={busyAction !== null} onClick={() => void trigger("inventory", "Simulated stock-in movement added.", { sku: "SKU-001", direction: "in", quantity: 1 })}><Box />Add stock movement</Button><Button variant="outline" disabled={busyAction !== null} onClick={() => void trigger("inventory-variance", "Simulated inventory variance added.")}><AlertTriangle />Add count variance</Button></div><div><span><Play />Guided presentation</span><Button disabled={busyAction !== null} onClick={() => void guidedScenario()}><Play />Create enterprise exception set</Button><Button variant="outline" asChild><Link href="/platform">Open reset controls</Link></Button></div></div><p className="action-message" aria-live="polite">{busyAction ? "Sending action…" : actionMessage}</p></SheetContent></Sheet></>} />

    {!connected && <div className="connection-alert" role="alert"><WifiOff /><span><strong>Edge agent is unavailable.</strong>{error ?? "Start the local service to restore live detections."}</span><Button variant="outline" size="sm" onClick={() => void refresh()}>Retry</Button></div>}

    {activeViolation && <section className="active-violation" aria-label="Active violation"><span className="violation-icon"><ShieldAlert /></span><div><span className="eyebrow">Active violation</span><strong>{activeViolation.title}</strong><p>{activeViolation.detail}</p></div><div className="violation-meta"><StatusBadge tone={activeViolation.sourceMode === "simulated" ? "simulated" : "critical"} label={activeViolation.sourceMode} /><span>{formatRelative(activeViolation.occurredAt, referenceTime)}</span><Button variant="outline" size="sm" asChild><Link href="/incidents">Review incident</Link></Button></div></section>}

    <section className="operations-grid" aria-label="Live camera and operational status">
      <article className="camera-workspace panel">
        <div className="camera-command-bar"><div className="camera-command-source"><span className="camera-icon"><Camera /></span><div className="camera-command-identity"><strong>{state.health.cameraLabel}</strong><span>Camera 01 · {state.health.sourceType.toUpperCase()}</span></div><CameraSourceControl activeId={state.health.cameraId} currentLabel={state.health.cameraLabel} disabled={!connected || state.health.cameraSwitchState === "switching"} onSwitched={cameraSwitched} /></div><div className="camera-command-metrics"><span><small>Processing</small><strong className="mono">{state.health.processedFps.toFixed(1)} fps</strong></span><span><small>Resolution</small><strong className="mono">1280×720</strong></span><StatusBadge tone={state.health.cameraSwitchState === "switching" ? "warning" : state.health.camera === "online" ? "safe" : "critical"} label={state.health.cameraSwitchState === "switching" ? "switching" : state.health.camera} /></div></div>
        <AutomaticMonitoringBar health={state.health} detection={detection} connected={connected} previewFailed={previewFailed} />
        <div className="camera-frame">{cloudVideoConfigured ? <LiveKitCamera /> : connected && !previewFailed ? <img key={`${state.health.cameraId}-${streamRevision}`} src="/api/edge/api/preview.mjpeg" alt={`Live annotated view from ${state.health.cameraLabel}`} onError={() => setPreviewFailed(true)} /> : <div className="camera-empty"><Camera /><strong>{previewFailed ? "Camera preview interrupted" : "Waiting for Camera 01"}</strong><span>{error ?? "Start the edge service and allow macOS camera access."}</span>{previewFailed && <Button variant="secondary" onClick={() => setPreviewFailed(false)}>Reconnect preview</Button>}</div>}<div className="camera-overlay top-left"><span className="record-dot" /> LIVE · NO CAMERA AUDIO</div><div className="camera-overlay bottom-left">Movement trail · zones · person · PPE</div></div>
        <DetectionRail detection={detection} cleared={detection.status === "attention" && dismissedDetectionKey === detectionKey} busy={resettingDetection} message={detectionMessage} onClear={clearDetectionWarnings} onReset={() => void restartDetection()} />
        <footer className="camera-foot"><span><Radio />Last frame {formatRelative(state.health.lastFrameAt, referenceTime)}</span><span className={`verifier-health is-${state.health.ppeVerifier?.status ?? "checking"}`}><ShieldCheck />PPE verifier <strong>{state.health.ppeVerifier?.status === "passed" ? "self-test passed" : state.health.ppeVerifier?.status === "failed" ? "disabled" : "starting"}</strong></span><span>Model <strong>{state.health.modelLabel.split("·")[0]}</strong></span></footer>
      </article>

      <aside className="operations-rail" aria-label="Current operational readings">
        <article className="metric-panel process-panel"><div className="section-label"><Clock3 /><span>Process timing</span><StatusBadge tone={state.process.status === "running" ? "warning" : "neutral"} label={state.process.status} /></div><div className="timer-value mono">{formatDuration(processElapsed)}</div><div className="process-title-row"><strong>{state.process.label}</strong><span>Target {formatDuration(state.process.targetMinSeconds)}–{formatDuration(state.process.targetMaxSeconds)}</span></div><Progress value={progressValue} aria-label="Process target progress" /><div className="process-steps"><span className={state.process.status === "idle" ? "" : "is-complete"}><i>{state.process.status === "idle" ? "1" : <Check />}</i>Start</span><span className={state.process.status === "running" ? "is-current" : state.process.status === "complete" ? "is-complete" : ""}><i>{state.process.status === "complete" ? <Check /> : "2"}</i>In progress</span><span className={state.process.status === "complete" ? "is-complete" : ""}><i>{state.process.status === "complete" ? <Check /> : "3"}</i>Complete</span></div></article>

        <div className="metric-split"><article className={`metric-panel temperature-panel tone-${state.temperature.status}`}><div className="section-label"><Thermometer /><span>Temperature</span></div><div className="primary-reading">{state.temperature.valueC.toFixed(1)}<small>°C</small></div><span className="subtle">Safe range {state.temperature.minC}–{state.temperature.maxC}°C</span><StatusBadge tone={state.temperature.sourceMode === "simulated" ? "simulated" : "safe"} label={state.temperature.sourceMode === "simulated" ? "Simulated sensor" : "Live sensor"} /></article><article className="metric-panel inventory-panel"><div className="section-label"><Box /><span>Inventory</span></div><div className="primary-reading">{inventoryTotal}<small>items</small></div><span className="subtle">Across {state.inventory.length} tagged SKUs</span><span className="tiny-state"><PackageCheck />Stable tagged-crossing rule active</span></article></div>

        <article className="metric-panel employee-panel"><div className="section-label"><UserRound /><span>Staff & PPE</span>{employee && <StatusBadge tone={employee.employeeId ? "safe" : "info"} label={employee.employeeId ? "Badge identified" : "Identity optional"} />}</div>{employee ? <><div className="employee-identity"><Avatar className="employee-avatar">{employee.photoUrl ? <AvatarImage src={employee.photoUrl} alt="" /> : null}<AvatarFallback>{employee.employeeId ? employee.displayName.slice(0, 2).toUpperCase() : "US"}</AvatarFallback></Avatar><div><strong>{employee.displayName}</strong><span>{employee.employeeId ?? `Track ${employee.trackId ?? "—"}`} · {employee.zone}</span></div>{employee.employeeId ? <BadgeCheck className="safe-icon" aria-label="Badge resolved" /> : <UserRound className="info-icon" aria-label="Identity not required" />}</div><p className="identity-method">{employee.employeeId ? <><BadgeCheck />Identified by badge {employee.badgeMarkerId ?? "—"}{employee.photoUrl ? " · profile photo for operator reference" : " · no biometric matching"}</> : <><ShieldCheck />PPE monitoring is active without employee identification. Badge or access-control matching can be added later.</>}</p><PpeGrid ppe={employee.ppe} /><div className="metric-foot"><span>{employee.activity}</span><span>Signal confidence {employee.ppe.confidence ? `${Math.round(employee.ppe.confidence * 100)}%` : "checking"}</span></div></> : <div className="empty-compact"><UserRound /><strong>No staff member in view</strong><span>Automatic PPE monitoring is active and waiting for a person. An employee badge is optional.</span></div>}</article>
      </aside>
    </section>

    <section className="timeline-panel panel"><div className="section-heading"><div><span className="eyebrow">Live event stream</span><h2>Latest operational activity</h2></div><Button variant="ghost" size="sm" asChild><Link href="/incidents">Review incidents</Link></Button></div><Separator /><ol className="event-list">{state.recentEvents.length ? state.recentEvents.slice(0, 5).map((event) => <li key={event.id} className={`event-row severity-${event.severity}`}><span className="event-icon"><EventIcon severity={event.severity} /></span><div><strong>{event.title}</strong><span>{event.detail}</span><small>{event.employeeName ?? "System"} · {event.zone ?? "No zone"}</small></div><time className="mono" dateTime={event.occurredAt}>{formatRelative(event.occurredAt, referenceTime)}</time><div className="event-tags"><StatusBadge tone={event.sourceMode === "simulated" ? "simulated" : "neutral"} label={event.sourceMode} /><StatusBadge tone={event.status === "new" ? "warning" : "neutral"} label={event.status} /></div></li>) : <li className="timeline-empty"><Radio /><strong>No events recorded</strong><span>New camera and sensor activity will appear here.</span></li>}</ol></section>
  </div>;
}
