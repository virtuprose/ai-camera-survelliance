import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const edgeHealthUrl = "http://127.0.0.1:8787/health";
const dashboardUrl = "http://localhost:3000/live";
const started: Array<{ name: string; process: Bun.Subprocess }> = [];

type LocalState = {
  health: {
    cameraLabel: string;
    processedFps: number;
    automaticMonitoring: "active" | "warming_up" | "attention" | "unavailable";
    monitoringMessage: string;
    storage: "online" | "degraded" | "offline" | "connecting";
    storageError: string | null;
    ppeVerifier?: { status: "passed" | "failed"; automaticSelfTest: boolean; failures: string[] };
  };
};

async function reachable(url: string) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1_500) });
    return response.ok;
  } catch {
    return false;
  }
}

function start(name: string, command: string[]) {
  const child = Bun.spawn(command, {
    cwd: projectRoot,
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  started.push({ name, process: child });
}

async function waitUntilReady(name: string, url: string, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await reachable(url)) return;
    await Bun.sleep(500);
  }
  throw new Error(`${name} did not become ready within ${Math.round(timeoutMs / 1_000)} seconds.`);
}

async function waitForAutomaticMonitoring(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let latest: LocalState | null = null;
  let attentionSince: number | null = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch("http://127.0.0.1:8787/api/state", { signal: AbortSignal.timeout(1_500) });
      if (response.ok) {
        latest = await response.json() as LocalState;
        if (latest.health.automaticMonitoring === "active" || latest.health.automaticMonitoring === "unavailable") return latest;
        if (latest.health.automaticMonitoring === "attention") {
          attentionSince ??= Date.now();
          if (Date.now() - attentionSince >= 15_000) return latest;
        } else {
          attentionSince = null;
        }
      }
    } catch {
      // Startup polling continues until the shared timeout expires.
    }
    await Bun.sleep(500);
  }
  if (latest) return latest;
  throw new Error("Camera monitoring did not report a readiness state within 60 seconds.");
}

async function stopStarted() {
  for (const service of started) {
    try {
      service.process.kill("SIGTERM");
    } catch {
      // The child may already have exited.
    }
  }
  await Promise.allSettled(started.map((service) => service.process.exited));
}

async function main() {
  const edgeAlreadyRunning = await reachable(edgeHealthUrl);
  const dashboardAlreadyRunning = await reachable(dashboardUrl);

  console.log("\nORVIA AI Surveillance · automatic local startup");
  if (edgeAlreadyRunning) console.log("✓ Edge camera service already running");
  else {
    console.log("Starting camera and automatic PPE monitoring…");
    start("edge camera service", ["bun", "run", "edge"]);
  }

  if (dashboardAlreadyRunning) console.log("✓ Dashboard already running");
  else {
    console.log("Starting local dashboard…");
    start("dashboard", ["bun", "run", "dev"]);
  }

  await Promise.all([
    waitUntilReady("Edge camera service", edgeHealthUrl),
    waitUntilReady("Dashboard", dashboardUrl),
  ]);

  const state = await waitForAutomaticMonitoring();
  console.log("\n✓ Local demo ready");
  console.log(`✓ Camera: ${state.health.cameraLabel}`);
  console.log(`✓ Processing: ${state.health.processedFps.toFixed(1)} FPS`);
  console.log(`${state.health.ppeVerifier?.status === "passed" ? "✓" : "!"} PPE verifier: ${state.health.ppeVerifier?.status === "passed" ? "automatic self-test passed" : "disabled"}`);
  console.log(`${state.health.storage === "online" ? "✓" : "!"} Local evidence store: ${state.health.storage}${state.health.storageError ? ` · ${state.health.storageError}` : ""}`);
  const stateMark = state.health.automaticMonitoring === "active" ? "✓" : "!";
  console.log(`${stateMark} Automatic monitoring: ${state.health.automaticMonitoring}`);
  console.log(`${stateMark} ${state.health.monitoringMessage}`);
  console.log(`\nOpen ${dashboardUrl}`);
  console.log("Person and PPE detection begin automatically. No badge or acceptance command is required.\n");

  if (started.length === 0) return;

  const stopRequest = new Promise<{ reason: string; code: number }>((resolveStop) => {
    process.once("SIGINT", () => resolveStop({ reason: "Stopped by operator", code: 0 }));
    process.once("SIGTERM", () => resolveStop({ reason: "Stopped by system", code: 0 }));
  });
  const childExit = Promise.race(started.map(async (service) => ({
    reason: `${service.name} exited unexpectedly`,
    code: await service.process.exited,
  })));
  const outcome = await Promise.race([stopRequest, childExit]);
  console.log(`\n${outcome.reason}. Shutting down local demo services…`);
  await stopStarted();
  process.exit(outcome.code);
}

main().catch(async (error) => {
  console.error(`\nLocal startup failed: ${error instanceof Error ? error.message : String(error)}`);
  await stopStarted();
  process.exit(1);
});
