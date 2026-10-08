# Workflow details

Read only the section needed for Go, WSL tests, hooks, or a skills audit.

## Go

`go_workspace` first; `go_file_context` after reading a Go file. Before the first Go edit, `go_vulncheck` once. Read `go_symbol_references` before changing a definition; use gopls rename and apply its returned edits. New files need no references to nonexistent symbols. After edits, `go_diagnostics` on changed paths; after module changes, rerun vulncheck. Match existing indentation and test conventions.

## WSL tests on Windows

Keep `workspace-write`, the elevated Windows sandbox, `on-request`, and `auto_review`. WSL can fail inside that sandbox with `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`; use a reviewed `require_escalated` execution for authorized Linux/POSIX tests. Keep native PowerShell tests on Windows. Do not install packages or change WSL/OS settings as part of testing.

Use `wsl.exe --distribution Debian --cd <absolute-linux-workdir> --exec <executable> <arguments>`. Select the workdir explicitly, such as `/mnt/c/Users/rannd/Projects/dotfiles`; do not rely on the default distro or cwd. Prefer explicit executables; when a shell is needed, use `/bin/bash --noprofile --norc -c <script>` and inspect the complete script, called test files, arguments, and side effects before execution. Review the complete command for each escalation; omit reusable `prefix_rule` approvals. A WSL prompt rule requests review, not a test-only security boundary. WSL runs outside the Windows sandbox; hooks are limited workflow guards.

Installer tests must use a fresh `mktemp -d` fixture under `/tmp` in Debian, with a temporary checkout/source copy and explicit fixture destinations. Set `HOME`, `USERPROFILE`, and XDG config/data/cache/state paths inside the fixture; start the test process with `env -i` and only needed variables, including `PATH`. Do not source real shell profiles, use the real HOME, inherit credentials, or read/write user configuration. Verify the fixture's resolved path before cleanup and confine cleanup to it. Review installers and subprocesses for hard-coded home/config paths; setting HOME alone is insufficient. If isolation cannot be established, stop that test.

Run `codex execpolicy check` against the tracked Windows rule set before scoped deployment. Check WSL invocations request review and existing forbidden decisions remain forbidden. Only when deployment is explicitly authorized and source checks pass, sync changed runtime files through `Install-UserFile` from `lib/core.ps1`, as used by `modules/codex.ps1`; do not invoke the whole installer. Reload Codex for rule/instruction changes and review hook trust through `/hooks` when required.

## Hooks and finish

Hook source and tests: `agents/hooks/`; install shared scripts and the Codex adapter to `~/.agents/hooks/bin`. Review/trust `~/.codex/hooks.json` through `/hooks`.

Codex PreToolUse checks protected paths and unsafe recursive Windows deletion. PostToolUse keeps Desktop Commander process metadata needed for interactive shell checks. Codex does not snapshot turns, run Stop validation, or invoke a review model.

Run formatting, targeted tests, and diagnostics explicitly for changed code before finishing. Keep formatter rewrites and inspect them. For Go, test/vet touched packages, test `./...` for module changes, and run diagnostics. Other stacks need their own checks. Report skipped checks.

Grok registers snapshots, formatting, and tests. Antigravity implements these checks, but no shipped registration or installer enables them. Grok review lives in `grok_review.py`; no shipped hook registration invokes it. Hooks are limited guards: dynamic shell expressions, indirect paths, and unregistered tool forms may evade static checks. Native sandbox and approval boundaries remain necessary.

Retained state: Codex session-scoped `desktop-process-shells.json` records interactive dialects until process kill; unknown or malformed entries fall back to conservative checks. Grok keeps turn snapshots. If invoked, Antigravity also writes snapshots, a session cursor, a same-diff test cache, and a bounded continuation record. These temporary files have no automatic expiry. Retired Codex snapshots, continuations, review caches, Go bookkeeping, and search counters are no longer written; old runtime files are left untouched.

AGENTS.md owns routing, documentation lookup, delegation mappings, and completion reporting.

## Skills audit

The installed Caveman/workflow skill definitions were reviewed without edits; inventory depends on the installed version.

- Shared Caveman skills come from external `JuliusBrussee/caveman` via `modules/caveman.ps1` and `modules/caveman.sh`. Codex mappings in AGENTS.md override conflicting shared instructions without changing other clients.
- `caveman-help` advertises a ~46% input reduction without a local comparison. Do not repeat it as a result.
- `caveman-compress` relies on a Python runner that calls Claude. Check prerequisites for a named target.
- `lean-build`'s “Native Core” means the repository's actual architecture; it does not authorize a new framework.

For a comparison, keep task, checkout, model, permissions, and MCP catalog constant. Record parent plus child input/output, cached input separately, tool-output volume, retries, elapsed time, and acceptance. File bytes are not billed tokens.
