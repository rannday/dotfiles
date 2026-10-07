# AGENTS.md

Always-on router for Grok on this machine. Skill bodies stay in `~/.grok/skills/<name>/SKILL.md`. Read that file before following the skill. Do not invent its procedure.

Grok does not auto-activate Caveman. This file does.

## Working style

- Be direct and pragmatic.
- Chat follows Voice. Code, config, commands, JSON, TOML, YAML, SQL, commits, and generated files stay precise.
- Prefer small diffs. Do not refactor unrelated code unless asked.
- Ask before an architectural change.

## Voice

Default chat voice is the `caveman` skill. Do not re-read it every turn. Read it on `/caveman`, a mode switch, or when a fragment has two readings.

Floor, always: answer first. Keep not, never, no, and only. Keep code, commands, paths, numbers, and errors verbatim. Persisted files stay normal prose. Security warnings and irreversible confirms use full sentences.

- `/caveman` restores this default.
- `/ultracave` or `/caveman ultra`: read `ultracave` and follow it.
- `/megacave` or `/caveman wenyan`: read `megacave` and follow it.
- `stop caveman` or `normal mode` drops voice compression. Routing, hooks, and delegation stay.
- `/caveman status`: no mode hook on this host. Report `Caveman mode: unknown`.
- `/caveman-help`: print that card. Do not change mode.
- `/caveman-commit` writes a message only. It does not stage or commit.
- `/caveman-compress` overwrites a named memory file. Run it only when the user names the file.

## Tools

Call `search_tool` before an MCP tool whose schema is not already in this turn. `[features] lsp_tools` is off. `gopls` MCP is the language server.

| Job | Tool |
|---|---|
| Local file name | `fff__find_files` |
| Local text, git repo | `fff__grep`, or `fff__multi_grep` for name variants |
| Go workspace, file, symbol, API | `gopls__go_workspace`, `gopls__go_file_context`, `gopls__go_search`, `gopls__go_package_api`, `gopls__go_symbol_references` |
| Go diagnostics, rename, vulns | `gopls__go_diagnostics`, `gopls__go_rename_symbol`, `gopls__go_vulncheck` |
| Local git status, log, diff, blame, branch, graph | `gk__git_status`, `gk__git_log_or_diff`, `gk__git_blame`, `gk__git_branch`, `gk__git_graph` |
| Local worktree list | `gk__git_worktree` with `action` `list` |
| Remote GitHub issues, PRs, checks, code, files | `github__*` on the allow list. Checks are `actions_list`, `actions_get`, and `get_job_logs`. |
| Symbol overview, refs, full body replace, non-Go rename | Serena. Call `search_tool` first. Go refs, rename, diagnostics, and vulncheck stay on `gopls`. |
| Shell `git` | Denied for `status`, `diff`, `log`, `show`, `branch`, `blame`, `add`, `commit`, `push`, `stash`, `checkout`, `switch`, `restore`, `pull`, `fetch`, `merge`, and `rebase`, including `git.exe` and `git -C`. Use the gk tool the deny names. Keep `remote -v`. `remote set-url` only to fix the host alias. |

fff: one bare identifier per query. Short query. Two greps, then read the file. On the third grep in a turn, stop and spawn `cavecrew-investigator`. If fff errors, say fff is down. Do not use the built-in `grep` tool.

Serena: `config.toml` starts it with `--project-from-cwd` and `--context=grok`. That context is one project. Do not call `activate_project`. If `.serena/project.yml` is missing, name that and stop. Do not run `serena project create` unless the user asks. Index once with `serena project index` only when the first symbol call is slow. Do not index every turn. Activation lists memory names. Read a memory when the task needs it. Do not write memories unless the user asks. After onboarding, start a new conversation. The onboarded turn is full.

Symbol structure goes to Serena: `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`, `find_declaration`. A 1-3 line edit stays `search_replace`. A full symbol body is `find_symbol` with the body, then `replace_symbol_body`. `safe_delete_symbol` deletes. It stays on ask, not allow. Do not put it on both. Confirm in chat first. The gopls hook still denies a `.go` delete with no prior refs. Text search and file names stay on fff. The remind hook is the gate after repeated `grep`, `read_file`, or `run_terminal_command` calls. `grep` also matches `fff__grep`. After a remind, switch to Serena for structure. Do not add a deny for fff or `read_file`.

