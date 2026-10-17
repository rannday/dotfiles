# Workflow details

Read only the section needed for tool routing, Go, WSL tests, hooks, or a skills audit.

## Tool routing

Follow AGENTS.md's routing policy. Discover the actual MCP tool catalog first; these Filesystem MCP names and arguments were verified with the connected server and its official [tool documentation](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem#tools). Examples use `/absolute/project` as a placeholder; on Windows use an absolute path such as `C:/Users/rannd/Projects/dotfiles`. Paths must stay within allowed roots and the authorized workspace.

- Known file: `read_text_file({path: "/absolute/project/src/main.py", head: 80})`; multiple known files: `read_multiple_files({paths: [...]})`.
- Targeted edit: `edit_file({path: "/absolute/project/src/main.py", edits: [{oldText: "timeout = 10", newText: "timeout = 20"}], dryRun: true})`. Inspect the returned diff, then apply with `dryRun: false`. It supports targeted and multiline replacements; avoid full-file rewrites.
- New file: `write_file({path: "/absolute/project/notes.txt", content: "Notes\n"})`. Full replacement of an existing file must be intentional.
- Semantic change: use Serena's symbol/ref tools and suitable symbol-scoped editing; use gopls for Go renames and supported language-aware work.
- Fallback: if `edit_file` is unavailable or cannot safely express the change, state that limitation and use native `apply_patch`. Do not replace a missing tool with an ad hoc shell/Python editing script.
- Execution: run project build/test commands through shell, such as `go test ./...` or `python -m unittest discover -s agents/hooks`. Python tests, existing scripts, Python tooling, and required data processing remain valid Python work.

Filesystem MCP also exposes `create_directory({path})`, `move_file({source, destination})`, `list_directory({path})`, `search_files({path, pattern, excludePatterns})`, and `get_file_info({path})`. Prefer fff for bounded repository discovery/text search. Use actual schemas; optional arguments may be omitted. No deletion tool is exposed by this server; use an authorized, narrowly bounded native fallback when needed.

Both platform configs approve read-only tools and explicitly prompt for `edit_file`, `write_file`, `create_directory`, and `move_file`; unknown tools retain `prompt`. An edit preview also prompts because approval is per tool, not per `dryRun` argument. These settings use Codex's [MCP approval fields](https://developers.openai.com/codex/config-reference/). Approval does not exempt protected paths or widen workspace permissions. PreToolUse still covers `mcp__filesystem__.*` and checks path arguments, including both move endpoints. Executable heredocs remain subject to existing fail-closed checks.

After an authorized installation, start a fresh Codex session on each platform. Check `/mcp`, `list_allowed_directories`, and hook trust through `/hooks`. In an authorized project under those roots, use a disposable fixture: read without approval; deny each `write_file`, `edit_file` (including `dryRun`), `create_directory`, and `move_file` request and confirm unchanged content/paths; then grant each request and verify the expected result. A preview must leave content unchanged. Check both move endpoints. Request protected `.env`/PEM targets only as synthetic hook events, never against real secrets; verify hook denial independently of approval. Repeat a small builder/investigator/reviewer task to check inherited routing and approval. Clean only the fixture. TOML parsing and direct MCP calls prove neither fresh-session approval prompts nor denial enforcement; record these checks as UNVERIFIED until exercised interactively.

## Go

`go_workspace` first; `go_file_context` after reading a Go file. Before the first Go edit, `go_vulncheck` once. Read `go_symbol_references` before changing a definition; use gopls rename and apply its returned edits. New files need no references to nonexistent symbols. After edits, `go_diagnostics` on changed paths; after module changes, rerun vulncheck. Match existing indentation and test conventions.

## WSL tests on Windows

Keep `workspace-write`, the elevated Windows sandbox, `on-request`, and `auto_review`. WSL can fail inside that sandbox with `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`; use a reviewed `require_escalated` execution for authorized Linux/POSIX tests. Keep native PowerShell tests on Windows. Do not install packages or change WSL/OS settings as part of testing.

Use `wsl.exe --distribution Debian --cd <absolute-linux-workdir> --exec <executable> <arguments>`. Select the workdir explicitly, such as `/mnt/c/Users/rannd/Projects/dotfiles`; do not rely on the default distro or cwd. Prefer explicit executables; when a shell is needed, use `/bin/bash --noprofile --norc -c <script>` and inspect the complete script, called test files, arguments, and side effects before execution. Review the complete command for each escalation; omit reusable `prefix_rule` approvals. A WSL prompt rule requests review, not a test-only security boundary. WSL runs outside the Windows sandbox; hooks are limited workflow guards.

Installer tests must use a fresh `mktemp -d` fixture under `/tmp` in Debian, with a temporary checkout/source copy and explicit fixture destinations. Set `HOME`, `USERPROFILE`, and XDG config/data/cache/state paths inside the fixture; start the test process with `env -i` and only needed variables, including `PATH`. Do not source real shell profiles, use the real HOME, inherit credentials, or read/write user configuration. Verify the fixture's resolved path before cleanup and confine cleanup to it. Review installers and subprocesses for hard-coded home/config paths; setting HOME alone is insufficient. If isolation cannot be established, stop that test.

