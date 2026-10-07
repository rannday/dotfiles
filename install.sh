#!/bin/sh
set -eu

main() {
  BASE_DIR=$(
    unset CDPATH
    cd -- "$(dirname -- "$0")" && pwd -P
  )

  LIB_DIR=$BASE_DIR/lib
  MODULE_DIR=$BASE_DIR/modules
  CONF_DIR=$BASE_DIR/confs

  export BASE_DIR LIB_DIR MODULE_DIR CONF_DIR

  # shellcheck source=lib/core.sh
  . "$LIB_DIR/core.sh"

  # shellcheck source=lib/os.sh
  . "$LIB_DIR/os.sh"

  # shellcheck source=lib/packages.sh
  . "$LIB_DIR/packages.sh"

  parse_args "$@"

  detect_os
  detect_package_backend
  load_package_backend

  run_module shell
  #run_module prompt
  run_module sddm
  run_module git
  run_module ssh
  #run_module alacritty
  run_module go
  run_module node
  run_module uv
  run_module docker
  run_module codex
  run_module grok
  #run_module antigravity
  run_module caveman
  run_module gitkraken-cli
  run_module fff_mcp
  run_module serena
  run_module zed
  #run_module zellij
  #run_module bat

  log_ok "All done"
}

if (return 0 2>/dev/null); then
  echo "Run, do not source." >&2
  return 1
fi

main "$@"
