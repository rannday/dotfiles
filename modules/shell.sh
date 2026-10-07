#!/bin/sh
# Shell setup module. Intended to be sourced.

module_shell() {
  log_info "Setting up shell"

  require_cmd dirname
  require_cmd install
  require_cmd cp
  require_cmd find
  require_cmd chmod

  pkg_install_missing_named bash

  BASH_DIR=$CONF_DIR/bash
  ETC_DIR=$BASH_DIR/etc
  ROOT_DIR=$BASH_DIR/root
  HOME_DIR=$BASH_DIR/home

  umask 022

  install_shell_etc
  install_shell_root
  install_shell_home
}

install_shell_etc() {
  if [ ! -d "$ETC_DIR" ]; then
    return 0
  fi

  log_info "Installing shell configurations to /etc"

  if [ -f "$ETC_DIR/bash.bashrc" ]; then
    install_root_file "$ETC_DIR/bash.bashrc" /etc/bash.bashrc 0644
  fi

  if [ -d "$ETC_DIR/bash.bashrc.d" ]; then
    install_root_dir_contents "$ETC_DIR/bash.bashrc.d" /etc/bash.bashrc.d 0644 0755
  fi
}

install_shell_root() {
  if [ ! -d "$ROOT_DIR" ]; then
    return 0
  fi

  log_info "Installing shell configurations to /root"

  if [ -f "$ROOT_DIR/bashrc" ]; then
    install_root_file "$ROOT_DIR/bashrc" /root/.bashrc 0644
  fi

  if [ -f "$ROOT_DIR/bash_profile" ]; then
    install_root_file "$ROOT_DIR/bash_profile" /root/.bash_profile 0644
  fi

  if [ -f "$ROOT_DIR/bash_logout" ]; then
    install_root_file "$ROOT_DIR/bash_logout" /root/.bash_logout 0644
  fi

  if [ -d "$ROOT_DIR/bashrc.d" ]; then
    install_root_dir_contents "$ROOT_DIR/bashrc.d" /root/.bashrc.d 0644 0755
  fi
}

install_shell_home() {
  if [ ! -d "$HOME_DIR" ]; then
    return 0
  fi

  log_info "Installing shell configurations to \$HOME"

  if [ -f "$HOME_DIR/bashrc" ]; then
    install_user_file "$HOME_DIR/bashrc" "$HOME/.bashrc" 0644
  fi

  if [ -f "$HOME_DIR/bash_profile" ]; then
    install_user_file "$HOME_DIR/bash_profile" "$HOME/.bash_profile" 0644
  fi

  if [ -f "$HOME_DIR/bash_logout" ]; then
    install_user_file "$HOME_DIR/bash_logout" "$HOME/.bash_logout" 0644
  fi

  if [ -f "$HOME_DIR/xprofile" ]; then
    install_user_file "$HOME_DIR/xprofile" "$HOME/.xprofile" 0644
  fi

  if [ -d "$HOME_DIR/bashrc.d" ]; then
    install_user_dir_contents "$HOME_DIR/bashrc.d" "$HOME/.bashrc.d" 0644 0755
  fi
}
