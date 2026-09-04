"use client";

import { BadgeCheck, Clock3, MapPin, Radio, ScanLine, ShieldCheck, UserRound, UsersRound } from "lucide-react";
import { DataBoundary, MetricStrip, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEdgeState } from "@/hooks/use-edge";
import { formatDateTime, formatDuration } from "@/lib/format";

export function StaffVisibilityView() {
  const { state } = useEdgeState();
  const subject = state.activeEmployee;
  const events = state.recentEvents.filter((event) => ["employee_entry", "staff_movement", "identity_unresolved"].includes(event.type));
  const entries = events.filter((event) => event.type === "employee_entry");
  const movements = events.filter((event) => event.type === "staff_movement");
  const unresolved = events.filter((event) => event.type === "identity_unresolved");
  const cameraMode = state.health.sourceType === "file" ? "simulated" : "live";
  return <div className="page-shell enterprise-page">
    <PageHeader eyebrow="Operations · Workforce visibility" title="Staff visibility" description="See who is in the current camera workspace, their operational zone, contextual activity, and retained movement evidence without requiring biometric identity." actions={<><SourceBadge mode={cameraMode} /><StatusBadge tone={subject ? "safe" : "neutral"} label={subject ? "Track active" : "No active track"} /></>} />
    <DataBoundary mode={cameraMode}>This demonstration reports one camera and its retained ledger. Multi-camera handoff requires the client camera/VMS survey and an approved identity policy.</DataBoundary>
    <MetricStrip items={[
      { label: "Staff in current view", value: subject ? "1" : "0", note: "Single-camera demo scope", tone: subject ? "safe" : "neutral", icon: <UsersRound /> },
      { label: "Identity state", value: subject?.employeeId ? "Linked" : "Optional", note: subject?.employeeId ? "ArUco badge association" : "Tracking continues without identity", tone: subject?.employeeId ? "safe" : "neutral", icon: <BadgeCheck /> },
      { label: "Entries in ledger", value: String(entries.length), note: "Currently loaded events", icon: <Clock3 /> },
      { label: "Movement records", value: String(movements.length), note: `${unresolved.length} unresolved identity record${unresolved.length === 1 ? "" : "s"}`, icon: <MapPin /> },
    ]} />
    <section className="assurance-grid">
      <article className="panel assurance-subject-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Current camera observation</span><h2>Tracked staff context</h2><p>Zone and process state provide the current operational context; they do not infer private intent.</p></div>{subject && <StatusBadge tone={subject.employeeId ? "safe" : "info"} label={subject.employeeId ? "Badge identified" : "Unidentified staff member"} />}</div><Separator />{subject ? <div className="assurance-employee"><div className="assurance-identity"><Avatar><AvatarImage src={subject.photoUrl ?? undefined} alt="" /><AvatarFallback>{subject.employeeId ? subject.displayName.slice(0, 2).toUpperCase() : "US"}</AvatarFallback></Avatar><div><strong>{subject.displayName}</strong><span>{subject.employeeId ?? `Track ${subject.trackId ?? "—"}`}</span><small>{subject.employeeId ? <><BadgeCheck /> Badge {subject.badgeMarkerId ?? "—"} associated</> : <><ShieldCheck /> Identity optional; PPE remains active</>}</small></div></div><dl className="detail-list"><div><dt>Current zone</dt><dd>{subject.zone}</dd></div><div><dt>Current operational context</dt><dd>{subject.activity}</dd></div><div><dt>Observed since</dt><dd>{subject.enteredAt ? formatDateTime(subject.enteredAt) : "Current frame"}</dd></div><div><dt>Observation duration</dt><dd className="mono">{formatDuration(subject.timeInZoneSeconds)}</dd></div><div><dt>Person track confidence</dt><dd className="mono">{subject.personConfidence == null ? "Checking" : `${Math.round(subject.personConfidence * 100)}%`}</dd></div></dl></div> : <div className="enterprise-empty"><UserRound /><strong>No staff member in the current camera view</strong><span>A person track will appear automatically. Employee identity remains optional for tracking and PPE monitoring.</span></div>}</article>
      <aside className="panel policy-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Tracking contract</span><h2>What the system measures</h2><p>Every label has a defined source and an explicit uncertainty boundary.</p></div></div><Separator /><ol><li><span><ScanLine /></span><div><strong>Person track</strong><p>A local track ID follows movement within this camera.</p></div></li><li><span><MapPin /></span><div><strong>Operational zone</strong><p>Stable configured-zone transitions create retained evidence.</p></div></li><li><span><Radio /></span><div><strong>Activity context</strong><p>The active SOP and zone provide context; detailed actions need site-trained models.</p></div></li><li><span><BadgeCheck /></span><div><strong>Optional identity</strong><p>An approved badge or access-control event may associate the track.</p></div></li></ol></aside>
    </section>
    <section className="panel enterprise-table-panel department-ledger"><div className="enterprise-panel-heading"><div><span className="eyebrow">Movement ledger</span><h2>Recent staff observations</h2><p>Entries, stable zone changes, and unresolved identity observations remain reviewable.</p></div></div><Table><TableHeader><TableRow><TableHead>Observation</TableHead><TableHead>Staff / track</TableHead><TableHead>Zone</TableHead><TableHead>Confidence</TableHead><TableHead>Source</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{events.length ? events.map((event) => <TableRow key={event.id}><TableCell><strong>{event.title}</strong><small>{event.detail}</small></TableCell><TableCell>{event.employeeName ?? (event.trackId == null ? "Unresolved" : `Track ${event.trackId}`)}</TableCell><TableCell>{event.zone ?? "—"}</TableCell><TableCell className="mono">{event.confidence == null ? "Unknown" : `${Math.round(event.confidence * 100)}%`}</TableCell><TableCell><SourceBadge mode={event.sourceMode} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={6}><div className="enterprise-empty"><MapPin /><strong>No staff movement records in the loaded ledger</strong><span>Stable camera-zone transitions and badge-based entries will appear here.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
