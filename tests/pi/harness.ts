import type {
	AgentBeforeSettleEvent,
	BoundaryResult,
	ExtensionAPI,
	ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import docstale from "../../.pi/extensions/docstale.ts";

type Handler = (event: unknown, ctx: ExtensionContext) => unknown;

export function createHarness(cwd = "/checkout with spaces") {
	const handlers = new Map<string, Handler>();
	const notifications: { message: string; level: string }[] = [];
	let sessionId = "one";
	const ctx = {
		cwd,
		hasUI: true,
		mode: "tui",
		signal: undefined,
		sessionManager: { getSessionId: () => sessionId },
		ui: {
			notify: (message: string, level: string) =>
				notifications.push({ message, level }),
		},
	} as unknown as ExtensionContext;
	const pi = {
		on(name: string, handler: Handler) {
			handlers.set(name, handler);
			return () => handlers.delete(name);
		},
	} as unknown as ExtensionAPI;
	docstale(pi);

	async function emit(name: string, event: Record<string, unknown> = {}) {
		return handlers.get(name)?.({ type: name, ...event }, ctx);
	}

	return {
		ctx,
		handlers,
		notifications,
		emit,
		setSessionId(id: string) {
			sessionId = id;
		},
		start(reason = "startup") {
			return emit("session_start", { reason });
		},
		settled() {
			return emit("agent_settled");
		},
		stop(event: Partial<AgentBeforeSettleEvent> = {}) {
			return emit("agent_before_settle", {
				entries: [],
				continue: false,
				outcome: "completed",
				// Normal settlement ends with an assistant message. The adapter's
				// custom message creates runnable context even when this is false.
				context: { canContinue: false },
				...event,
			}) as Promise<BoundaryResult | undefined>;
		},
	};
}
