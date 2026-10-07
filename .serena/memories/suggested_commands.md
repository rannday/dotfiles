# Commands

- Windows: `.\install.ps1 --help`; `.\install.ps1 --dry-run` previews the full install. `.\install.ps1` applies it; no module selector is advertised.
- POSIX: `sh ./install.sh --help`; `sh ./install.sh --dry-run --profile desktop` (also server, wsl, minimal). Running without `--dry-run` applies it.
- Shared hooks: `python -B -m unittest discover -s agents/hooks -p 'test_*.py'`.
- Codex adapter: `python -B -m unittest discover -s confs/codex/hooks -p 'test_*.py'`; run both suites for hook integration changes.
- Serena memory-reference check: `serena memories check` from project root.
