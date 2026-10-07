This repo is personal dotfiles. Keep changes narrow.

## What matters

- Do not edit `README.md` unless the user says so.
- Do not broaden scope. Touch only files tied to the request.
- Preserve existing layout, naming, and platform split.
- Keep docs terse. No generic public-repo prose.

## Repo shape

- `install.sh` and `install.ps1` are entrypoints.
- `modules/` holds shell and PowerShell install modules.
- `confs/` is the shipped source. Install copies it outward.
- `confs/grok/` is the Grok home source (`~/.grok`).
- `confs/codex/` is the Codex home source (`~/.codex`), including `rules/`.
- `agents/hooks/` holds shared Python hook source and tests. Grok and Codex modules install shared scripts to `~/.agents/hooks/bin`.
- `confs/codex/hooks/` holds the Codex adapter and tests. The adapter installs to `~/.codex/hooks/bin`.
- Do not treat a repo `.grok/` or `.codex/` directory as source. Install does not write those.

## Agent work

- Use fff search tools first in this repo.
- Prefer existing repo config over guessing defaults.
- If changing Grok behavior, check `confs/grok/config.toml`.
- If changing Codex behavior, check `confs/codex/linux.config.toml` and `confs/codex/windows.config.toml`.
- Do not invent extra project layout.

## Validation

- State exact files changed.
- Say if validation skipped.
- If a change is platform-specific, call out which side was checked.
