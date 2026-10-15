#!/bin/sh
# Node setup module. Intended to be sourced.

module_node() {
  log_info "Setting up node"

  if [ "$PROFILE" = wsl ]; then
    install_wsl_node
  else
    pkg_install_missing_named node npm
  fi

  log_ok "Node setup complete"
}
