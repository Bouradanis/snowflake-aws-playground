async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  const toolArgs = JSON.parse(Buffer.concat(chunks).toString());
  const command = toolArgs.tool_input?.command || "";

  // Git is read-only for Claude in this repo. Never git add/commit/push/rm/
  // reset/checkout/merge/etc. -- the user handles all git writes themselves,
  // even when a skill template or an earlier plan step suggests otherwise.
  //
  // Allowlist a handful of definitely-read-only invocations rather than trying
  // to denylist every mutating git verb -- fail closed (block) on anything
  // ambiguous rather than fail open.
  const gitInvocations = command.match(/\bgit\s+[^\s;&|]+(?:\s+[^\s;&|]+)*/g) || [];

  const READ_ONLY_SUBCOMMANDS = new Set([
    "status", "diff", "log", "show", "blame", "ls-files", "ls-tree",
    "ls-remote", "rev-parse", "rev-list", "describe", "shortlog",
    "cat-file", "grep", "help", "--version", "version", "diff-tree",
    "count-objects", "reflog",
  ]);

  for (const invocation of gitInvocations) {
    const trimmed = invocation.trim();
    const tokens = trimmed.split(/\s+/).slice(1); // drop leading "git"
    const subcommand = tokens[0];

    if (READ_ONLY_SUBCOMMANDS.has(subcommand)) {
      continue;
    }

    // "branch" and "tag" have safe read-only forms (bare / --list / -a / -v / -r)
    // alongside destructive ones (create/delete/rename/force) -- only allow the
    // read-only forms.
    if (subcommand === "branch" || subcommand === "tag") {
      const rest = tokens.slice(1);
      const writeFlags = ["-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "-f", "--force"];
      const hasWriteFlag = rest.some((t) => writeFlags.includes(t));
      const hasPositionalArg = rest.some((t) => !t.startsWith("-"));
      if (hasWriteFlag || hasPositionalArg) {
        console.error(
          `Blocked: git is read-only for Claude in this repo -- "${trimmed}" looks like it creates/deletes/renames a ${subcommand}. The user handles all git writes.`
        );
        process.exit(2);
      }
      continue;
    }

    if (subcommand === "remote") {
      const rest = tokens.slice(1);
      const readOnlyForms = [[], ["-v"], ["show"]];
      const isReadOnly = readOnlyForms.some(
        (form) => form.length === rest.length && form.every((t, i) => t === rest[i])
      );
      if (!isReadOnly) {
        console.error(
          `Blocked: git is read-only for Claude in this repo -- "${trimmed}" looks like it modifies a remote. The user handles all git writes.`
        );
        process.exit(2);
      }
      continue;
    }

    if (subcommand === "stash") {
      const rest = tokens.slice(1);
      if (rest.length === 0 || rest[0] === "list" || rest[0] === "show") {
        continue;
      }
      console.error(
        `Blocked: git is read-only for Claude in this repo -- "${trimmed}" mutates the stash. The user handles all git writes.`
      );
      process.exit(2);
    }

    if (subcommand === "config") {
      const rest = tokens.slice(1);
      if (rest.includes("--get") || rest.includes("--list") || rest.includes("-l")) {
        continue;
      }
      console.error(
        `Blocked: git is read-only for Claude in this repo -- "${trimmed}" looks like it writes config. The user handles all git writes.`
      );
      process.exit(2);
    }

    // Anything else under `git` (add, commit, push, rm, mv, reset, checkout,
    // restore, clean, merge, rebase, cherry-pick, revert, apply, am, fetch,
    // pull, clone, init, gc, prune, submodule, worktree, filter-branch, ...)
    // is a write -- block it.
    console.error(
      `Blocked: git is read-only for Claude in this repo -- "${trimmed}" is a git write action. The user handles all committing, pushing, and other git writes themselves.`
    );
    process.exit(2);
  }
}

main();