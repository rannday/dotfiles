#!/bin/sh
# Alacritty setup module. Intended to be sourced.

module_alacritty() {
  log_info "Setting up alacritty"

  require_cmd install

  pkg_install_missing_named alacritty adobe-source-code-pro-fonts

  ALAC_DIR=$CONF_DIR/alacritty
  ALAC_CONF=$ALAC_DIR/linux.alacritty.toml
  ALAC_HOME=${XDG_CONFIG_HOME:-$HOME/.config}/alacritty
  ALAC_THEMES=$ALAC_HOME/themes

  require_file "$ALAC_CONF"

  if [ ! -d "$ALAC_HOME" ]; then
    log_info "Creating Alacritty config directory: $ALAC_HOME"
    run_cmd install -d -m 0755 "$ALAC_HOME"
  fi

  install_user_file "$ALAC_CONF" "$ALAC_HOME/alacritty.toml" 0644

  if [ -d "$ALAC_DIR/themes" ]; then
    install_user_dir_contents "$ALAC_DIR/themes" "$ALAC_THEMES" 0644 0755
  else
    log_warn "No Alacritty themes found in $ALAC_DIR/themes"
  fi
}
