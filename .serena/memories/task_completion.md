# Completion

- Hook changes: run both unittest commands in `mem:suggested_commands`; shared-only discovery misses relocated Codex tests.
- Shell modules: `sh -n modules/codex.sh modules/grok.sh` for these installers (Git Bash `bash -n` can verify syntax on Windows; it does not prove live Linux installation).
- PowerShell parser check: `$tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'modules/codex.ps1'),[ref]$tokens,[ref]$errors) | Out-Null; if ($errors.Count) { throw ($errors | Out-String) }`; repeat for changed PowerShell modules.
- For config changes, parse the relevant JSON/TOML and verify intended command/source/destination paths. Installer routing can be checked with mocked helpers; do not apply the full installer merely to validate a narrow change.
- Read `confs/codex/workflow.md` for hook failures, Go changes or measurement requirements. Trust/review installed Codex hooks through `/hooks`.
- Report exact changed files, task-relevant checks, skipped validation and platform limits. New edits invalidate prior diff checks. Stop after acceptance passes.
