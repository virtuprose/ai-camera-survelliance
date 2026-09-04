import { describe, expect, it } from "vitest";
import { formatClock, formatDateTime, formatDuration, formatRelative } from "@/lib/format";

describe("format helpers", () => {
  it("formats a duration as minutes and seconds", () => {
    expect(formatDuration(125)).toBe("02:05");
  });

  it("uses a safe value for missing timestamps", () => {
    expect(formatRelative(null)).toBe("never");
  });

  it("renders Kuwait timestamps deterministically across server and browser runtimes", () => {
    expect(formatClock("2026-08-22T00:00:00.000Z")).toBe("03:00:00");
    expect(formatDateTime("2026-08-22T00:00:00.000Z")).toBe("22 Aug 2026, 03:00");
  });
});
