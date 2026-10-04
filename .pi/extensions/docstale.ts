import childProcess from "node:child_process";
import type {
	ExtensionAPI,
	ExtensionContext,
} from "@earendil-works/pi-coding-agent";

type HookEvent = "SessionStart" | "Stop";
type HookResult = { stdout: string; stderr: string };

const TIMEOUT_MS = 30_000;
const MAX_BUFFER = 1024 * 1024;

function invokeHook(
	ctx: ExtensionContext,
	event: HookEvent,
	signal: AbortSignal,
): Promise<HookResult> {
	const executable = process.env.DOCSTALE_EXECUTABLE || "docstale";
	const payload = {
		hook_event_name: event,
		session_id: `pi:${ctx.sessionManager.getSessionId()}`,
		cwd: ctx.cwd,
		...(event === "Stop" ? { stop_hook_active: false } : {}),
	};

	return new Promise((resolve, reject) => {
		const child = childProcess.execFile(
			executable,
			["hook"],
			{
				cwd: ctx.cwd,
				encoding: "utf8",
				timeout: TIMEOUT_MS,
				maxBuffer: MAX_BUFFER,
				killSignal: "SIGKILL",
				signal,
				windowsHide: true,
			},
			(error, stdout, stderr) => {
				if (!error) {
					resolve({ stdout, stderr });
				} else if (error.code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER") {
					reject(new Error("docstale hook exceeded its output limit."));
				} else if (error.killed && error.signal === "SIGKILL") {
					reject(new Error("docstale hook exceeded its 30-second timeout."));
				} else {
					reject(new Error(stderr.trim() || error.message));
				}
			},
		);
		// Handle a closed input pipe without an unhandled stream error.
		child.stdin?.on("error", reject);
		child.stdin?.end(JSON.stringify(payload));
	});
}

function readReason(stdout: string): string | undefined {
	if (!stdout.trim()) return undefined;
	let value: unknown;
	try {
		value = JSON.parse(stdout);
	} catch {
		throw new Error("docstale hook returned invalid JSON.");
	}
	if (
		value === null ||
		typeof value !== "object" ||
		!("decision" in value) ||
		value.decision !== "block" ||
		!("reason" in value) ||
		typeof value.reason !== "string" ||
		!value.reason.trim()
	) {
		throw new Error("docstale hook returned an invalid response.");
	}
	return value.reason;
}

function reportWarning(ctx: ExtensionContext, message: string): void {
	if (ctx.hasUI) {
		ctx.ui.notify(message, "warning");
	} else {
		// Print and JSON/RPC modes must keep stdout free of diagnostics.
		console.error(message);
	}
}

function failureReason(error: unknown): string {
	return `docstale could not complete its check: ${error instanceof Error ? error.message : String(error)}`;
}

export default function docstale(pi: ExtensionAPI): void {
	let continuationActive = false;
	const pending = new Set<AbortController>();

	async function run(
		event: HookEvent,
		ctx: ExtensionContext,
	): Promise<HookResult | undefined> {
		const controller = new AbortController();
		const signal = ctx.signal
			? AbortSignal.any([controller.signal, ctx.signal])
			: controller.signal;
		if (signal.aborted) return undefined;
		pending.add(controller);
		try {
			const result = await invokeHook(ctx, event, signal);
			return signal.aborted ? undefined : result;
		} catch (error) {
			if (signal.aborted) return undefined;
			// An input-pipe error can precede process exit. Cancel that process.
			controller.abort();
			throw error;
		} finally {
			pending.delete(controller);
		}
	}

	pi.on("session_start", async (_event, ctx) => {
		continuationActive = false;
		try {
			const result = await run("SessionStart", ctx);
			if (!result) return;
			if (result.stderr.trim()) reportWarning(ctx, result.stderr.trim());
			if (result.stdout.trim()) {
				throw new Error(
					"docstale hook returned unexpected SessionStart output.",
				);
			}
		} catch (error) {
			reportWarning(ctx, failureReason(error));
		}
	});

	pi.on("agent_before_settle", async (event, ctx) => {
		// Do not check the review continuation or restart cancelled/failed work.
		// Defer if an earlier extension already requested more work.
		if (continuationActive || event.outcome !== "completed" || event.continue)
			return;
		let reason: string | undefined;
		try {
			const result = await run("Stop", ctx);
			if (!result) return;
			if (result.stderr.trim()) reportWarning(ctx, result.stderr.trim());
			reason = readReason(result.stdout);
		} catch (error) {
			reason = failureReason(error);
		}
		if (!reason) return;
		continuationActive = true;
		return {
			entries: [
				...event.entries,
				{
					type: "custom_message" as const,
					customType: "docstale",
					content: reason,
					display: true,
				},
			],
			continue: true,
		};
	});

	pi.on("agent_settled", () => {
		continuationActive = false;
	});
	pi.on("session_shutdown", () => {
		for (const controller of pending) controller.abort();
	});
}
