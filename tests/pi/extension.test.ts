import assert from "node:assert/strict";
import childProcess, { type ExecFileOptions } from "node:child_process";
import { PassThrough } from "node:stream";
import { test, type TestContext } from "node:test";
import { createHarness } from "./harness.ts";

type ExecCallback = (
	error: Error | null,
	stdout: string,
	stderr: string,
) => void;

type Reply = {
	stdout?: string;
	stderr?: string;
	error?: Error;
	action?: () => void;
};

function mockHook(t: TestContext, ...replies: Reply[]) {
	const calls: {
		executable: string;
		args: string[];
		options: ExecFileOptions;
		payload?: unknown;
	}[] = [];
	t.mock.method(
		childProcess,
		"execFile",
		(
			executable: string,
			args: string[],
			options: ExecFileOptions,
			callback: ExecCallback,
		) => {
			const call = { executable, args, options, payload: undefined as unknown };
			calls.push(call);
			const reply = replies.shift() ?? {};
			const stdin = new PassThrough();
			let input = "";
			stdin.on("data", (data) => {
				input += data.toString();
			});
			stdin.on("finish", () => {
				call.payload = JSON.parse(input);
				reply.action?.();
				callback(reply.error ?? null, reply.stdout ?? "", reply.stderr ?? "");
			});
			return { stdin };
		},
	);
	const oldExecutable = process.env.DOCSTALE_EXECUTABLE;
	delete process.env.DOCSTALE_EXECUTABLE;
	t.after(() => {
		if (oldExecutable === undefined) delete process.env.DOCSTALE_EXECUTABLE;
		else process.env.DOCSTALE_EXECUTABLE = oldExecutable;
	});
	return calls;
}

const block = (reason = "Review README.md.") =>
	JSON.stringify({ decision: "block", reason });

test("the factory only registers session handlers", (t) => {
	const calls = mockHook(t);
	const harness = createHarness();
	assert.deepEqual(
		[...harness.handlers.keys()],
		[
			"session_start",
			"agent_before_settle",
			"agent_settled",
			"session_shutdown",
		],
	);
	assert.equal(calls.length, 0);
});

test("session and Stop payloads use the active directory and namespaced session ID", async (t) => {
	const calls = mockHook(t);
	const harness = createHarness();
	harness.setSessionId('a"b\\c');
	await harness.start();
	await harness.stop();
	assert.deepEqual(
		calls.map((call) => call.payload),
		[
			{
				hook_event_name: "SessionStart",
				session_id: 'pi:a"b\\c',
				cwd: harness.ctx.cwd,
			},
			{
				hook_event_name: "Stop",
				session_id: 'pi:a"b\\c',
				cwd: harness.ctx.cwd,
				stop_hook_active: false,
			},
		],
	);
	for (const call of calls) {
		assert.equal(call.executable, "docstale");
		assert.deepEqual(call.args, ["hook"]);
		assert.equal(call.options.cwd, harness.ctx.cwd);
		assert.equal(call.options.timeout, 30_000);
		assert.equal(call.options.maxBuffer, 1024 * 1024);
		assert.equal(call.options.killSignal, "SIGKILL");
		assert.equal(call.options.encoding, "utf8");
		assert.equal(call.options.windowsHide, true);
		assert.equal(call.options.shell, undefined);
		assert.ok(call.options.signal instanceof AbortSignal);
	}
});

test("an executable override is one path, not a shell command", async (t) => {
	const calls = mockHook(t);
	process.env.DOCSTALE_EXECUTABLE = "/tools with spaces/docstale;not-a-command";
	await createHarness().start();
	assert.equal(calls[0].executable, process.env.DOCSTALE_EXECUTABLE);
	assert.deepEqual(calls[0].args, ["hook"]);
});

test("empty output is silent", async (t) => {
	mockHook(t, {}, { stdout: " \n" });
	const harness = createHarness();
	assert.equal(await harness.start(), undefined);
	assert.equal(await harness.stop(), undefined);
	assert.deepEqual(harness.notifications, []);
});

test("a reminder preserves earlier entries and requests exactly one continuation", async (t) => {
	const calls = mockHook(
		t,
		{ stdout: block() },
		{ stdout: block("Another review.") },
	);
	const harness = createHarness();
	const previous = {
		type: "custom" as const,
		customType: "other",
		data: { kept: true },
	};
	assert.deepEqual(await harness.stop({ entries: [previous] }), {
		entries: [
			previous,
			{
				type: "custom_message",
				customType: "docstale",
				content: "Review README.md.",
				display: true,
			},
		],
		continue: true,
	});
	assert.equal(await harness.stop(), undefined);
	assert.equal(calls.length, 1);
	await harness.emit("agent_start");
	await harness.emit("before_agent_start");
	await harness.emit("session_compact");
	assert.equal(await harness.stop(), undefined);
	assert.equal(calls.length, 1);
	await harness.settled();
	assert.equal((await harness.stop())?.continue, true);
	assert.equal(calls.length, 2);
});

for (const reason of ["startup", "reload", "new", "resume", "fork"]) {
	test(`${reason} uses SessionStart with the current pi session ID`, async (t) => {
		const calls = mockHook(t);
		const harness = createHarness();
		harness.setSessionId(reason);
		await harness.start(reason);
		assert.deepEqual(calls[0].payload, {
			hook_event_name: "SessionStart",
			session_id: `pi:${reason}`,
			cwd: harness.ctx.cwd,
		});
	});
}

for (const outcome of ["aborted", "error"] as const) {
	test(`${outcome} work does not run a check or request a continuation`, async (t) => {
		const calls = mockHook(t);
		assert.equal(await createHarness().stop({ outcome }), undefined);
		assert.equal(calls.length, 0);
	});
}

