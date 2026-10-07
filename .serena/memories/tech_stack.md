# Stack

- POSIX shell (`#!/bin/sh`) and PowerShell installation modules; Python standard-library hook policies/adapters and unittest suites. TOML agent configuration, JSON hook entrypoints, Codex `.rules` files.
- Windows entrypoint loads winget helpers; shell entrypoint detects OS/package backend before running modules. Installers can install packages/CLIs: execution has effects beyond copying config.
- Modules are sourced/dot-sourced by helpers; entrypoint scripts must be executed directly. Keep shared policy agent-independent and platform installation in paired `.sh`/`.ps1` modules.
