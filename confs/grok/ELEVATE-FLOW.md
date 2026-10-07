# Agentic flow

Improve the coding loop: caveman skills, fff, gk, gopls, github, hooks, agents, subagents, workflows, and loops. Source is `confs/grok/`. This note is not installed. Do not install onto `~/.grok`.

A wrong tool call has to fail in `config.toml` and `hooks/tool_gate.py`. Do not add router prose and call a gate done.

## Do not build

- A hook that rewrites shell `git` into a gk call.
- A `UserPromptSubmit` hook that prepends `AGENTS.md`.
- A voice grader.
- Denies for `gk__git_*`, `fff__*`, `gopls__*`, or GitHub reads.
- A Caveman base URL on Grok.

## Caveman skills

- `caveman-explore` still names Claude `Read`, `Glob`, `Grep`, and `haiku`. Keep cold-start search on `cavecrew-investigator`. Rewrite that skill for fff, gk, and gopls only if a non-xAI model pin exists. `subagent_model_inheritance` is on, so a haiku pin does not apply.
- Audit `investigate-first`, `surgical-patch`, `lean-build`, `safe-refactor`, `migration`, and `verify-and-stop`. Each body should route fff, gk, gopls, and github the same way `AGENTS.md` does, and should not send search to `caveman-explore` or built-in `grep`.
- Pack updates go through `modules/caveman.ps1`. A present `~/.grok/skills/caveman/SKILL.md` skips the installer. Do not fork upstream skill bodies in this repo.
- Cloud skills stay gated. Read them only when the human asks. If login, project, `GATEWAY`, or `CAVE_API_KEY` is missing, stop and name the gap.

## Serena

- Server is in `config.toml`: `serena start-mcp-server --project-from-cwd --context=grok`. One project. Do not call `activate_project`.
- Missing `.serena/project.yml`: name it. Do not run `serena project create` unless the human asks.
- Index once, only when the first symbol call is slow. Do not index every turn.
- Activation lists memory names. Read one when the task needs it. Do not write memories unless the human asks. After onboarding, start a new conversation.
- Structure and refs: `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`, `find_declaration`. Call `search_tool` before the first Serena tool in a turn.
- A 1-3 line edit stays `search_replace`. A full symbol body is `find_symbol`, then `replace_symbol_body`. `safe_delete_symbol` stays on ask, not allow. Do not put it on both. Under always-approve that ask does not prompt. Confirm in chat before the call. Do not add a `tool_gate.py` deny for that confirm. The gopls hook still denies a `.go` delete with no prior refs.
- Go refs, rename, diagnostics, and vulncheck stay on `gopls`. Text search and file names stay on fff.
- `windows.hooks.json` and `linux.hooks.json` run `serena-hooks remind --client=grok` on `grep|read_file|run_terminal_command`, and `serena-hooks cleanup --client=grok` on `Stop` after review. No `SessionStart` hook. Grok ignores that stdout. The remind hook is the gate. Do not add a `tool_gate.py` deny for fff or `read_file`.

## fff

- On the third `fff__grep` or `fff__multi_grep` in a turn, stop and spawn `cavecrew-investigator`. `tool_gate.py` already nudges. The parent still has to obey. Do not add a fourth query variation.
- If fff errors, say fff is down. Do not use the built-in `grep` tool. Fall back to `rg` via `run_terminal_command` on the host shell. One bare identifier. Same short-query cap as fff.

## gk

- `gk__git_add`, `gk__git_commit`, and `gk__git_push` are allowed. Checkout, stash, pull, and worktree stay on `ask`. Under always-approve that ask does not prompt. Confirm in chat before those calls. `MCPTool` matches the tool id, not `action`, so `gk__git_branch` stays on allow and list stays allowed. `tool_gate.py` denies action `create` and names the confirm. Do not put that tool on ask. Do not deny list.
- After the next session loads source `config.toml`, confirm cloud and UI gk tools are gone from the live catalog. Deny stays if `[disabled_mcp_tools]` is ignored.
- When gk is down, shell `git diff`, `git log -p`, `git show`, and `git status` stay denied, including from `agents/cavecrew-reviewer.md`. Name the outage. Do not bypass it.

