# Antigravity

## Work

- Answer first. Read `~/.agents/skills/caveman/SKILL.md` once per session when available. Keep files normally formatted; Ultra/Wenyan only on request.
- Keep edits within the task. Preserve layout and unrelated work. Inspect the worktree first. Generated files need an explicit request.
- Honor authorization already given. Diagnose unknown failures, then continue an authorized fix. Ask only for missing scope or new permission.
- No commit, push, history rewrite, discarded work, dependency install, or OS change without authorization.
- Protected `.env` variants and PEM paths stay unread and unedited. Request a redacted example when needed.

## Tools

| Work | Route |
|---|---|
| Names and text | fff; short query, bounded matches |
| Symbol structure or whole-body edits | Serena; tiny edits use the normal editor |
| Go workspace, context, refs, rename, diagnostics, vulns | gopls; absolute paths |
| Local Git | gk; pass `directory` |
| Remote issues, PRs, checks | GitHub; paginate, select fields |
| Library docs / browser | Context7 / Playwright |

Discover schemas as needed. Search briefly, then read owning ranges; avoid whole-file dumps. If a required server is unavailable, name it. fff may fall back to `rg`; local Git stays on gk. Shell Git is blocked except remote inspection/fix and operations without a gk route allowed by the execution rules.

Serena starts from cwd with `--context=antigravity`. Do not activate another project. Report missing `.serena/project.yml`; creation/onboarding and memory writes need authorization. `.go` renames stay on gopls.

GitHub reads must not duplicate this checkout. Confirm unauthorized remote writes; exclusions remain in config. gk branch creation, checkout, stash, pull, and worktree changes need authorization; listing does not authorize mutation.

Before push, `git remote -v`. Use SSH aliases: `github.com-rannday`, `github.com-sggsa`, `github.com-varda`. Fix a wrong host with `git remote set-url`; never replace an alias with bare `github.com`.

For Go changes, follow the Go sequence: `gopls__go_workspace` first, `go_symbol_references` before changing a definition, `go_diagnostics` after edits.

## Delegation and skills

- Broad localization or an unsuccessful bounded search: `cavecrew-investigator`. Exact-file work and known facts stay inline.
- Known one/two-file edit: `cavecrew-builder`. Larger work stays with the parent. Assign disjoint file ownership; children never delegate.
- Requested bug scan: `cavecrew-reviewer`. Return evidence. Native review owns a PR/branch process; `caveman-review` only controls finding text.
- Use a named agent only if the spawn tool supports it; otherwise put its compact contract in the prompt.
- Choose one primary workflow: `investigate-first`, `surgical-patch`, `lean-build`, `safe-refactor`, `migration`, or `verify-and-stop`. Read once; switch at a phase change.
- Route `caveman-explore` to the native investigator. `caveman-commit` writes only the message; `caveman-compress` needs a named target and a working runner.
- Cloud/learn/setup/optimization skills load only for an actual request and available CLI/account/report prerequisites. Do not wrap Antigravity in a proxy or invent credentials.

## Finish

Lifecycle hooks load from `~/.gemini/config/hooks.json`. Fix hook blocks; three identical failures halt with validation incomplete.

State changed files, checks, skipped validation, and platform limits. Re-read is not a test. Stop when acceptance passes.
