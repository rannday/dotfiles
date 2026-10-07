#!/bin/sh
# OS/environment detection. Intended to be sourced.

OS_ID=unknown
OS_NAME=unknown
OS_VERSION_ID=
OS_ID_LIKE=
IS_WSL=0
HAS_SYSTEMD=0
INIT_SYSTEM=unknown

detect_os_release() {
  if [ ! -r /etc/os-release ]; then
    die "Cannot read /etc/os-release"
  fi

  # /etc/os-release is shell-compatible key=value data.
  # shellcheck disable=SC1091
  . /etc/os-release

  OS_ID=${ID:-unknown}
  OS_NAME=${NAME:-unknown}
  OS_VERSION_ID=${VERSION_ID:-}
  OS_ID_LIKE=${ID_LIKE:-}

  export OS_ID OS_NAME OS_VERSION_ID OS_ID_LIKE
}

detect_wsl() {
  IS_WSL=0

  if [ -n "${WSL_DISTRO_NAME:-}" ]; then
    IS_WSL=1
  elif grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=1
  fi

  export IS_WSL
}

detect_init_system() {
  HAS_SYSTEMD=0
  INIT_SYSTEM=unknown

  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    HAS_SYSTEMD=1
    INIT_SYSTEM=systemd
  elif command -v dinitctl >/dev/null 2>&1; then
    INIT_SYSTEM=dinit
  elif command -v rc-service >/dev/null 2>&1; then
    INIT_SYSTEM=openrc
  elif command -v sv >/dev/null 2>&1; then
    INIT_SYSTEM=runit
  elif command -v s6-rc >/dev/null 2>&1; then
    INIT_SYSTEM=s6
  elif command -v service >/dev/null 2>&1; then
    INIT_SYSTEM=sysvinit
  fi

  export HAS_SYSTEMD INIT_SYSTEM
}

detect_os() {
  detect_os_release
  detect_wsl
  detect_init_system

  log_info "Detected OS: $OS_NAME"
  log_info "OS ID: $OS_ID"

  if [ -n "$OS_VERSION_ID" ]; then
    log_info "Version: $OS_VERSION_ID"
  fi

  if [ -n "$OS_ID_LIKE" ]; then
    log_info "ID like: $OS_ID_LIKE"
  fi

  if [ "$IS_WSL" -eq 1 ]; then
    log_info "Environment: WSL"
  fi

  log_info "Init system: $INIT_SYSTEM"
}

os_is() {
  wanted=$1

  [ "$OS_ID" = "$wanted" ]
}

os_like() {
  wanted=$1

  case " $OS_ID $OS_ID_LIKE " in
    *" $wanted "*) return 0 ;;
    *) return 1 ;;
  esac
}

is_wsl() {
  [ "$IS_WSL" -eq 1 ]
}

has_systemd() {
  [ "$HAS_SYSTEMD" -eq 1 ]
}
