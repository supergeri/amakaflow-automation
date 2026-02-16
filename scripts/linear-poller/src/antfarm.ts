/**
 * Antfarm workflow runner.
 *
 * `antfarm workflow run` is non-blocking — it starts a run and exits immediately.
 * This module starts the run, extracts the run ID, then polls
 * `antfarm workflow status <run-id>` until the run completes or fails.
 */

import { execFileSync, spawn } from "node:child_process";
import type { Config } from "./config.js";
import { log } from "./log.js";

export interface AntfarmResult {
  success: boolean;
  runId: string | null;
  finalStatus: string;  // "completed" | "failed" | "cancelled" | "timed_out"
  stderr: string;
  exitCode: number | null;
  timedOut: boolean;
  durationMs: number;
}

/**
 * Build the task prompt from a Linear issue.
 * This is what gets passed to `antfarm workflow run <workflow> "<task>"`.
 */
export function buildTaskPrompt(issue: {
  identifier: string;
  title: string;
  description: string;
  url: string;
}): string {
  // Truncate description to avoid shell argument limits (~100KB is safe, but be conservative)
  const maxDescLen = 8000;
  const desc =
    issue.description.length > maxDescLen
      ? issue.description.slice(0, maxDescLen) + "\n\n[description truncated]"
      : issue.description;

  return [
    `Linear ticket: ${issue.identifier} — ${issue.title}`,
    `URL: ${issue.url}`,
    "",
    "## Description",
    desc,
    "",
    "## Instructions",
    "- Follow the ticket description exactly",
    "- Commit your work with a message referencing the ticket ID",
    "- If the ticket references specific files, only modify those files",
    "- Run any relevant tests before finishing",
  ].join("\n");
}

/**
 * Start an Antfarm workflow run. Returns the run ID or throws.
 * `antfarm workflow run` exits immediately with the run ID in stdout.
 */
function startWorkflow(config: Config, task: string): string {
  const result = (() => {
    try {
      const stdout = execFileSync(
        config.antfarmBin,
        ["workflow", "run", config.antfarmWorkflow, task],
        { encoding: "utf-8", timeout: 30_000, env: { ...process.env } }
      );
      return { stdout, stderr: "", exitCode: 0 };
    } catch (err: unknown) {
      const e = err as { stdout?: string; stderr?: string; status?: number; message?: string };
      return {
        stdout: e.stdout || "",
        stderr: e.stderr || e.message || "unknown error",
        exitCode: e.status ?? 1,
      };
    }
  })();

  if (result.exitCode !== 0) {
    throw new Error(`antfarm workflow run failed (exit ${result.exitCode}): ${result.stderr.trim()}`);
  }

  // Extract run ID from output like "Run: e4ca9670-2dcd-4b92-adea-6cdb39161440"
  const match = result.stdout.match(/Run:\s+([0-9a-f-]+)/i);
  if (!match) {
    throw new Error(`Could not extract run ID from antfarm output: ${result.stdout.trim()}`);
  }

  return match[1];
}

/**
 * Poll `antfarm workflow status <run-id>` and return the current status.
 * Returns: "running" | "completed" | "failed" | "cancelled" | "unknown"
 */
function checkRunStatus(config: Config, runId: string): { status: string; output: string } {
  try {
    const stdout = execFileSync(
      config.antfarmBin,
      ["workflow", "status", runId],
      { encoding: "utf-8", timeout: 15_000, env: { ...process.env } }
    );

    // Parse "Status: running" or "Status: completed" etc.
    const statusMatch = stdout.match(/Status:\s+(\w+)/i);
    const status = statusMatch ? statusMatch[1].toLowerCase() : "unknown";

    return { status, output: stdout };
  } catch {
    return { status: "unknown", output: "" };
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Run an Antfarm workflow and wait for completion by polling status.
 *
 * 1. Start the run (non-blocking)
 * 2. Poll status every `statusPollIntervalMs` until done or timeout
 * 3. Return final result
 */
export async function runWorkflow(
  config: Config,
  task: string
): Promise<AntfarmResult> {
  const startTime = Date.now();
  const statusPollMs = 30_000;  // Check status every 30s

  // Step 1: Start the run
  let runId: string;
  try {
    runId = startWorkflow(config, task);
  } catch (err) {
    return {
      success: false,
      runId: null,
      finalStatus: "failed",
      stderr: (err as Error).message,
      exitCode: 1,
      timedOut: false,
      durationMs: Date.now() - startTime,
    };
  }

  log.info("antfarm", `Run started: ${runId}`);

  // Step 2: Poll status until completion or timeout
  let lastStatus = "running";
  let lastOutput = "";

  while (true) {
    const elapsed = Date.now() - startTime;

    // Timeout check
    if (elapsed >= config.antfarmTimeoutMs) {
      log.warn("antfarm", `Timeout after ${Math.round(elapsed / 1000)}s — cancelling run`);
      try {
        execFileSync(config.antfarmBin, ["workflow", "stop", runId], {
          encoding: "utf-8",
          timeout: 15_000,
          env: { ...process.env },
        });
      } catch {
        log.error("antfarm", "Failed to cancel timed-out run");
      }

      return {
        success: false,
        runId,
        finalStatus: "timed_out",
        stderr: `Workflow timed out after ${Math.round(config.antfarmTimeoutMs / 1000)}s`,
        exitCode: null,
        timedOut: true,
        durationMs: elapsed,
      };
    }

    await sleep(statusPollMs);

    const { status, output } = checkRunStatus(config, runId);
    lastStatus = status;
    lastOutput = output;

    const elapsedMin = Math.round((Date.now() - startTime) / 60_000);
    log.debug("antfarm", `Run ${runId.slice(0, 8)}: ${status} (${elapsedMin}m elapsed)`);

    // Terminal states
    if (status === "completed") {
      return {
        success: true,
        runId,
        finalStatus: "completed",
        stderr: "",
        exitCode: 0,
        timedOut: false,
        durationMs: Date.now() - startTime,
      };
    }

    if (status === "failed" || status === "cancelled") {
      return {
        success: false,
        runId,
        finalStatus: status,
        stderr: lastOutput,
        exitCode: 1,
        timedOut: false,
        durationMs: Date.now() - startTime,
      };
    }

    // "running", "unknown" → keep polling
  }
}
