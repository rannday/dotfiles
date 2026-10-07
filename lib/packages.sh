#!/bin/sh
# Package manager abstraction. Intended to be sourced.

PKG_BACKEND=${PKG_BACKEND:-}

detect_package_backend() {
  if [ -n "$PKG_BACKEND" ]; then
    log_info "Using package backend from env: $PKG_BACKEND"
  elif command -v pacman >/dev/null 2>&1; then
    PKG_BACKEND=pacman
  elif command -v apt-get >/dev/null 2>&1; then
    PKG_BACKEND=apt
  else
    die "No supported package manager found"
  fi

  case "$PKG_BACKEND" in
    pacman|apt)
      ;;
    *)
      die "Unsupported package backend: $PKG_BACKEND"
      ;;
  esac

  export PKG_BACKEND
  log_info "Package backend: $PKG_BACKEND"
}

load_package_backend() {
  case "$PKG_BACKEND" in
    pacman)
      # shellcheck source=lib/pacman.sh
      . "$LIB_DIR/pacman.sh"
      ;;
    apt)
      # shellcheck source=lib/apt.sh
      . "$LIB_DIR/apt.sh"
      ;;
    *)
      die "Unsupported package backend: $PKG_BACKEND"
      ;;
  esac

  require_pkg_backend_func pkg_update
  require_pkg_backend_func pkg_upgrade
  require_pkg_backend_func pkg_install
  require_pkg_backend_func pkg_installed
  require_pkg_backend_func pkg_name
}

require_pkg_backend_func() {
  func=$1

  if ! command -v "$func" >/dev/null 2>&1; then
    die "Package backend '$PKG_BACKEND' does not define $func"
  fi
}

#pkg_install_named() {
#  pkgs=
#
#  for logical in "$@"; do
#    name=$(pkg_name "$logical")
#    pkgs=${pkgs:+"$pkgs "}$name
#  done
#
#  [ -n "$pkgs" ] || return 0
#
#  # shellcheck disable=SC2086
#  pkg_install $pkgs
#}

pkg_missing_named() {
  missing=

  for logical in "$@"; do
    name=$(pkg_name "$logical")

    if ! pkg_installed "$name"; then
      missing=${missing:+"$missing "}$name
    fi
  done

  printf '%s\n' "$missing"
}

pkg_install_missing_named() {
  missing=$(pkg_missing_named "$@")

  if [ -z "$missing" ]; then
    log_ok "Packages already installed: $*"
    return 0
  fi

  # shellcheck disable=SC2086
  pkg_install $missing
}

pkg_aur_install_missing_named() {
  missing=$(pkg_missing_named "$@")

  if [ -z "$missing" ]; then
    log_ok "AUR packages already installed: $*"
    return 0
  fi

  # shellcheck disable=SC2086
  pkg_aur_install $missing
}

pkg_aur_update() {
  :
}

pkg_aur_install() {
  die "AUR packages are not supported by backend: $PKG_BACKEND"
}