## gopls

- A `.go` edit is denied in `tool_gate.py` PreToolUse without `gopls__go_symbol_references` before the change. Stop blocks without `gopls__go_diagnostics` after. PostToolUse watches those two calls. It does not run `go_vulncheck`. A static `config.toml` deny cannot see the prior call. Do not deny `gopls__*`. Serena `.go` symbol edits, including `safe_delete_symbol`, use the same gate. `serena__rename_symbol` stays on allow. The hook denies a `.go` path and names `gopls__go_rename_symbol`. Non-go rename stays allowed. Do not remove the allow entry. `replace_content` and `replace_in_files` use it when the call can touch `.go`. A dry run does not.
- Keep vulncheck on the agent: once before the first Go edit, again after `go.mod` or `go.sum` changes. Do not add a session-start scan.
- `go_rename_symbol` returns edits. The agent applies them. Do not add a hook that writes the files.

## github

- Issue and pull-request writes do not prompt. Confirm in chat before those calls.
- After MCP reconnect, confirm the catalog still omits `merge_pull_request`, `delete_repository`, `delete_file`, `push_files`, `create_or_update_file`, `create_branch`, `create_repository`, `fork_repository`, `update_pull_request_branch`, and `actions_run_trigger`. Deny is the block if the exclude header is ignored.
- `github__get_file_contents` and `github__search_code` are denied in `tool_gate.py` when owner/repo matches a local git remote. Other remotes stay allowed. A static `config.toml` deny cannot see the checkout. Do not deny those tools. fff and gk own this checkout.

## Hooks

- Format and test dispatch by path. Go runs `gofmt`, `go test`, `go vet`, and `gopls check` on every edited Go file. Add another stack only when one is in use.
- Review is a parent `Stop` `grok -p` call with `XAI_API_KEY`. No login. `SubagentStop` runs format and test. It does not start a second model.
- After a Grok upgrade, check `/hooks` if a session-end Stop starts running the suite. The skip keys off `GROK_HOOK_EVENT=stop`.
- Prove one real Stop on a dirty Go tree after the human asks to install. Unit tests in `confs/grok/hooks` are not that proof.
- A turn-end block is the next round. Fix the named failure. Do not loop on the same block. Eight continuations, then the host forces a stop.

## Agents and subagents

- Open `/config-agents` and confirm investigator and reviewer tool ids are `read_file`, `grep`, `list_dir`, and `run_terminal_cmd`. An unknown name fails open to the full toolset. Do not add names until that check.
- Builder stays at one or two files. 3 or more is `too-big.` Do not give it an explore step.
- Leave `[subagents] max_concurrent` unset. A scout is two or three investigators with different angles, spawned by the parent. A child cannot spawn.
- `isolation: worktree` only when parent and child would edit the same files. `gk__git_worktree` list is not the merge.
- Split review jobs. Bundled `review` owns a PR or branch. `caveman-review` owns one-line comment text. Crew reviewer owns a small audit. Do not run all three on the same diff.

## Workflows and loops

- Do not add a project workflow that restates the crew table. `deep-research` stays for a sourced investigation. `learn-traces` stays behind `/learn`.
- A new workflow needs a repeated loop that skills and hooks do not already close. Write it only after that loop shows up in a session.
- Long work stays on the existing split: `block_until_ms: 0` for one command, `monitor` for a scriptable predicate, `scheduler_create` for judgment over logs. Read `long-running-background-tasks` before starting one. Cancel the scheduler when the job ends. Kill a monitor you replaced.
- Leave auto-compact at 85% and compaction mode at the default. Try `features.compaction_mode = "segments"` and `features.compaction_detail = "balanced"` only after a long Go session loses file contents.
