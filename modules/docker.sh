#!/bin/sh
# Docker setup module. Intended to be sourced.

module_docker() {
  log_info "Setting up docker"

  pkg_install_missing_named docker docker-compose

  log_ok "Docker setup complete"
}
