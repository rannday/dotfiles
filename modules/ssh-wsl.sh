#!/bin/sh
# Debian default, GitHub, and Varda SSH keys. Intended to be sourced.

module_ssh_wsl() {
  log_info "Setting up WSL SSH"
  pkg_install_missing_named ssh-client

  run_cmd install -d -m 0700 "$HOME/.ssh"
  for _wsl_key in id_ed25519 id_ed25519_github id_ed25519_varda; do
    if [ -f "$HOME/.ssh/$_wsl_key" ]; then
      log_ok "SSH key already exists: ~/.ssh/$_wsl_key"
    else
      [ ! -e "$HOME/.ssh/$_wsl_key.pub" ] || die "Public key exists without private key: ~/.ssh/$_wsl_key.pub"
      run_cmd ssh-keygen -t ed25519 -f "$HOME/.ssh/$_wsl_key" -N ""
    fi

    run_cmd chmod 0600 "$HOME/.ssh/$_wsl_key"
    if [ -f "$HOME/.ssh/$_wsl_key.pub" ]; then
      run_cmd chmod 0644 "$HOME/.ssh/$_wsl_key.pub"
    fi
  done
}
