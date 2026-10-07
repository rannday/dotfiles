#!/bin/sh
# FFF MCP setup module. Intended to be sourced.

module_fff_mcp() {
  log_info "Setting up fff-mcp"

  if command -v fff-mcp >/dev/null 2>&1 || [ -x "$HOME/.local/bin/fff-mcp" ]; then
    log_ok "FFF MCP already installed"
    return 0
  fi

  require_cmd bash
  require_cmd curl

  pkg_install_missing_named curl

  log_info "Installing FFF MCP"
  run_cmd curl -L https://dmtrkovalenko.dev/install-fff-mcp.sh -o /tmp/install-fff-mcp.sh
  run_cmd bash /tmp/install-fff-mcp.sh
}