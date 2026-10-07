#!/bin/sh
# Zellij setup module. Intended to be sourced.

module_zellij() {
  log_info "Setting up zellij"

  pkg_install_missing_named zellij

  ZELLIJ_DIR=$CONF_DIR/zellij
  ZELLIJ_CONF=$ZELLIJ_DIR/linux.config.kdl
  ZELLIJ_LAYOUTS=$ZELLIJ_DIR/layouts
  ZELLIJ_HOME=${XDG_CONFIG_HOME:-$HOME/.config}/zellij
  ZELLIJ_LAYOUT_DST=$ZELLIJ_HOME/layouts

  require_file "$ZELLIJ_CONF"
  require_dir "$ZELLIJ_LAYOUTS"

  install_user_file "$ZELLIJ_CONF" "$ZELLIJ_HOME/config.kdl" 0644
  install_user_dir_contents "$ZELLIJ_LAYOUTS" "$ZELLIJ_LAYOUT_DST" 0644 0755

  log_ok "Zellij config installed: $ZELLIJ_HOME/config.kdl"
  log_ok "Zellij layouts installed: $ZELLIJ_LAYOUT_DST"
}
