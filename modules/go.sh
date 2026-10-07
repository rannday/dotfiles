#!/bin/sh
# Go setup module. Intended to be sourced.

module_go() {
  log_info "Setting up go"

  pkg_install_missing_named go

  export GOTMPDIR=${GOTMPDIR:-$HOME/go/tmp}
  export GOCACHE=${GOCACHE:-$HOME/.cache/go-build}
  export GOMODCACHE=${GOMODCACHE:-$HOME/go/pkg/mod}

  run_cmd install -d -m 0755 "$GOTMPDIR" "$GOCACHE" "$GOMODCACHE"

  if command -v gopls >/dev/null 2>&1 || [ -x "$HOME/go/bin/gopls" ]; then
    log_ok "gopls already installed"
  else
    require_cmd go
    log_info "Installing gopls"
    run_cmd go install golang.org/x/tools/gopls@latest
  fi

  log_ok "Go setup complete"
}