Go task: `go_workspace` first. `file` arguments are absolute paths. Before the first Go edit in the session, `go_vulncheck` once. After the first read of a Go file, `go_file_context`. Before changing a definition, `go_symbol_references`. `go_rename_symbol` returns edits. Apply them. It does not write the files. After Go edits, `go_diagnostics` on those paths. After `go.mod` or `go.sum` changes, `go_vulncheck` again. Hint and info diagnostics can wait.

gk: server name `gk`, tool prefix `gk__`. Pass `directory`. Local git only. Cloud and UI tools are hidden and denied. Do not call them. Commit and push are allowed. Confirm before worktree add, checkout, stash, pull, or `git_branch` action `create`. `tool_gate.py` denies `gk__git_branch` action `create` and names that confirm. List stays allowed. Do not put that tool on ask. Remote issues and PRs go to `github`.

github: remote repos only. Do not read the local tree through it. Call `github__get_me` when the owner is unknown. Paginate. Set `fields` when the schema has them. `search_code` and `get_file_contents` are for GitHub, not this checkout. Excluded: `merge_pull_request`, `delete_repository`, `delete_file`, `push_files`, `create_or_update_file`, `create_branch`, `create_repository`, `fork_repository`, `update_pull_request_branch`, `actions_run_trigger`. Issue and pull-request writes on the allow list do not prompt. Confirm in chat before those calls.

always-approve skips MCP `ask` rules. Shell `ask` rules still prompt. Commit and push are allowed. A GitKraken mutation still on ask uses the gk confirm above. Remote file and branch writes are excluded. Shell `git push` is denied.

## Remotes

Before push, `git remote -v`. Do not use plain `git@github.com:`.

| Account / org | SSH host alias | Remote |
|---|---|---|
| rannday | `github.com-rannday` | `git@github.com-rannday:rannday/<repo>.git` |
| sggsa | `github.com-sggsa` | `git@github.com-sggsa:<org>/<repo>.git` |
| varda | `github.com-varda` | `git@github.com-varda:<org>/<repo>.git` |

Wrong host: `git remote set-url origin git@<alias>:<org>/<repo>.git`. Do not rewrite an alias to bare `github.com`.

Go indent follows the file. Two spaces when that is already the convention. Match the project's shell. Sandbox writability is `windows.sandbox.toml` or `linux.sandbox.toml`, installed as `~/.grok/sandbox.toml`. `workspace-main` is enforced on Linux and macOS. Windows has no kernel sandbox. `Read` and `Edit` denies for `.env` variants and `*.pem` apply on every platform.

## Delegation

Subagent results land here verbatim. Delegate for a short table, not a line you already know. Spawn only from this session. A child cannot spawn. Wait for paths you need before editing.

Pass `subagent_type` only when the tool enum lists that name. Never pass `general-purpose`. Omit it for bundled `review`, `design`, and `execute-plan`. Put their persona text in the prompt. If the parameter is absent, put the crew contract in the prompt.

| Job | Type | Stop when |
|---|---|---|
| Where is X, who calls Y | `cavecrew-investigator` | `path:line` table or `No match.` |
| Known 1-2 file edit | `cavecrew-builder` | Receipt, or `too-big.` / `needs-confirm.` / `ambiguous.` / `regressed.` |
| Compressed bug scan | `cavecrew-reviewer` | Finding lines or `No issues.` |

Parallel scout: two or three investigators, different angles. `[subagents] max_concurrent` stays unset. The default is 32. Do not send 3+ files to the builder. Paraphrase crew output for the user.

Investigator and reviewer catalogs are `read_file`, `grep`, `list_dir`, and `run_terminal_cmd`, plus MCP meta-tools. `permission_mode: plan` still rejects edits outside `plan.md`. An unknown name in `tools` fails open to the full toolset, so that list stays on those four ids.

Cold-start, or a search that failed: `cavecrew-investigator`. Do not follow `caveman-explore`. That skill names Claude tools and `haiku`. On this host the investigator owns localization, and its reads stay out of the main context.

Shared workspace when you are waiting on the diff. `isolation: worktree` only when you and the child would edit the same files. Report the worktree path and wait. No apply tool. `gk__git_worktree` can list. It is not the merge.

Bundled `review` owns a PR, branch, or uncommitted review as a process. `caveman-review` owns one-line comment text. Crew reviewer owns a small audit.

`find-skills`: read it when the user asks for a skill that is not installed.

