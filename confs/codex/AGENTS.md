# Codex

## Work

- Answer first. Read `~/.agents/skills/caveman/SKILL.md` once per session when available. Keep files normally formatted; Ultra/Wenyan only on request.
- Keep edits within the task. Preserve layout and unrelated work. Generated files need an explicit request.
- Honor authorization already given. Diagnose unknown failures, then continue an authorized fix. Ask only for missing scope or new permission.
- No commit, push, history rewrite, discarded work, dependency install, or OS change without authorization. Approval review does not widen task scope.
- Real `.env` files, secret-bearing `.env` variants, and PEM paths stay unread and unedited. Public `.env.example` templates may be read and edited; never copy real secrets into them. Request a redacted example when needed.

## Tools

| Work | Preferred tool |
|---|---|
| Repository names and text / discovery / search | fff; short query, bounded matches |
| Ordinary file reads, edits, creation, moves, listings, metadata, path search | Filesystem MCP; specific operations, absolute paths |
| Semantic code structure, symbols, refs, refactors | Serena |
| Go workspace, context, refs, rename, diagnostics, vulns | gopls; absolute paths |
| Local Git | Git MCP; pass `repo_path` |
| Web page extraction | Fetch MCP; use Playwright for browser interaction |
| Remote issues, PRs, checks | GitHub; paginate, select fields |
| OpenAI / Codex docs | openaiDeveloperDocs |
| Other library docs / browser | Context7 / Playwright |

Discover tools by exact MCP server prefix and relevant tool names; bound output and inspect only needed schemas. Avoid broad tool-description searches. Filesystem MCP is limited to configured user-home roots; use absolute paths and bounded reads. Avoid whole-file dumps. Real `.env` files, secret-bearing `.env` variants, and PEM paths stay unread and unedited. Public `.env.example` templates may be read and edited; never copy real secrets into them. If a preferred tool is unavailable, name it and use a bounded native alternative. Tool choice does not widen scope, permissions, or secret access. Use Git MCP with an explicit `repo_path` for local repository status, diffs, logs, and branches. Git mutations, merge, rebase, and restore require user authorization. Fetch MCP extracts web pages as Markdown; it can reach local/internal IP addresses, so use it only for intended public URLs.

Filesystem MCP is the default for ordinary filesystem work, including source-file edits. Use the most specific available operation: `read_text_file` for known files, `read_multiple_files` for multiple known files, `edit_file` for targeted replacements, `write_file` for new files or intentional full replacements, `create_directory`, `move_file` for moves/renames, `list_directory`, `get_file_info`, and `search_files` for filesystem path searches. Keep fff first for bounded repository discovery and text search. Do not replace a whole existing file when a targeted edit suffices. Preview `edit_file` with `dryRun` when useful; discover actual schemas rather than assuming tool availability. Use absolute paths within configured roots and authorized workspace boundaries. Read approvals do not permit protected-file access; writes, directory creation, and moves prompt, including edit previews under the per-tool policy.

Prefer Serena for symbol navigation, references, implementations, code structure, semantic refactoring, and suitable symbol-scoped changes. Serena's `read_file` remains available for semantic work; routine file operations belong to Filesystem MCP. Prefer language servers for supported diagnostics, references, renames, and refactors; do not substitute blind text replacement when semantic correctness matters.

Native patch/edit tools are fallbacks when Filesystem MCP is unavailable, lacks an operation, cannot safely represent the edit, or a native patch is materially safer or more precise. Name the unavailable tool or explain the relevant limitation before falling back; do not silently switch to shell-generated editing scripts.

Use shell for builds, tests, compilers, linters, formatters, existing project scripts, and legitimate CLI execution. Do not default to shell reads, redirection, `sed`, `awk`, `perl`, or similar source edits when Filesystem MCP can perform the operation. Python remains appropriate for Python tests, existing scripts, Python tooling, data processing, and operations that require Python. Do not generate ad hoc Python scripts or executable heredocs such as `python3 - <<'PY'` merely to edit ordinary source files. Tool routing never bypasses approval, sandbox, workspace, or protected-file rules. Mutating host actions require authorization.

Serena starts from cwd with the custom `~/.codex/serena-context.yml` semantic context. Do not activate another project. Report missing `.serena/project.yml`; creation/onboarding and memory writes need authorization. `.go` renames stay on gopls.

