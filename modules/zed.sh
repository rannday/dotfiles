#!/bin/sh
# Zed setup module. Intended to be sourced.

module_zed() {
  log_info "Setting up zed"

  #pkg_install_missing_named zed

  ZED_CONF=$CONF_DIR/zed/settings.linux.json
  ZED_HOME=${XDG_CONFIG_HOME:-$HOME/.config}/zed
  ZED_DST=$ZED_HOME/settings.json

  require_file "$ZED_CONF"

  install_user_file "$ZED_CONF" "$ZED_DST" 0644

  log_ok "Zed settings installed: $ZED_DST"
}
