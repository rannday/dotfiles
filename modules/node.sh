#!/bin/sh
# Node setup module. Intended to be sourced.

module_node() {
  log_info "Setting up node"

  pkg_install_missing_named node npm

  log_ok "Node setup complete"
}
