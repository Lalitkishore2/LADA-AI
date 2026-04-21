import { spawnSync } from "node:child_process";
import {
  acquireLocalHeavyCheckLockSync,
  applyLocalOxlintPolicy,
} from "./lib/local-heavy-check-runtime.mjs";
import { createPnpmRunnerSpawnSpec } from "./pnpm-runner.mjs";

const { args: finalArgs, env } = applyLocalOxlintPolicy(process.argv.slice(2), process.env);

const releaseLock = acquireLocalHeavyCheckLockSync({
  cwd: process.cwd(),
  env,
  toolName: "oxlint",
});

try {
  const spawnSpec = createPnpmRunnerSpawnSpec({
    pnpmArgs: ["exec", "oxlint", ...finalArgs],
    cwd: process.cwd(),
    stdio: "inherit",
    env,
  });
  const result = spawnSync(spawnSpec.command, spawnSpec.args, spawnSpec.options);

  if (result.error) {
    throw result.error;
  }

  process.exit(result.status ?? 1);
} finally {
  releaseLock();
}
