# Project map

- Personal dotfiles; `confs/` is shipped source, `modules/` installs outward through `install.ps1` or `install.sh` and `lib/` helpers. Repo `.codex/`/`.grok/` are not install sources.
- Shared Python hooks/tests: `agents/hooks/`; shared runtime: `~/.agents/hooks/bin`. Codex adapter/tests: `confs/codex/hooks/`; adapter runtime: `~/.codex/hooks/bin`. Grok hooks JSON installs under `~/.grok/hooks/`; Codex hooks JSON under `~/.codex/`.
- Preserve platform split, unrelated work, layout and naming. README edits need explicit request. Consult current AGENTS.md before acting.
- Runtime/tool dependencies: `mem:tech_stack`. Editing conventions and tool routing: `mem:conventions`. Installer usage: `mem:suggested_commands`. Completion checks: `mem:task_completion`.
