#!/bin/sh
# Core POSIX helpers. Intended to be sourced.

: "${BASE_DIR:?BASE_DIR must be set before sourcing core.sh}"
: "${LIB_DIR:?LIB_DIR must be set before sourcing core.sh}"
: "${MODULE_DIR:?MODULE_DIR must be set before sourcing core.sh}"
: "${CONF_DIR:?CONF_DIR must be set before sourcing core.sh}"

PROFILE=${PROFILE:-desktop}
DRY_RUN=${DRY_RUN:-0}

if command -v tput >/dev/null 2>&1 && [ -t 1 ]; then
  red=$(tput setaf 1)
  green=$(tput setaf 2)
  yellow=$(tput setaf 3)
  blue=$(tput setaf 4)
  cyan=$(tput setaf 6)
  reset=$(tput sgr0)
else
  red=
  green=
  yellow=
  blue=
  cyan=
  reset=
fi

export PROFILE DRY_RUN
export red green yellow blue cyan reset

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --profile NAME       Install profile: desktop, server, wsl, minimal
  --dry-run            Print intended actions without making changes
  -h, --help           Show this help
EOF
}

log_info() {
  printf '%s%s%s\n' "$blue" "$*" "$reset"
}

log_ok() {
  printf '%s%s%s\n' "$green" "$*" "$reset"
}

log_warn() {
  printf '%sWARNING:%s %s\n' "$yellow" "$reset" "$*" >&2
}

log_err() {
  printf '%sERROR:%s %s\n' "$red" "$reset" "$*" >&2
}

die() {
  log_err "$*"
  exit 1
}

require_cmd() {
  _core_cmd=$1

  if ! command -v "$_core_cmd" >/dev/null 2>&1; then
    die "Required command not found: $_core_cmd"
  fi
}

require_file() {
  _core_file=$1

  if [ ! -f "$_core_file" ]; then
    die "Missing file: $_core_file"
  fi
}

require_dir() {
  _core_dir=$1

  if [ ! -d "$_core_dir" ]; then
    die "Missing directory: $_core_dir"
  fi
}

run_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '%sDRY RUN:%s' "$cyan" "$reset"
    printf ' %s' "$@"
    printf '\n'
    return 0
  fi

  "$@"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --profile)
        shift
        [ "$#" -gt 0 ] || die "--profile requires a value"
        PROFILE=$1
        ;;
      --profile=*)
        PROFILE=${1#*=}
        ;;
      --dry-run)
        DRY_RUN=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown option: $1"
        ;;
    esac
    shift
  done

  case "$PROFILE" in
    desktop|server|wsl|minimal)
      ;;
    *)
      die "Unsupported profile: $PROFILE"
      ;;
  esac

  export PROFILE DRY_RUN
}

run_module() {
  _core_module_name=$1
  _core_module_file=$MODULE_DIR/$_core_module_name.sh

  require_file "$_core_module_file"

  log_info "Running module: $_core_module_name"

  # shellcheck source=/dev/null
  . "$_core_module_file"

  _core_module_func=module_$_core_module_name

  if ! command -v "$_core_module_func" >/dev/null 2>&1; then
    die "Module '$_core_module_name' does not define $_core_module_func"
  fi

  "$_core_module_func"
}

install_user_file() {
  _core_src=$1
  _core_dst=$2
  _core_mode=${3:-0644}

  _core_dst_dir=$(dirname -- "$_core_dst")

  if [ ! -d "$_core_dst_dir" ]; then
    run_cmd install -d -m 0755 "$_core_dst_dir"
  fi

  run_cmd install -m "$_core_mode" "$_core_src" "$_core_dst"
}

install_root_file() {
  _core_src=$1
  _core_dst=$2
  _core_mode=${3:-0644}

  _core_dst_dir=$(dirname -- "$_core_dst")

  if [ ! -d "$_core_dst_dir" ]; then
    run_cmd sudo install -d -o root -g root -m 0755 "$_core_dst_dir"
  fi

  run_cmd sudo install -o root -g root -m "$_core_mode" "$_core_src" "$_core_dst"
}

install_user_dir_contents() {
  _core_src_dir=$1
  _core_dst_dir=$2
  _core_file_mode=${3:-0644}
  _core_dir_mode=${4:-0755}

  require_dir "$_core_src_dir"

  run_cmd install -d -m "$_core_dir_mode" "$_core_dst_dir"
  run_cmd cp -Rf "$_core_src_dir/." "$_core_dst_dir/"
  run_cmd find "$_core_dst_dir" -type d -exec chmod "$_core_dir_mode" {} +
  run_cmd find "$_core_dst_dir" -type f -exec chmod "$_core_file_mode" {} +
}

install_root_dir_contents() {
  _core_src_dir=$1
  _core_dst_dir=$2
  _core_file_mode=${3:-0644}
  _core_dir_mode=${4:-0755}

  require_dir "$_core_src_dir"

  run_cmd sudo install -d -o root -g root -m "$_core_dir_mode" "$_core_dst_dir"
  run_cmd sudo cp -Rf "$_core_src_dir/." "$_core_dst_dir/"
  run_cmd sudo find "$_core_dst_dir" -type d -exec chmod "$_core_dir_mode" {} +
  run_cmd sudo find "$_core_dst_dir" -type f -exec chmod "$_core_file_mode" {} +
  run_cmd sudo chown -R root:root "$_core_dst_dir"
}
