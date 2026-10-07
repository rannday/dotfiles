#!/bin/sh
# GitKraken CLI setup module. Intended to be sourced.

module_gitkraken-cli() {
  log_info "Setting up gitkraken-cli"

  if command -v gk >/dev/null 2>&1; then
    log_ok "GitKraken CLI already installed"
    return 0
  fi

  log_warn "GitKraken CLI is not installed. Windows installs GitKraken.cli with winget. No apt or pacman package is mapped."
}
