#!/bin/sh
# Go setup module. Intended to be sourced.

module_go() {
  log_info "Setting up go"

  if [ "$PROFILE" = wsl ]; then
    install_wsl_go
  else
    pkg_install_missing_named go
  fi

  export GOTMPDIR=${GOTMPDIR:-$HOME/go/tmp}
  export GOCACHE=${GOCACHE:-$HOME/.cache/go-build}
  export GOMODCACHE=${GOMODCACHE:-$HOME/go/pkg/mod}

  run_cmd install -d -m 0755 "$GOTMPDIR" "$GOCACHE" "$GOMODCACHE"

  if command -v gopls >/dev/null 2>&1 || [ -x "$HOME/go/bin/gopls" ]; then
    log_ok "gopls already installed"
  else
    [ "$DRY_RUN" -eq 1 ] || require_cmd go
    log_info "Installing gopls"
    run_cmd go install golang.org/x/tools/gopls@latest
  fi

  if command -v govulncheck >/dev/null 2>&1 || [ -x "$HOME/go/bin/govulncheck" ]; then
    log_ok "govulncheck already installed"
  else
    [ "$DRY_RUN" -eq 1 ] || require_cmd go
    log_info "Installing govulncheck"
    run_cmd go install golang.org/x/vuln/cmd/govulncheck@latest
  fi

  if command -v golangci-lint >/dev/null 2>&1 || [ -x "$HOME/go/bin/golangci-lint" ]; then
    log_ok "golangci-lint already installed"
  elif [ "$DRY_RUN" -eq 1 ]; then
    log_info "DRY RUN: install golangci-lint v2.14.0 to $HOME/go/bin"
  else
    pkg_install_missing_named curl
    log_info "Installing golangci-lint v2.14.0"
    run_cmd install -d -m 0755 "$HOME/go/bin"
    (
      installer=$(mktemp)
      trap 'rm -f -- "$installer"' EXIT HUP INT TERM
      curl -sSfL https://golangci-lint.run/install.sh -o "$installer"
      sh "$installer" -b "$HOME/go/bin" v2.14.0
    )
  fi

  log_ok "Go setup complete"
}
