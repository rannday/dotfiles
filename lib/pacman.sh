#!/bin/sh
# pacman package backend. Intended to be sourced.

pkg_update() {
  :
}

pkg_upgrade() {
  log_info "Updating and upgrading pacman packages"
  run_cmd sudo pacman -Syu --noconfirm
}

pkg_install() {
  [ "$#" -gt 0 ] || return 0

  log_info "Installing packages with pacman: $*"
  run_cmd sudo pacman -S --needed --noconfirm "$@"
}

pkg_installed() {
  pkg=$1
  pacman -Qi "$pkg" >/dev/null 2>&1
}

pkg_name() {
  case "$1" in
    git)
      echo git
      ;;
    ssh-client|ssh-server)
      echo openssh
      ;;
    curl)
      echo curl
      ;;
    wget)
      echo wget
      ;;
    ca-certificates)
      echo ca-certificates
      ;;
    gnupg)
      echo gnupg
      ;;
    unzip)
      echo unzip
      ;;
    tar)
      echo tar
      ;;
    gzip)
      echo gzip
      ;;
    make)
      echo make
      ;;
    gcc)
      echo gcc
      ;;
    go)
      echo go
      ;;
    node)
      echo nodejs
      ;;
    npm)
      echo npm
      ;;
    docker)
      echo docker
      ;;
    docker-compose)
      echo docker-compose
      ;;
    bat)
      echo bat
      ;;
    fd)
      echo fd
      ;;
    ripgrep)
      echo ripgrep
      ;;
    zellij)
      echo zellij
      ;;
    jq)
      echo jq
      ;;
    openai-codex)
      echo openai-codex-bin
      ;;
    fff-mcp)
      echo fff-mcp-bin
      ;;
    *)
      echo "$1"
      ;;
  esac
}

pkg_aur_update() {
  if command -v paru >/dev/null 2>&1; then
    log_info "Updating AUR packages with paru"
    run_cmd paru -Sua --noconfirm
  else
    log_warn "paru not found; skipping AUR update"
  fi
}

pkg_aur_install() {
  [ "$#" -gt 0 ] || return 0

  if ! command -v paru >/dev/null 2>&1; then
    die "paru not found; cannot install AUR packages: $*"
  fi

  log_info "Installing AUR packages with paru: $*"
  run_cmd paru -S --needed --noconfirm "$@"
}
