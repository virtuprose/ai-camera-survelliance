function part(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) {
  return parts.find((item) => item.type === type)?.value ?? "";
}

export function formatClock(value: string | null) {
  if (!value) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuwait",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  return `${part(parts, "hour")}:${part(parts, "minute")}:${part(parts, "second")}`;
}

export function formatDateTime(value: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuwait",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  return `${part(parts, "day")} ${part(parts, "month")} ${part(parts, "year")}, ${part(parts, "hour")}:${part(parts, "minute")}`;
}

export function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function formatConfidence(value: number | null) {
  return value === null ? "Not measured" : `${Math.round(value * 100)}% confidence`;
}

export function formatRelative(value: string | null, referenceTime = Date.now()) {
  if (!value) return "never";
  const seconds = Math.max(0, Math.floor((referenceTime - new Date(value).getTime()) / 1_000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return formatDateTime(value);
}
