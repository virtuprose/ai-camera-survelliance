import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fallbackState } from "../../src/lib/demo-state";

const routes = [
  ["/", "Command center"], ["/live", "Live operations"],
  ["/food-safety", "Food safety & PPE"], ["/processes", "Process assurance"],
  ["/staff", "Staff visibility"], ["/cold-chain", "Cold chain"], ["/inventory", "Inventory"],
  ["/incidents", "Incidents & evidence"], ["/reports", "Reports & audit"],
  ["/platform", "Platform"],
] as const;

async function expectAccessible(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).exclude(".camera-frame").analyze();
  expect(results.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
}

async function expectAppReady(page: import("@playwright/test").Page) {
  await expect(page.getByText("Edge online", { exact: true })).toBeVisible({ timeout: 8_000 });
}

test("all enterprise routes render with branding and accessibility", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  for (const [path, heading] of routes) {
    await page.goto(path, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expectAppReady(page);
    await expect(page.getByAltText("ORVIA")).toBeVisible();
    await expect(page).toHaveTitle(/ORVIA AI Surveillance/);
    await expect(page.getByText("Controlled pilot", { exact: true })).toHaveCount(0);
    await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
    await expectAccessible(page);
    await page.screenshot({ path: `test-results/screenshots/enterprise-${path === "/" ? "command" : path.slice(1)}.png`, fullPage: true, animations: "disabled" });
  }
  expect(consoleErrors).toEqual([]);
});

test("legacy routes redirect to the enterprise replacements", async ({ page }) => {
  await page.goto("/events", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/incidents$/);
  await page.goto("/system", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/platform$/);
});

test("workspace selector separates live simulated and planned contexts", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  await page.getByRole("button", { name: "Change active workspace" }).click();
  await expect(page.getByRole("button", { name: /Kitchen 01.*CAM-01.*live/i })).toBeEnabled();
  for (const workspace of ["Receiving", "Cold Storage", "Inventory Store"]) {
    await expect(page.getByRole("button", { name: new RegExp(`${workspace}.*simulated`, "i") })).toBeEnabled();
  }
  await expect(page.getByRole("button", { name: /Secondary Facility.*Future facility.*Planned/i })).toBeDisabled();
  await expect(page.getByText(/Simulated departments are interactive demonstration environments/i)).toBeVisible();
});

test("demo persona changes navigation emphasis without claiming authorization", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  await expect(page.getByText("View as · Demo", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Change demo view" }).click();
  await page.getByRole("option", { name: "Executive" }).click();
  await expect(page.getByRole("link", { name: "Reports & audit" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Live operations" })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Change demo view" }).click();
  await page.getByRole("option", { name: "IT" }).click();
  await expect(page.getByRole("link", { name: "Platform" })).toBeVisible();
});

test("incident workbench exposes lifecycle guards and retained detail", async ({ page }) => {
  const baselineResponse = await page.request.get("http://127.0.0.1:8787/api/enterprise/incidents?limit=250");
  const baselineIds = new Set(((await baselineResponse.json()) as { items: Array<{ id: string }> }).items.map((item) => item.id));
  await page.request.post("http://127.0.0.1:8787/api/demo/ppe-violation", { data: {} });
  let incidentId: string | undefined;
  await expect.poll(async () => {
    const response = await page.request.get("http://127.0.0.1:8787/api/enterprise/incidents?limit=250");
    const payload = (await response.json()) as { items: Array<{ id: string; title: string; sourceMode: string }> };
    incidentId = payload.items.find((item) => !baselineIds.has(item.id) && item.title === "Gloves not detected" && item.sourceMode === "simulated")?.id;
    return incidentId;
  }, { timeout: 8_000 }).toBeTruthy();
  await page.goto(`/incidents?id=${incidentId}`, { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  await expect(page.getByText("Gloves not detected", { exact: true }).first()).toBeVisible({ timeout: 8_000 });
  await expect(page.getByRole("button", { name: "Resolve incident" })).toBeDisabled();
  await expect(page.getByText("Retention until", { exact: true })).toBeVisible();
  await expectAccessible(page);
});

test("reports export CSV and PDF audit artifacts", async ({ page }) => {
  await page.goto("/reports", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  const csvPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV ledger" }).click();
  expect((await csvPromise).suggestedFilename()).toMatch(/food-safety-report-24h\.csv/);
  const pdfPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Audit PDF" }).click();
  expect((await pdfPromise).suggestedFilename()).toMatch(/\.pdf$/);
  await expect(page.getByText(/Unknown checks are retained but excluded/i)).toBeVisible();
});

test("violation sound is muted until explicitly enabled", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  const trigger = page.getByRole("button", { name: "Violation sound off" });
  await trigger.click();
  const soundSwitch = page.getByRole("switch", { name: "Play alert chime" });
  await expect(soundSwitch).not.toBeChecked();
  await soundSwitch.click();
  await expect(soundSwitch).toBeChecked();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("safeguard.alert-sound.enabled.v1"))).toBe("true");
});

test("mobile navigation and expanded operational tools remain accessible", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/live", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Tools" }).click();
  await expect(page.getByRole("button", { name: "Add overtime exception" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add count variance" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create enterprise exception set" })).toBeVisible();
  await expectAccessible(page);
});