test("an earlier extension's continuation defers the check", async (t) => {
	const calls = mockHook(t);
	const harness = createHarness();
	assert.equal(await harness.stop({ continue: true }), undefined);
	assert.equal(calls.length, 0);
	await harness.stop();
	assert.equal(calls.length, 1);
});

test("an already aborted signal never starts a process", async (t) => {
	const calls = mockHook(t);
	const harness = createHarness();
	harness.ctx.signal = AbortSignal.abort();
	await harness.start();
	assert.equal(await harness.stop(), undefined);
	assert.equal(calls.length, 0);
	assert.deepEqual(harness.notifications, []);
});

test("cancellation while the process runs discards its response", async (t) => {
	const controller = new AbortController();
	const calls = mockHook(t, {
		stdout: block(),
		action: () => controller.abort(),
	});
	const harness = createHarness();
	harness.ctx.signal = controller.signal;
	assert.equal(await harness.stop(), undefined);
	assert.equal((calls[0].options.signal as AbortSignal).aborted, true);
	assert.deepEqual(harness.notifications, []);
});

test("shutdown aborts pending work and suppresses its error", async (t) => {
	const calls = mockHook(t);
	let callback: ExecCallback;
	t.mock.method(
		childProcess,
		"execFile",
		(
			_executable: string,
			_args: string[],
			options: ExecFileOptions,
			cb: ExecCallback,
		) => {
			callback = cb;
			assert.ok(options.signal);
			options.signal.addEventListener("abort", () =>
				callback(new Error("aborted"), "", ""),
			);
			return { stdin: new PassThrough() };
		},
	);
	const harness = createHarness();
	const result = harness.stop();
	await harness.emit("session_shutdown", { reason: "reload" });
	assert.equal(await result, undefined);
	assert.deepEqual(harness.notifications, []);
	assert.equal(calls.length, 0);
});

for (const stdout of [
	"{",
	"null",
	"[]",
	'"text"',
	'{"decision":"allow"}',
	'{"decision":"block"}',
	'{"decision":"block","reason":1}',
	block(" "),
]) {
	test(`malformed Stop output becomes one continuation: ${stdout}`, async (t) => {
		const calls = mockHook(t, { stdout });
		const harness = createHarness();
		const result = await harness.stop();
		assert.equal(result?.continue, true);
		assert.match(
			JSON.stringify(result?.entries),
			/docstale could not complete its check/,
		);
		assert.equal(await harness.stop(), undefined);
		assert.equal(calls.length, 1);
	});
}

for (const reply of [
	{ error: new Error("spawn docstale ENOENT") },
	{ error: new Error("exit 1"), stderr: "command failed" },
	{
		error: Object.assign(new Error("killed"), {
			killed: true,
			signal: "SIGKILL",
		}),
	},
	{
		error: Object.assign(new Error("too large"), {
			code: "ERR_CHILD_PROCESS_STDIO_MAXBUFFER",
			killed: true,
			signal: "SIGKILL",
		}),
	},
]) {
	test(`process failure becomes one continuation: ${reply.error.message}`, async (t) => {
		const calls = mockHook(t, reply);
		const harness = createHarness();
		const result = await harness.stop();
		assert.equal(result?.continue, true);
		assert.match(
			JSON.stringify(result?.entries),
			/docstale could not complete its check/,
		);
		if (reply.error.message === "killed")
			assert.match(JSON.stringify(result), /30-second timeout/);
		if (reply.error.message === "too large")
			assert.match(JSON.stringify(result), /output limit/);
		assert.equal(await harness.stop(), undefined);
		assert.equal(calls.length, 1);
	});
}

test("a closed stdin pipe produces a handled failure", async (t) => {
	mockHook(t);
	let signal: AbortSignal | undefined;
	t.mock.method(
		childProcess,
		"execFile",
		(_executable: string, _args: string[], options: ExecFileOptions) => {
			signal = options.signal;
			const stdin = new PassThrough();
			queueMicrotask(() => stdin.emit("error", new Error("EPIPE")));
			return { stdin };
		},
	);
	const result = await createHarness().stop();
	assert.equal(result?.continue, true);
	assert.match(JSON.stringify(result), /EPIPE/);
	assert.equal(signal?.aborted, true);
});

for (const reply of [
	{ stderr: "baseline failed" },
	{ error: new Error("missing executable") },
	{ stdout: block() },
]) {
	test("startup failures warn without starting model work", async (t) => {
		mockHook(t, reply);
		const harness = createHarness();
		assert.equal(await harness.start(), undefined);
		assert.equal(harness.notifications.length, 1);
		assert.equal(harness.notifications[0].level, "warning");
	});
}

for (const mode of ["tui", "rpc", "json", "print"] as const) {
	test(`${mode} delivers reminders without terminal-only UI`, async (t) => {
		mockHook(t, { stderr: "baseline failed" }, { stdout: block() });
		const stderr: string[] = [];
		t.mock.method(console, "error", (message: string) => stderr.push(message));
		const stdout = t.mock.method(console, "log", () => {});
		const harness = createHarness();
		harness.ctx.mode = mode;
		harness.ctx.hasUI = mode === "tui" || mode === "rpc";
		await harness.start();
		assert.equal((await harness.stop())?.continue, true);
		assert.equal(stdout.mock.callCount(), 0);
		assert.equal(harness.notifications.length, harness.ctx.hasUI ? 1 : 0);
		assert.deepEqual(stderr, harness.ctx.hasUI ? [] : ["baseline failed"]);
	});
}
