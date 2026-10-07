#!/bin/sh
# uv setup module. Intended to be sourced.

module_uv() {
  log_info "Setting up uv"

  if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
    log_ok "uv already installed"
    return 0
  fi

  require_cmd curl
  require_cmd sh

  log_info "Installing uv"
  run_cmd curl -LsSf https://astral.sh/uv/install.sh -o /tmp/install-uv.sh
  run_cmd sh /tmp/install-uv.sh

  log_ok "uv setup complete"
}