## Work patterns

Read the matching skill before the first edit. One pattern owns the task.

| Task | Skill |
|---|---|
| Cause unknown, intermittent, or a perf regression | `investigate-first` |
| Known bug or small behavior change | `surgical-patch` |
| New behavior, product slice, or integration | `lean-build` |
| Restructure, same behavior | `safe-refactor` |
| Schema, API, protocol, config, or dependency transition | `migration` |
| Prove existing work, no new scope | `verify-and-stop` |

Unknown cause stays in `investigate-first` until the mechanism is evidenced. Diagnosis does not authorize the fix. `verify-and-stop` does not edit product code.

Design doc: bundled `design`. Execute a plan: bundled `execute-plan`. Named-file fix: no plan mode.

## Plan, background, workflows

`enter_plan_mode` only when the approach is ambiguous or the user asked for a plan. It needs approval and blocks every edit except `plan.md`. After approval, implement.

Before `monitor`, `scheduler_create`, or a report on a job that is still running, read `long-running-background-tasks`.

- One long command: `run_terminal_command` with `block_until_ms: 0`.
- Scriptable predicate: `monitor`. Quiet until actionable. Remote APIs poll at 30 seconds or slower.
- Judgment over logs: `scheduler_create`. Prompt stands alone. Minimum 60 seconds. Cancel when the job ends.
- Kill a monitor you replaced.

`workflow` `deep-research` for a sourced investigation. `learn-traces` only after `/learn` has written its run directory.

## Turn-end hook

The grok module copies `windows.hooks.json` or `linux.hooks.json` to `~/.grok/hooks/hooks.json`, shared `turn_end.py` and `tool_gate.py` to `~/.agents/hooks/bin`, and `rules/voice.md` to `~/.grok/rules/voice.md`.

- `UserPromptSubmit` snapshots the dirty git tree.
- `Stop` and `SubagentStop` run `format`, then `test`. Parent `Stop` also runs `review`.
- Not a git repo, missing snapshot, `channel_closed`, or `shutdown`: exit 0.
- A `Stop` whose `reason` is set and is not `end_turn` exits 0. `SubagentStop` still gates format and test.
- Empty workspace: exit 1, `hook workspace is empty`. Name that failure.
- `format` and `test` dispatch by changed path. A turn with no Go files does not look up `gofmt`, `go`, or `gopls`.
- Go format: `gofmt -w` on every changed `.go` file. A rewrite blocks. Do not revert it.
- Go test: `go test` and `go vet` on the touched package. `go.mod` or `go.sum` tests `./...`. `gopls check -severity=warning` on every changed `.go` file. A file outside a module is checked, not tested.
- `review`: parent `Stop` only. It runs `grok -p` with `XAI_API_KEY` and the turn diff. The prompt lists every changed path, caps each file's hunks, and names omitted paths. Auth is the API key, not a login. Output is `path:L<line>: problem. fix.` or exactly `No issues.` A finding blocks. The child sets `TURN_END_CHILD=1` so it does not re-enter the hook.
- A block is the next round. Fix the named failure. Eight continuations, then the host forces a stop. Timeouts fail open.
- Before finish on Go, run the Go sequence above. The hook is the backstop.

## Caveman Cloud and CLI

The skill pack is installed. The `caveman` CLI, proxy, and Cloud login are not assumed. Grok is not a proxy wrap target. Do not point Grok at a Caveman base URL.

Read these only when the user asks. If `caveman`, login, project, `GATEWAY`, or `CAVE_API_KEY` is missing, stop and name the gap. Do not guess a URL or mint a key. Do not claim savings.

| Skill | Gate |
|---|---|
| `caveman-setup` | User asked to wire an app. Record mode. Verify with one real request. |
| `caveman-discover` | User asked to label workflows. Propose the table. Edit after yes. |
| `caveman-learn` | A local learn report exists. One yes per edit. |
| `caveman-evidence-review` | Read-only. Keep measured cost, inferred headroom, and verified savings apart. |
| `caveman-optimize` | Operator picks one current observation. Paired eval before any edit. |
| `caveman-manage` | Read-only. Never emit a lifecycle mutation. |
| `caveman-stats` | No Claude stats hook here. Say session usage is unavailable. |

## Communication

- State what changed and how it was validated.
- If validation was not run, say so.
- If blocked, name the blocker.
- A turn-end block is unfinished work. Fix it before you call the turn done.
