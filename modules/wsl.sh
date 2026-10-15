#!/bin/sh
# Debian WSL profile. Intended to be sourced.

module_wsl() {
  [ "$OS_ID" = debian ] && is_wsl || die "The wsl profile requires Debian under WSL"
  [ "$(id -u)" -ne 0 ] || die "Run WSL setup as your Debian user, not root"
  require_cmd sudo

  # Do not pick up Windows executables from WSL's inherited PATH.
  PATH=$HOME/.local/bin:$HOME/.go/bin:$HOME/.go/current/bin:$HOME/go/bin:$HOME/.grok/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  export PATH

  pkg_install_missing_named bash bash-completion git ssh-client curl ca-certificates \
    build-essential python3 python3-venv jq tar gzip xz-utils unzip ripgrep

  run_module shell
  run_module git
  . "$MODULE_DIR/ssh-wsl.sh"
  module_ssh_wsl
  run_module go
  run_module node
  run_module uv
  run_module codex
  run_module grok
  run_module caveman
  run_module fff_mcp
  run_module serena

  log_ok "WSL development setup complete. Open a new Debian shell; authenticate Codex and Grok separately."
}

install_wsl_go() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log_info "DRY RUN: install goup if missing, then install latest stable Go with goup"
    return
  fi

  if [ ! -x "$HOME/.go/bin/goup" ]; then
    (
      installer=$(mktemp)
      trap 'rm -f -- "$installer"' EXIT HUP INT TERM
      curl -fsSL https://raw.githubusercontent.com/owenthereal/goup/master/install.sh -o "$installer"
      sh "$installer" --skip-prompt
    )
  fi
  "$HOME/.go/bin/goup" install
  "$HOME/.go/current/bin/go" version
}

install_wsl_node() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log_info "DRY RUN: install nvm if missing, then install and select latest Node LTS"
    return
  fi

  NVM_DIR="$HOME/.nvm"
  export NVM_DIR

  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    (
      installer=$(mktemp)
      trap 'rm -f -- "$installer"' EXIT HUP INT TERM
      curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.7/install.sh -o "$installer"
      PROFILE=/dev/null bash --noprofile --norc "$installer"
    )
  fi

  # Keep nvm's shell state outside the installer's strict POSIX shell.
  node_binary=$(bash --noprofile --norc -c '
    . "$NVM_DIR/nvm.sh" --no-use || exit 1
    nvm install --lts >&2 || exit 1
    nvm alias default "lts/*" >&2 || exit 1
    nvm which default
  ') || die "Node LTS setup with nvm failed"
  [ -x "$node_binary" ] || die "nvm did not select an installed Node binary"
  PATH=${node_binary%/*}:$PATH
  export PATH
  node --version
  npm --version
}
