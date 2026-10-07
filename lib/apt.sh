#!/bin/sh
# apt package backend. Intended to be sourced.

pkg_update() {
  log_info "Updating apt package index"
  run_cmd sudo apt-get update
}

pkg_upgrade() {
  log_info "Upgrading apt packages"
  run_cmd sudo apt-get upgrade -y
}

pkg_install() {
  [ "$#" -gt 0 ] || return 0

  if [ "${APT_INDEX_UPDATED:-0}" -ne 1 ]; then
    log_info "Updating apt package index"
    run_cmd sudo apt-get update
    APT_INDEX_UPDATED=1
    export APT_INDEX_UPDATED
  fi

  log_info "Installing packages with apt: $*"
  run_cmd sudo apt-get install -y "$@"
}

pkg_installed() {
  pkg=$1
  dpkg -s "$pkg" >/dev/null 2>&1
}

pkg_name() {
  case "$1" in
    git)
      echo git
      ;;
    ssh-client)
      echo openssh-client
      ;;
    ssh-server)
      echo openssh-server
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
      echo golang
      ;;
    node)
      echo nodejs
      ;;
    npm)
      echo npm
      ;;
    docker)
      echo docker.io
      ;;
    docker-compose)
      echo docker-compose
      ;;
    bat)
      echo bat
      ;;
    fd)
      echo fd-find
      ;;
    ripgrep)
      echo ripgrep
      ;;
    zellij)
      echo zellij
      ;;
    bitwarden-cli)
      echo bitwarden-cli
      ;;
    jq)
      echo jq
      ;;
    *)
      echo "$1"
      ;;
  esac
}
