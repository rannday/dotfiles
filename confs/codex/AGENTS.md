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
| Library docs / browser | Context7 / Playwright |

Discover tools by exact MCP server prefix and relevant tool names; bound discovery output and inspect only needed schemas. Avoid broad searches across tool descriptions for words such as "search" or "read". Use fff for discovery and text search, then Desktop Commander for relevant bounded file ranges (`offset` is zero-based; `length` limits lines). Desktop Commander is the normal reader for known files, including skills, configuration, documentation, and files outside the active project. Avoid whole-file dumps. If a required server or tool is unavailable, name it before falling back: fff to `rg`, Desktop Commander to bounded native/shell reads. Routing is a workflow preference; no recorded failure is required for fallback. Local Git stays on gk. Shell Git is blocked except remote inspection/fix and operations without a gk route allowed by the execution rules.

Use Serena for symbols, declarations, references, implementations, code structure, and semantic refactors. Its `read_file` remains available for semantic work; generic reads belong to Desktop Commander. Prefer gopls for Go semantic operations where it provides the capability. Prefer Codex native editing for ordinary textual edits and native shell for builds, tests, and other command execution. This does not make shell the default for file discovery, text search, or generic file inspection. Use Desktop Commander process execution for host-level situations with a concrete advantage. Mutating host actions require authorization.

Serena starts from cwd with the custom `~/.codex/serena-context.yml` semantic context. Do not activate another project. Report missing `.serena/project.yml`; creation/onboarding and memory writes need authorization. `.go` renames stay on gopls.

Use Context7 for current library, framework, SDK, API, CLI, and cloud-service documentation. Resolve the library ID first, then query one concept at a time. Use Playwright for browser work. Report connection failures before falling back.

GitHub reads must not duplicate this checkout. Confirm unauthorized remote writes; exclusions remain in config. gk branch creation, checkout, stash, pull, and worktree changes need authorization; listing does not authorize mutation.

Before push, `git remote -v`. Use SSH aliases: `github.com-rannday`, `github.com-sggsa`, `github.com-varda`. Fix a wrong host with `git remote set-url`; never replace an alias with bare `github.com`.

For Go changes, read the Go sequence in `~/.codex/workflow.md` once.

For Linux/POSIX tests on Windows, read the WSL tests section in `~/.codex/workflow.md`. Use reviewed `require_escalated` calls with explicit Debian distro and workdir; keep PowerShell tests native.

## Delegation and skills

- Broad localization or an unsuccessful bounded search: `cavecrew-investigator`. Exact-file work and known facts stay inline.
- Known one/two-file edit: `cavecrew-builder`. Larger work stays with the parent. Assign disjoint file ownership; children never delegate.
- Requested bug scan: `cavecrew-reviewer`. Return evidence. Native review owns a PR/branch process; `caveman-review` only controls finding text.
- Use a named agent only if the spawn tool supports it; otherwise put its compact contract in the prompt.
- Choose one primary workflow: `investigate-first`, `surgical-patch`, `lean-build`, `safe-refactor`, `migration`, or `verify-and-stop`. Read once; switch at a phase change.
- Route `caveman-explore` to the native investigator. `caveman-commit` writes only the message; `caveman-compress` needs a named target and a working runner.
- Cloud/learn/setup/optimization skills load only for an actual request and available CLI/account/report prerequisites. Do not wrap Codex in a proxy or invent credentials.
- Short returns reduce parent context, not proven total cost. Measure parent plus child usage and acceptance; do not claim unmeasured savings.

## Finish

Read `~/.codex/workflow.md` for Go edits, hook failures, or measurement details. Codex hooks load from `~/.codex/hooks.json`; review/trust them through `/hooks`.

No-change turns skip model review. Successful checks reuse the same turn diff; new edits invalidate them. Automatic review is an extra model call, not proven savings. Fix hook blocks; three identical failures halt with validation incomplete.

State changed files, checks, skipped validation, and platform limits. Re-read is not a test. Stop when acceptance passes.

<!-- context7 -->
Use Context7 MCP to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service — even well-known ones like React, Next.js, Prisma, Express, Tailwind, Django, or Spring Boot. This includes API syntax, configuration, version migration, library-specific debugging, setup instructions, and CLI tool usage. Use even when you think you know the answer — your training data may not reflect recent changes. Prefer this over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## Steps

1. Always start with `resolve-library-id` using the library name and what to look up in the library's documentation, unless the user provides an exact library ID in `/org/project` format
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better). If results don't look right, try alternate names or queries (e.g., "next.js" not "nextjs", or rephrase the question). Use version-specific IDs when the user mentions a version
3. `query-docs` with the selected library ID and what to look up in the library's documentation (not single words), scoped to a single concept. If the question spans multiple distinct concepts (e.g. routing and auth and caching), make a separate `query-docs` call per concept with the same library ID, unless the question is about how the concepts interact — combined queries dilute ranking and return shallow results for each topic
4. Answer using the fetched docs
<!-- context7 -->
