#!/bin/sh
# Serena setup module. Intended to be sourced.
# serena init rewrites ~/.serena/serena_config.yml. The shipped YAML is the config.
# serena setup grok runs `grok mcp add` and rewrites ~/.grok/config.toml.
# The grok module already registers that server.

serena_uv() {
  if command -v uv >/dev/null 2>&1; then
    printf '%s\n' uv
    return 0
  fi

  if [ -x "$HOME/.local/bin/uv" ]; then
    printf '%s\n' "$HOME/.local/bin/uv"
    return 0
  fi

  return 1
}

serena_agent_installed() {
  _serena_uv=$1
  _serena_listing=$("$_serena_uv" tool list 2>/dev/null) || return 1

  case "
$_serena_listing
" in
    *'
serena-agent '*) return 0 ;;
  esac

  return 1
}

install_serena_agent() {
  if ! _serena_uv=$(serena_uv); then
    if [ "$DRY_RUN" -eq 1 ]; then
      log_info "DRY RUN: uv tool install -p 3.13 serena-agent"
      return 0
    fi

    die "Required command not found: uv"
  fi

  if serena_agent_installed "$_serena_uv"; then
    log_ok "Serena already installed"
    return 0
  fi

  log_info "Installing Serena"
  run_cmd "$_serena_uv" tool install -p 3.13 serena-agent
}

serena_home() {
  if [ -n "${SERENA_HOME:-}" ]; then
    printf '%s\n' "$SERENA_HOME"
    return 0
  fi

  printf '%s\n' "$HOME/.serena"
}

serena_projects_block() {
  _serena_file=$1
  _serena_capture=0
  _serena_found=0

  while IFS= read -r _serena_line || [ -n "$_serena_line" ]; do
    case "$_serena_line" in
      projects:*)
        _serena_capture=1
        _serena_found=1
        printf '%s\n' "$_serena_line"
        ;;
      *)
        if [ "$_serena_capture" -eq 1 ]; then
          case "$_serena_line" in
            ""|[[:space:]]*|-*)
              printf '%s\n' "$_serena_line"
              ;;
            *)
              _serena_capture=0
              ;;
          esac
        fi
        ;;
    esac
  done < "$_serena_file"

  [ "$_serena_found" -eq 1 ]
}

install_serena_config() {
  _serena_source=$CONF_DIR/serena/serena_config.linux.yml
  _serena_dest=$(serena_home)/serena_config.yml
  _serena_projects=

  require_file "$_serena_source"

  if [ -f "$_serena_dest" ] && ! grep -q '^projects:' "$_serena_source"; then
    _serena_projects=$(serena_projects_block "$_serena_dest" || true)
  fi

  install_user_file "$_serena_source" "$_serena_dest" 0644

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ -n "$_serena_projects" ]; then
      log_info "DRY RUN: keep registered projects in $_serena_dest"
    fi
    return 0
  fi

  if [ -n "$_serena_projects" ] && ! grep -q '^projects:' "$_serena_dest"; then
    printf '\n%s\n' "$_serena_projects" >> "$_serena_dest"
    log_info "Kept registered Serena projects in $_serena_dest"
  fi

  log_ok "Serena config installed: $_serena_dest"
}

module_serena() {
  log_info "Setting up serena"

  install_serena_agent
  install_serena_config

  log_ok "Serena setup complete"
}
