#!/bin/sh
# SDDM setup module. Intended to be sourced.

module_sddm() {
  log_info "Setting up sddm"

  require_cmd chmod
  require_cmd cp
  require_cmd find
  require_cmd install

  pkg_install_missing_named sddm qt5-quickcontrols2

  SDDM_DIR=$CONF_DIR/sddm/theme-windows-xp
  SDDM_THEME_DIR=/usr/share/sddm/themes/windows-xp

  require_dir "$SDDM_DIR"

  install_sddm_theme
}

install_sddm_theme() {
  log_info "Installing SDDM theme to $SDDM_THEME_DIR"
  install_root_dir_contents "$SDDM_DIR" "$SDDM_THEME_DIR" 0644 0755
}
