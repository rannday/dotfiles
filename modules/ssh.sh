#!/bin/sh
# shellcheck disable=SC2153
# SSH setup module. Intended to be sourced.

module_ssh() {
  log_info "Setting up ssh"

  require_cmd awk
  require_cmd cat
  require_cmd chmod
  require_cmd chown
  require_cmd find
  require_cmd id
  require_cmd install
  require_cmd mktemp
  require_cmd mv
  require_cmd od
  require_cmd rm
  require_cmd hostname
  require_cmd ssh-keygen
  require_cmd tail
  require_cmd tr

  pkg_install_missing_named ssh-client

  SSH_CONF=$CONF_DIR/sshconfig
  SSH_HOME=$HOME/.ssh
  NOC_CONF=$SSH_HOME/noc-config
  CONF_DST=$SSH_HOME/config
  STAGED_CONF=$SSH_HOME/sshconfig

  require_file "$SSH_CONF"

  run_cmd install -d -m 0700 "$SSH_HOME"

  generate_ssh_keys
  install_ssh_config

  if [ "$DRY_RUN" -eq 0 ]; then
    warn_missing_ssh_identities
  fi

  fix_ssh_permissions
}

generate_ssh_keys() {
  log_info "Checking machine-specific SSH keys"

  generate_ssh_key "$SSH_HOME/id_ed25519" "default"
  generate_ssh_key "$SSH_HOME/id_ed25519_github" "github"
  generate_ssh_key "$SSH_HOME/id_ed25519_varda" "varda"
  generate_ssh_key "$SSH_HOME/id_ed25519_noc" "noc"
  generate_ssh_key "$SSH_HOME/id_ed25519_noc_github" "noc-github"
}

generate_ssh_key() {
  _ssh_key_path=$1
  _ssh_key_label=$2

  if [ -f "$_ssh_key_path" ]; then
    log_ok "SSH key already exists: $_ssh_key_path"
    return 0
  fi

  if [ -f "$_ssh_key_path.pub" ]; then
    log_warn "Public key exists without private key: $_ssh_key_path.pub"
    return 1
  fi

  log_info "Generating SSH key: $_ssh_key_path"

  run_cmd ssh-keygen \
    -t ed25519 \
    -f "$_ssh_key_path" \
    -C "$(id -un)@$(hostname)-$_ssh_key_label" \
    -N ""
}

install_ssh_config() {
  _ssh_tmp_cfg=$(mktemp)
  trap 'rm -f "$_ssh_tmp_cfg"' EXIT HUP INT TERM

  log_info "Cleaning up old SSH config files"
  run_cmd rm -f -- "$CONF_DST" "$STAGED_CONF"

  log_info "Copying base SSH configuration"
  run_cmd install -m 0600 "$SSH_CONF" "$STAGED_CONF"

  if [ -f "$NOC_CONF" ]; then
    log_info "Merging noc-config into SSH config"

    if [ "$DRY_RUN" -eq 1 ]; then
      log_info "Would merge $NOC_CONF and $STAGED_CONF into $CONF_DST"
      run_cmd rm -f -- "$STAGED_CONF"
      return 0
    fi

    cat "$NOC_CONF" >"$_ssh_tmp_cfg"

    if [ -s "$_ssh_tmp_cfg" ] &&
      [ "$(tail -c 1 "$_ssh_tmp_cfg" | od -An -tx1 | tr -d '[:space:]')" != "0a" ]; then
      printf '\n' >>"$_ssh_tmp_cfg"
    fi

    cat "$STAGED_CONF" >>"$_ssh_tmp_cfg"

    log_info "Installing merged SSH configuration"
    run_cmd install -m 0600 "$_ssh_tmp_cfg" "$CONF_DST"
    run_cmd rm -f -- "$STAGED_CONF"

    log_ok "SSH config successfully merged and updated"
  else
    log_warn "noc-config not found; using base SSH config only"
    run_cmd mv -f -- "$STAGED_CONF" "$CONF_DST"
    run_cmd chmod 0600 "$CONF_DST"
  fi
}

warn_missing_ssh_identities() {
  _ssh_missing=0

  awk 'tolower($1) == "identityfile" { print $2 }' "$CONF_DST" |
    while IFS= read -r _ssh_identity_file; do
      _ssh_identity_file=$(printf '%s' "$_ssh_identity_file" | tr -d '\r')
      _ssh_identity_file=${_ssh_identity_file%\"}
      _ssh_identity_file=${_ssh_identity_file#\"}

      case "$_ssh_identity_file" in
        \~/*)
          _ssh_identity_file=$HOME/${_ssh_identity_file#\~/}
          ;;
      esac

      case "$_ssh_identity_file" in
        /*)
          if [ ! -f "$_ssh_identity_file" ]; then
            if [ "$_ssh_missing" -eq 0 ]; then
              log_warn "SSH config references missing identity files:"
              _ssh_missing=1
            fi

            printf '  %s\n' "$_ssh_identity_file" >&2
          fi
          ;;
      esac
    done
}

fix_ssh_permissions() {
  log_info "Fixing SSH permissions"

  run_cmd chown -R "$(id -u):$(id -g)" "$SSH_HOME"

  run_cmd find "$SSH_HOME" -type d -exec chmod 0700 {} +
  run_cmd find "$SSH_HOME" -type f -exec chmod 0600 {} +
  run_cmd find "$SSH_HOME" -type f -name "*.pub" -exec chmod 0644 {} +

  if [ -f "$SSH_HOME/known_hosts" ]; then
    run_cmd chmod 0644 "$SSH_HOME/known_hosts"
  fi

  if [ -f "$SSH_HOME/known_hosts2" ]; then
    run_cmd chmod 0644 "$SSH_HOME/known_hosts2"
  fi

  if [ -f "$SSH_HOME/config" ]; then
    run_cmd chmod 0600 "$SSH_HOME/config"
  fi

  if [ -f "$SSH_HOME/authorized_keys" ]; then
    run_cmd chmod 0600 "$SSH_HOME/authorized_keys"
  fi

  run_cmd chmod go-w "$HOME"
}
