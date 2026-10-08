# Codex

## Work

- Answer first. Read `~/.agents/skills/caveman/SKILL.md` once per session when available. Keep files normally formatted; Ultra/Wenyan only on request.
- Keep edits within the task. Preserve layout and unrelated work. Inspect the worktree first. Generated files need an explicit request.
- Honor authorization already given. Diagnose unknown failures, then continue an authorized fix. Ask only for missing scope or new permission.
- No commit, push, history rewrite, discarded work, dependency install, or OS change without authorization. Approval review does not widen task scope.
- Protected `.env` variants and PEM paths stay unread and unedited. Request a redacted example when needed.

## Tools

| Work | Route |
|---|---|
| Names and text / discovery / search | fff; short query, bounded matches |
| Generic known-file reads | Desktop Commander; bounded ranges, absolute paths |
| Host filesystem operations | Desktop Commander; mutations need authorization |
| Semantic code structure, symbols, refs, refactors | Serena |
| Go workspace, context, refs, rename, diagnostics, vulns | gopls; absolute paths |
| Local Git | gk; pass `directory` |
| Remote issues, PRs, checks | GitHub; paginate, select fields |
| OpenAI / Codex docs | openaiDeveloperDocs |
| Other library docs / browser | Context7 / Playwright |

Discover tools by exact MCP server prefix and relevant tool names; bound output and inspect only needed schemas. Avoid broad tool-description searches. Desktop Commander reads include skills, configuration, documentation, and external files; use absolute paths and bounded ranges (`offset` is zero-based; `length` limits lines). Avoid whole-file dumps. Name an unavailable required tool before using a permitted fallback: fff to bounded `rg`, Desktop Commander to bounded native/shell reads. No recorded failure is required. Fallbacks retain scope, permissions, secret protection, and execution rules. Local Git stays on gk; its absence does not permit shell Git. Merge, rebase, and restore remain user-controlled; gk has no dedicated route for them. Shell exceptions are only remote inspection/fix and other operations explicitly permitted by execution rules.

Serena's `read_file` remains available for semantic work; generic reads belong to Desktop Commander. Prefer native editing for ordinary textual edits and native shell for builds, tests, and other commands, not default discovery/search/inspection. Use Desktop Commander process execution for host-level situations with a concrete advantage. Mutating host actions require authorization.

Serena starts from cwd with the custom `~/.codex/serena-context.yml` semantic context. Do not activate another project. Report missing `.serena/project.yml`; creation/onboarding and memory writes need authorization. `.go` renames stay on gopls.

Use openaiDeveloperDocs for current OpenAI/Codex documentation: search, then fetch the relevant page. If unavailable, name it and use official OpenAI documentation. For other library, framework, SDK, API, CLI, and cloud-service docs, use Context7: `resolve-library-id` first unless an exact `/org/project` ID is supplied, then `query-docs` with a focused question per concept. Select the relevant official source/version and answer from fetched docs. If Context7 is unavailable, name it and use official library documentation. General programming, business logic, and code review alone do not require library docs. Report connection failures before fallback. Use Playwright for browser work.

GitHub reads must not duplicate this checkout. Confirm unauthorized remote writes; exclusions remain in config. gk branch creation, checkout, stash, pull, and worktree changes need authorization; listing does not authorize mutation.

Before push, `git remote -v`. Use SSH aliases: `github.com-rannday`, `github.com-sggsa`, `github.com-varda`. Fix a wrong host with `git remote set-url`; never replace an alias with bare `github.com`.

For Go changes, read the Go sequence in `~/.codex/workflow.md` once.

For Linux/POSIX tests on Windows, read the WSL tests section in `~/.codex/workflow.md`. Use reviewed `require_escalated` calls with explicit Debian distro and workdir; keep PowerShell tests native.

## Delegation and skills

- Broad localization or an unsuccessful bounded search: `cavecrew-investigator`. Exact-file work and known facts stay inline.
- Known one/two-file edit: `cavecrew-builder`. Larger work stays with the parent. Assign disjoint file ownership; children never delegate.
- Requested bug scan: `cavecrew-reviewer` owns evidence and coverage; `caveman-review` only formats findings. PR/branch actions need their own authorization.
- Use a named agent only if the spawn tool supports it; otherwise put its compact contract in the prompt.
- Choose one primary workflow: `investigate-first`, `surgical-patch`, `lean-build`, `safe-refactor`, `migration`, or `verify-and-stop`. Read once; switch at a phase change.
- In Codex, route `caveman-explore` to `cavecrew-investigator`, overriding shared skill references to Claude tools or `haiku`. Inherit the current model unless the user selects another. Other clients' skill behavior stays unchanged.
- `caveman-commit` writes only the message; `caveman-compress` needs a named target and a working runner.
- Cloud/learn/setup/optimization skills load only for an actual request and available CLI/account/report prerequisites. Do not wrap Codex in a proxy or invent credentials.
- Short returns reduce parent context, not proven total cost. Measure parent plus child usage and acceptance; do not claim unmeasured savings.

## Finish

Read `~/.codex/workflow.md` for Go edits, hook failures, or measurement details. Codex hooks load from `~/.codex/hooks.json`; review/trust them through `/hooks`.

Follow workflow.md's hook validation, cache, and retry rules. Automatic review is an extra model call, not proven savings.

State changed files, checks, skipped validation, and platform limits. Re-read is not a test. Stop when acceptance passes.
