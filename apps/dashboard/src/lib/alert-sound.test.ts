import { describe, expect, it } from "vitest";
import { seedEvents } from "@/lib/demo-state";
import { isViolationAlert, unseenViolations } from "@/lib/alert-sound";

describe("violation alert selection", () => {
  it("accepts only new PPE or temperature violations", () => {
    expect(isViolationAlert(seedEvents[0])).toBe(true);
    expect(isViolationAlert(seedEvents[1])).toBe(false);
    expect(isViolationAlert(seedEvents[2])).toBe(false);
    expect(isViolationAlert({ ...seedEvents[2], status: "new" })).toBe(true);
  });

  it("suppresses previously seen ids and returns newest first", () => {
    const first = { ...seedEvents[0], id: "first", occurredAt: "2026-08-22T10:00:00.000Z" };
    const latest = { ...seedEvents[0], id: "latest", occurredAt: "2026-08-22T10:01:00.000Z" };
    expect(unseenViolations([first, latest], new Set(["first"]))).toEqual([latest]);
  });
});
