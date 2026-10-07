#!/bin/sh
# Shell setup module. Intended to be sourced.

install_starship() {
  log_info "Installing starship prompt"

  pkg_install_missing_named starship ttf-font-nerd
}

install_zoxide() {
  pkg_install_missing_named zoxide fzf
}

module_prompt() {
  log_info "Setting up prompt"
}