Run `codex execpolicy check` against the tracked Windows rule set before deployment. Check WSL invocations request review and existing forbidden decisions remain forbidden. Only deploy when explicitly authorized and source checks pass; use the existing platform installer described below. Reload Codex for rule/instruction changes and review hook trust through `/hooks` when required.

## Hooks and finish

Hook source and tests: `agents/hooks/`; install shared scripts and the Codex adapter to `~/.agents/hooks/bin`. Review/trust `~/.codex/hooks.json` through `/hooks`.

Deploy hook changes with the existing installer from the checkout: `sh ./install.sh` on Linux, `sh ./install.sh --profile wsl` in Debian WSL, or `.\install.ps1` on Windows. These invoke `modules/codex.sh` or `modules/codex.ps1`, copying `agents/hooks/{tool_gate,codex_hooks}.py` and the platform hook/config files into the user home. Copies overwrite local edits without backup; they are not symlinks. Repeated copies use the same destinations. The installers also run their other setup modules. No separate hook installer is needed. Restart Codex after the installer refreshes configuration; review hook trust through `/hooks`. The hook script itself starts a fresh Python process for each event.

Protected shell checks use token/path candidates and wildcard-language overlap, not substring matches. PATH list splitting requires a literal assignment name in a supported top-level statement: leading POSIX `PATH=...` assignments or a standalone PowerShell `$env:PATH=...` assignment (`:` and `;` separators respectively). Empty entries remain empty candidates. Redirection operands, positional arguments, nested expressions/substitution bodies, quoted assignment names, and uncertain contexts retain conservative whole-path checks; a colon or semicolon can belong to a filename. Commands containing comment or here-document markers (`#`, `<<`), carriage returns, or PowerShell here-string markers receive no PATH exemption. Assignment names after parentheses, braces, or backticks also receive no exemption: the bounded lexer cannot establish their expression boundaries (even quoted markers are conservative). Pipeline/conditional-operator boundaries and unrecognized assignment forms (including spaced PowerShell assignments and cmd.exe PATH lists) also receive no PATH exemption and may produce false positives. Executed substitution bodies and protected PATH entries remain checked. Other assignment handling is unchanged. This is bounded static inspection, not full shell evaluation; wholly indirect paths and runtime expansion results remain existing limitations. Partial filename expansions that could select protected names remain denied. Protected rules cover the configured `.env` names and PEM files, not every credential/private-key filename.

Executable-input regression: a quoted `python3 - <<'PY'` heredoc editing ordinary Python fixtures was denied even without any protected filename. `shell_secret_paths` deliberately rejects unclassified heredocs; `tool_policy` incorrectly described every rejection as a detected secret path. Parser-limit rejections now report unresolved executable input or filesystem targets. A quoted delimiter prevents shell expansion, but does not make Python input inert. Computed Python paths and arbitrary interpreter code remain unsupported and denied; the minimal allow-case test is an explicit expected failure, not completed acceptance. Regression tests also cover nested parser-limit diagnostics, ordinary fixture/documentation writes with secret filename examples, and protected argument/redirection targets. Literal documentation write forms remain supported; this change grants no new command exemptions. General comments and quoted data arguments still lack full semantic classification.

Codex PreToolUse checks protected paths and unsafe recursive Windows deletion. No Codex PostToolUse registration is needed. Codex does not snapshot turns, run Stop validation, or invoke a review model.

Run formatting, targeted tests, and diagnostics explicitly for changed code before finishing. Keep formatter rewrites and inspect them. For Go, test/vet touched packages, test `./...` for module changes, and run diagnostics. Other stacks need their own checks. Report skipped checks.

Grok registers snapshots, formatting, and tests. Antigravity implements these checks, but no shipped registration or installer enables them. Grok review lives in `grok_review.py`; no shipped hook registration invokes it. Hooks are limited guards: dynamic shell expressions, indirect paths, and unregistered tool forms may evade static checks. Native sandbox and approval boundaries remain necessary.

Retained state: Codex no longer records interactive process metadata; old runtime files are left untouched. Grok keeps turn snapshots. If invoked, Antigravity also writes snapshots, a session cursor, a same-diff test cache, and a bounded continuation record. These temporary files have no automatic expiry. Retired Codex snapshots, continuations, review caches, Go bookkeeping, and search counters are no longer written; old runtime files are left untouched.

AGENTS.md owns routing, documentation lookup, delegation mappings, and completion reporting.

## Skills audit

The installed Caveman/workflow skill definitions were reviewed without edits; inventory depends on the installed version.

- Shared Caveman skills come from external `JuliusBrussee/caveman` via `modules/caveman.ps1` and `modules/caveman.sh`. Codex mappings in AGENTS.md override conflicting shared instructions without changing other clients.
- `caveman-help` advertises a ~46% input reduction without a local comparison. Do not repeat it as a result.
- `caveman-compress` relies on a Python runner that calls Claude. Check prerequisites for a named target.
- `lean-build`'s “Native Core” means the repository's actual architecture; it does not authorize a new framework.

For a comparison, keep task, checkout, model, permissions, and MCP catalog constant. Record parent plus child input/output, cached input separately, tool-output volume, retries, elapsed time, and acceptance. File bytes are not billed tokens.