test("badge identity works without profile imagery", async ({ page }) => {
  await page.route("**/api/edge/api/state", async (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...fallbackState, activeEmployee: { employeeId: "EMP-002", displayName: "Demo Operator B", photoUrl: null, badgeMarkerId: 102, identityMethod: "aruco_badge", trackId: 12, zone: "Preparation", activity: "Working in preparation", enteredAt: new Date().toISOString(), timeInZoneSeconds: 12, badgeConfidence: 0.99, ppe: { mask: null, gloves: null, hairnet: null, apron: null, confidence: null } } }) }));
  await page.goto("/live", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Demo Operator B", { exact: true })).toBeVisible();
  await expect(page.getByText("Identified by badge 102 · no biometric matching", { exact: true })).toBeVisible();
  await expect(page.locator(".employee-avatar img")).toHaveCount(0);
});

test("automatic PPE monitoring is ready without a manual acceptance command", async ({ page }) => {
  await page.route("**/api/edge/api/state", async (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      ...fallbackState,
      health: {
        ...fallbackState.health,
        edge: "online",
        camera: "online",
        stream: "online",
        processedFps: 9.6,
        automaticMonitoring: "active",
        monitoringMessage: "Camera analysis and PPE monitoring are running automatically.",
      },
      recentEvents: [],
    }),
  }));
  await page.goto("/live", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Live demo systems ready", { exact: true })).toBeVisible();
  await expect(page.getByText(/Camera fresh at 9\.6 FPS · PPE verifier self-test passed/i)).toBeVisible();
  await expect(page.getByText("Automatic PPE monitoring is active and waiting for a person. An employee badge is optional.", { exact: true })).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: "test-results/screenshots/automatic-monitoring-ready.png", fullPage: true, animations: "disabled" });
});

