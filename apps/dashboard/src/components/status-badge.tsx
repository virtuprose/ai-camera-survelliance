import { AlertCircle, Check, Circle, FlaskConical, Info, WifiOff } from "lucide-react";
import type { ConnectionState, Severity } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Tone = "safe" | "warning" | "critical" | "neutral" | "info" | "simulated";
const icons = { safe: Check, warning: AlertCircle, critical: AlertCircle, neutral: Circle, info: Info, simulated: FlaskConical };

export function StatusBadge({ label, tone = "neutral", className }: { label: string; tone?: Tone; className?: string }) {
  const isNew = label.trim().toLowerCase() === "new";
  const Icon = isNew ? Circle : icons[tone];
  return <Badge variant="outline" className={cn("status-badge", `tone-${tone}`, isNew && "is-new", className)}><Icon aria-hidden="true" />{label}</Badge>;
}

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  if (state === "online") return <StatusBadge label="Online" tone="safe" />;
  if (state === "degraded") return <StatusBadge label="Degraded" tone="warning" />;
  if (state === "connecting") return <StatusBadge label="Connecting" tone="info" />;
  return <Badge variant="outline" className="status-badge tone-critical"><WifiOff aria-hidden="true" />Offline</Badge>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <StatusBadge label={severity[0].toUpperCase() + severity.slice(1)} tone={severity === "critical" ? "critical" : severity === "warning" ? "warning" : "info"} />;
}
