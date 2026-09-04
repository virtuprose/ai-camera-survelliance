import type { DemoEvent } from "@/lib/types";

export const ALERT_SOUND_STORAGE_KEY = "safeguard.alert-sound.enabled.v1";

export function isViolationAlert(event: DemoEvent): boolean {
  return event.status === "new" && (event.type === "ppe_violation" || event.type === "temperature_alert");
}

export function unseenViolations(events: DemoEvent[], seenIds: ReadonlySet<string>): DemoEvent[] {
  return events
    .filter((event) => !seenIds.has(event.id) && isViolationAlert(event))
    .sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());
}