test("PPE monitoring remains active without employee identity", async ({ page }) => {
  let resetRequested = false;
  const observedAt = new Date().toISOString();
  const item = (state: "not_visible" | "checking" | "detected" | "missing", side: "left" | "right" | null = null, required = true) => ({
    state, confidence: state === "detected" || state === "missing" ? 0.93 : null,
    visibilityConfidence: state === "not_visible" ? 0.12 : 0.96,
    blueRatio: state === "detected" ? 0.28 : state === "missing" ? 0.01 : null,
    threshold: 0.05, stableForMs: state === "missing" ? 3_200 : 1_100, side, roi: null, required,
  });
  const ppeItems = {
    mask: item("missing"), left_glove: item("detected", "left"),
    right_glove: item("not_visible", "right"), hairnet: item("checking", null, false), apron: item("checking", null, false),
  };
  const readiness = {
    brightness: 112, lightingReady: true, faceVisible: true, leftHandVisible: true,
    rightHandVisible: false, torsoVisible: true, framingReady: false,
    guidance: ["Raise both hands for glove assessment"],
  };
  const detection = {
    status: "attention" as const,
    trackId: 17,
    identityDetected: false,
    identityStatus: { state: "not_associated" as const, label: "Identity not associated", detail: "Optional badge or access-control association; PPE monitoring remains active." },
    ppeDetected: false,
    issues: [
      { code: "mask_missing", title: "Mask not detected", detail: "The mask region was visible and remained below the configured blue-PPE threshold." },
    ],
    ppeItems,
    readiness,
    proof: { zone: "Preparation", activity: "PPE monitoring active", personConfidence: 0.98, ppeConfidence: 0.91, movementSamples: 18, evidencePolicy: "snapshot_and_clip_on_persistent_event" as const, brightness: 112, framingReady: false, assessmentAvailable: true },
    resetGeneration: 0,
    lastResetAt: null,
    updatedAt: observedAt,
  };
  await page.route("**/api/edge/api/detection/reset", async (route) => {
    resetRequested = true;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, detection: { ...fallbackState.detection, resetGeneration: 1, lastResetAt: observedAt } }) });
  });
  const maskEvent = { ...fallbackState.recentEvents[0], id: "evt-mask", occurredAt: observedAt, title: "Mask not detected", detail: "The visible face region remained below the configured controlled-PPE threshold for 3 seconds.", employeeId: null, employeeName: "Unidentified staff member", metadata: { item: "mask" } };
  const gloveEvent = { ...fallbackState.recentEvents[0], id: "evt-right-glove", occurredAt: observedAt, title: "Right glove not detected", detail: "The visible right-hand region remained below the configured controlled-PPE threshold for 3 seconds.", employeeId: null, employeeName: "Unidentified staff member", metadata: { item: "right_glove" } };
  await page.route("**/api/edge/api/state", async (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...fallbackState, health: { ...fallbackState.health, edge: "online", camera: "online", stream: "online", processedFps: 9.6, automaticMonitoring: "active", monitoringMessage: "Camera analysis and PPE monitoring are running automatically." }, recentEvents: [gloveEvent, maskEvent], detection, activeEmployee: { employeeId: null, displayName: "Unidentified staff member", photoUrl: null, badgeMarkerId: null, trackId: 17, zone: "Preparation", activity: "PPE monitoring active", enteredAt: observedAt, timeInZoneSeconds: 12, badgeConfidence: null, personConfidence: 0.98, ppe: { mask: false, gloves: null, hairnet: null, apron: null, confidence: 0.91, assessmentAvailable: true, items: ppeItems, readiness } } }) }));
  await page.goto("/live", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Unidentified staff member", { exact: true })).toBeVisible();
  await expect(page.getByText("Identity optional", { exact: true })).toBeVisible();
  await expect(page.getByText("PPE monitoring is active without employee identification. Badge or access-control matching can be added later.", { exact: true })).toBeVisible();
  const liveDetection = page.getByRole("alert", { name: "Live detection status" });
  await expect(liveDetection.getByText("Identity not associated", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("Mask not detected", { exact: true }).first()).toBeVisible();
  await expect(liveDetection.getByText("Left glove verified", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("Right hand not visible", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("No violation recorded", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("Raise both hands for glove assessment", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("18 samples", { exact: true })).toBeVisible();
  await expect(liveDetection.getByText("98%", { exact: true })).toBeVisible();
  await expect(page.locator(".active-violation").getByText("Mask not detected", { exact: true })).toBeVisible();
  await expect(page.getByText("PPE violation detected automatically", { exact: true })).toBeVisible();
  await expect(page.getByText("Verified", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Missing", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/live-detection-warning.png", fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Clear warnings" }).click();
  await expect(page.getByText("Warnings cleared for Track 17", { exact: true })).toBeVisible();
  await expect(liveDetection).toHaveCount(0);
  await page.getByRole("button", { name: "Reset detection" }).click();
  await expect.poll(() => resetRequested).toBe(true);
  await expect(page.getByText(/Detection reset.*retained events were not deleted/i)).toBeVisible();
  await expectAccessible(page);

  await page.goto("/staff", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Staff visibility", level: 1 })).toBeVisible();
  await expect(page.getByText("Unidentified staff member", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Track 17", { exact: true })).toBeVisible();
  await expect(page.getByText(/Identity optional; PPE remains active/i)).toBeVisible();
  await expectAccessible(page);
});

test("camera source selector lists discovered cameras and the labelled fallback", async ({ page }) => {
  let activeId = "facetime";
  let requestedId: string | null = null;
  const activeLabel = () => activeId === "camo" ? "Camo Camera" : activeId === "avf-samsung-slimfit-camera-demo1234" ? "Samsung SlimFit Camera" : activeId === "fallback" ? "Prerecorded local fallback" : "FaceTime HD Camera";
  const catalog = () => ({
    activeId,
    switchState: "idle",
    message: activeId === "facetime" ? null : `Switched to ${activeLabel()}.`,
    options: [
      { id: "facetime", label: "FaceTime HD Camera", description: "Built-in MacBook camera", kind: "avfoundation", source: "0", registered: true, active: activeId === "facetime" },
      { id: "camo", label: "Camo Camera", description: "iPhone through Camo Studio", kind: "avfoundation", source: "1", registered: true, active: activeId === "camo" },
      { id: "avf-samsung-slimfit-camera-demo1234", label: "Samsung SlimFit Camera", description: "Monitor camera detected by macOS", kind: "avfoundation", source: "2", registered: true, active: activeId === "avf-samsung-slimfit-camera-demo1234" },
      { id: "fallback", label: "Prerecorded local fallback", description: "Clearly labelled simulated presentation fallback", kind: "file", source: "/demo/fallback-demo.mp4", registered: true, active: activeId === "fallback" },
    ],
  });
  await page.route("**/api/edge/api/state", async (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      ...fallbackState,
      health: { ...fallbackState.health, edge: "online", camera: "online", stream: "online", processedFps: 9.6, automaticMonitoring: "active", monitoringMessage: "Camera analysis and PPE monitoring are running automatically.", cameraId: activeId, cameraLabel: activeLabel() },
    }),
  }));
  await page.route("**/api/edge/api/cameras", async (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(catalog()) }));
  await page.route("**/api/edge/api/cameras/active", async (route) => {
    requestedId = ((await route.request().postDataJSON()) as { cameraId: string }).cameraId;
    activeId = requestedId;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(catalog()) });
  });

  await page.goto("/live", { waitUntil: "domcontentloaded" });
  await expectAppReady(page);
  await page.getByRole("button", { name: /Change camera source.*FaceTime HD Camera/i }).click();
  await expect(page.getByText("3 connected cameras detected by macOS.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /FaceTime HD Camera.*Active/i })).toBeDisabled();
  const camoOption = page.getByRole("button", { name: /Camo Camera.*Available/i });
  await expect(camoOption).toBeEnabled();
  await camoOption.click();
  await expect.poll(() => requestedId).toBe("camo");
  await expect(page.getByRole("button", { name: /Camo Camera.*Active/i })).toBeDisabled();
  await expect(page.getByText("Switched to Camo Camera.", { exact: true })).toBeVisible();
  const samsungOption = page.getByRole("button", { name: /Samsung SlimFit Camera.*Available/i });
  await expect(samsungOption).toBeEnabled();
  await samsungOption.click();
  await expect.poll(() => requestedId).toBe("avf-samsung-slimfit-camera-demo1234");
  await expect(page.getByRole("button", { name: /Samsung SlimFit Camera.*Active/i })).toBeDisabled();
  await expect(page.getByText("Switched to Samsung SlimFit Camera.", { exact: true })).toBeVisible();
  const fallbackOption = page.getByRole("button", { name: /Prerecorded local fallback.*Available/i });
  await expect(fallbackOption).toBeEnabled();
  await fallbackOption.click();
  await expect.poll(() => requestedId).toBe("fallback");
  await expect(page.getByRole("button", { name: /Prerecorded local fallback.*Active/i })).toBeDisabled();
  await expect(page.getByText("Switched to Prerecorded local fallback.", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/camera-source-selector.png", fullPage: true, animations: "disabled" });
  await expectAccessible(page);
});

for (const viewport of [
  { name: "phone-375", width: 375, height: 900 }, { name: "tablet-768", width: 768, height: 1024 },
  { name: "laptop-1024", width: 1024, height: 900 }, { name: "desktop-1440", width: 1440, height: 1000 },
]) {
  test(`command center and live operations are responsive at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const [path, heading, suffix] of [["/", "Command center", "command"], ["/live", "Live operations", "live"]] as const) {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
      if (path === "/live") await page.waitForTimeout(1_500);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
      await page.screenshot({ path: `test-results/screenshots/${viewport.name}-${suffix}.png`, fullPage: true, animations: "disabled" });
    }
  });
}
