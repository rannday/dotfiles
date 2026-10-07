#!/bin/sh
# Git setup module. Intended to be sourced.

module_git() {
  log_info "Setting up git"

  pkg_install_missing_named git

  GIT_DIR=$CONF_DIR/git

  require_dir "$GIT_DIR"

  for git_file in .gitconfig .gitconfig-varda; do
    require_file "$GIT_DIR/$git_file"
    install_user_file "$GIT_DIR/$git_file" "$HOME/$git_file" 0644
  done
}