Use openaiDeveloperDocs for current OpenAI/Codex documentation: search, then fetch the relevant page. If unavailable, name it and use official OpenAI documentation. For other library, framework, SDK, API, CLI, and cloud-service docs, use Context7: `resolve-library-id` first unless an exact `/org/project` ID is supplied, then `query-docs` with a focused question per concept. Select the relevant official source/version and answer from fetched docs. If Context7 is unavailable, name it and use official library documentation. General programming, business logic, and code review alone do not require library docs. Report connection failures before fallback. Use Playwright for browser work.

GitHub reads must not duplicate this checkout. Confirm unauthorized remote writes; exclusions remain in config. Git MCP branch creation, checkout, stash, pull, and worktree changes need authorization; listing does not authorize mutation.

Verify Git MCP capabilities before choosing a tool. Use native Git for unsupported operations or options: root/HEAD discovery, path-scoped history, blame, pickaxe, bisect, and worktree inspection. Name the missing capability; keep native approval, sandbox, and protected-path checks. Bisect needs a reliable reproducer and authorization for its repository changes; fetch also needs authorization.

Before push, `git remote -v`. Use SSH aliases: `github.com-rannday`, `github.com-sggsa`, `github.com-varda`. Fix a wrong host with `git remote set-url`; never replace an alias with bare `github.com`.

For Go changes, read the Go sequence in `~/.codex/workflow.md` once.

For Linux/POSIX tests on Windows, read the WSL tests section in `~/.codex/workflow.md`. Use reviewed `require_escalated` calls with explicit Debian distro and workdir; keep PowerShell tests native.

## Git task lifecycle

- At task start, record repository root, branch (or detached HEAD), HEAD, staged/unstaged diffs, and untracked paths. Inspect relevant untracked content safely. Keep this baseline in task context; preserve pre-existing work without staging, stashing, or snapshots. Reuse it unless the repository or task changes; reconcile concurrent edits.
- Before editing regressions, unfamiliar behavior, contracts, or potentially breaking changes, investigate bounded relevant history. Read the Git section of `~/.codex/workflow.md` for technique and policy limits. History is evidence; verify present behavior. Skip history for trivial changes.
- Before finishing, inspect staged/unstaged diffs and relevant untracked files against the original baseline, separating pre-existing work from task edits. Check unrelated changes, unexpected deletions, and regressions. Validate explicitly; never infer a clean worktree or passing tests.

## Delegation and skills

- Consider delegation for broad localization or an unsuccessful bounded search: `cavecrew-investigator`. Exact-file work and known facts stay inline.
- Consider delegation for a known one/two-file edit: `cavecrew-builder`. Larger work stays with the parent. Assign disjoint file ownership and pass the relevant baseline/history; children never delegate. The parent owns broader history and final integration verification.
- Requested bug scan: `cavecrew-reviewer` owns evidence and coverage; `caveman-review` only formats findings. PR/branch actions need their own authorization.
- Use a named agent only if the spawn tool supports it; otherwise put its compact contract in the prompt.
- Choose one primary workflow: `investigate-first`, `surgical-patch`, `lean-build`, `safe-refactor`, `migration`, or `verify-and-stop`. Read only the selected skill once; load supporting sections when needed. Switch at a phase change.
- In Codex, route `caveman-explore` to `cavecrew-investigator`, overriding shared skill references to Claude tools or `haiku`. Inherit the current model unless the user selects another. Other clients' skill behavior stays unchanged.
- `caveman-commit` writes only the message; `caveman-compress` needs a named target and a working runner.
- Cloud/learn/setup/optimization skills load only for an actual request and available CLI/account/report prerequisites. Do not wrap Codex in a proxy or invent credentials.
- Short returns reduce parent context, not proven total cost. Measure parent plus child usage and acceptance; do not claim unmeasured savings.
- For parallel tasks needing independent branches, builds, or overlapping files, consider isolated worktrees; see workflow.md. Preserve configured concurrency limits. Creation/removal, branch changes, and commits each need authorization; never provision them automatically.

## Finish

Read `~/.codex/workflow.md` for Go edits, hook failures, or measurement details. Codex hooks load from `~/.codex/hooks.json`; review/trust them through `/hooks`.

Run task-relevant formatting, tests, and diagnostics explicitly before finishing. Hooks enforce narrow safety checks; they do not establish completion.

State changed files, checks, skipped validation, and platform limits. Re-read is not a test. Stop when acceptance passes.
