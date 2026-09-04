import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const edgeRoot = resolve(projectRoot, "services/edge");
const started: Bun.Subprocess[] = [];

async function reachable(url: string) {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(1_500) })).ok;
  } catch {
    return false;
  }
}

async function waitUntilReady(label: string, url: string, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await reachable(url)) return;
    await Bun.sleep(500);
  }
  throw new Error(`${label} did not become ready within ${Math.round(timeoutMs / 1_000)} seconds.`);
}

function start(command: string[], cwd: string, env?: Record<string, string>) {
  const child = Bun.spawn(command, {
    cwd,
    env: { ...process.env, ...env },
    stdin: "ignore",
    stdout: "inherit",
    stderr: "inherit",
  });
  started.push(child);
}

async function stopStarted() {
  for (const child of started) {
    try {
      child.kill("SIGTERM");
    } catch {
      // A service may already have stopped after a test failure.
    }
  }
  const graceful = Promise.allSettled(started.map((child) => child.exited)).then(() => true);
  const stopped = await Promise.race([graceful, Bun.sleep(5_000).then(() => false)]);
  if (!stopped) {
    for (const child of started) {
      try {
        child.kill("SIGKILL");
      } catch {
        // The service may have exited during the grace period.
      }
    }
    await Promise.allSettled(started.map((child) => child.exited));
  }
}

async function main() {
  if (!(await reachable("http://127.0.0.1:8787/health"))) {
    start(
      ["uv", "run", "uvicorn", "foodsafe_edge.main:app", "--host", "127.0.0.1", "--port", "8787"],
      edgeRoot,
      { CAMERA_ENABLED: "false", DATA_DIR: "data/e2e" },
    );
  }

  if (!(await reachable("http://localhost:3000"))) {
    start(["bun", "run", "--cwd", "apps/dashboard", "dev"], projectRoot);
  }

  await Promise.all([
    waitUntilReady("isolated edge test service", "http://127.0.0.1:8787/health"),
    waitUntilReady("dashboard test service", "http://localhost:3000"),
  ]);

  const tests = Bun.spawn(["bun", "run", "--cwd", "apps/dashboard", "test:e2e"], {
    cwd: projectRoot,
    env: process.env,
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  const code = await tests.exited;
  await stopStarted();
  process.exit(code);
}

process.once("SIGINT", async () => {
  await stopStarted();
  process.exit(130);
});

process.once("SIGTERM", async () => {
  await stopStarted();
  process.exit(143);
});

main().catch(async (error) => {
  console.error(error instanceof Error ? error.message : String(error));
  await stopStarted();
  process.exit(1);
});
