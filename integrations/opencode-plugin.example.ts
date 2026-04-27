type StructuredHookOutput = {
  decision?: string;
  prompt?: string;
  reason?: string;
};

function getHookErrorMessage(
  stdout: string,
  stderr: string,
  exitCode: number,
): string {
  if (stdout) {
    try {
      const parsed = JSON.parse(stdout) as StructuredHookOutput;
      if (parsed.decision === "block") {
        return parsed.reason ?? parsed.prompt ?? stdout;
      }
    } catch {
      return stdout;
    }

    return stdout;
  }

  if (stderr) {
    return stderr;
  }

  return `doc-sync hook failed with exit code ${exitCode}`;
}

export const DocSyncHook = async ({
  $,
  worktree,
}: {
  $: any;
  worktree: string;
}) => {
  return {
    event: async ({ event }: { event: { type: string } }) => {
      if (event.type !== "session.idle") return;

      const shell = $.cwd(worktree).env({ CLAUDE_PROJECT_DIR: worktree });
      const result =
        await shell`bash ${worktree}/tools/doc-sync/hook.sh --event session.idle`
          .quiet()
          .nothrow();

      if (result.exitCode !== 0) {
        throw new Error(
          getHookErrorMessage(
            result.text().trim(),
            result.stderr.toString().trim(),
            result.exitCode,
          ),
        );
      }
    },
  };
};
