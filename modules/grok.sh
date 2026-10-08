#!/bin/sh
# Grok setup module. Intended to be sourced.

install_grok_cli() {
  if command -v grok >/dev/null 2>&1; then
    log_ok "Grok CLI already installed"
    return 0
  fi

  require_cmd bash
  require_cmd curl

  log_info "Installing Grok CLI"
  run_cmd curl -fsSL https://x.ai/cli/install.sh -o /tmp/install-grok.sh
  run_cmd bash /tmp/install-grok.sh
}

module_grok() {
  log_info "Setting up grok"

  require_cmd install

  install_grok_cli

  GROK_DIR=$CONF_DIR/grok
  AGENTS_FILE=$GROK_DIR/AGENTS.md
  CONFIG_FILE=$GROK_DIR/config.toml
  SANDBOX_FILE=$GROK_DIR/linux.sandbox.toml
  CREW_DIR=$GROK_DIR/agents
  GROK_HOME=$HOME/.grok

  require_file "$AGENTS_FILE"
  require_file "$CONFIG_FILE"
  require_file "$SANDBOX_FILE"
  require_dir "$CREW_DIR"

  run_cmd install -d -m 0755 "$GROK_HOME"
  run_cmd install -d -m 0755 "$GROK_HOME/agents"

  install_user_file "$AGENTS_FILE" "$GROK_HOME/AGENTS.md" 0644
  install_user_file "$CONFIG_FILE" "$GROK_HOME/config.toml" 0644
  install_user_file "$SANDBOX_FILE" "$GROK_HOME/sandbox.toml" 0644

  for agent_file in "$CREW_DIR"/*.md; do
    require_file "$agent_file"
    install_user_file "$agent_file" "$GROK_HOME/agents/$(basename -- "$agent_file")" 0644
  done

  install_grok_hooks

  log_ok "Grok config installed: $GROK_HOME"
}

install_grok_hooks() {
  hook_json=$CONF_DIR/grok/linux.hooks.json
  turn_end=$CONF_DIR/../agents/hooks/turn_end.py
  tool_gate=$CONF_DIR/../agents/hooks/tool_gate.py
  grok_review=$CONF_DIR/../agents/hooks/grok_review.py
  voice=$CONF_DIR/grok/rules/voice.md
  grok_hooks=$HOME/.grok/hooks
  shared_hook_target=$HOME/.agents/hooks/bin
  grok_rules=$HOME/.grok/rules

  require_file "$hook_json"
  require_file "$turn_end"
  require_file "$tool_gate"
  require_file "$grok_review"
  require_file "$voice"

  if ! command -v python3 >/dev/null 2>&1; then
    log_warn "python3 not found; grok hooks need python3"
  fi

  # Grok loads ~/.grok/hooks/*.json. Shared scripts live in ~/.agents/hooks/bin.
  # Drop the old config name so those hooks do not run twice.
  log_info "Installing Grok hooks"
  install_user_file "$turn_end" "$shared_hook_target/turn_end.py" 0644
  install_user_file "$tool_gate" "$shared_hook_target/tool_gate.py" 0644
  install_user_file "$grok_review" "$shared_hook_target/grok_review.py" 0644
  install_user_file "$hook_json" "$grok_hooks/hooks.json" 0644
  install_user_file "$voice" "$grok_rules/voice.md" 0644
  if [ -f "$grok_hooks/turn_end.json" ]; then
    run_cmd rm -f -- "$grok_hooks/turn_end.json"
  fi
  log_ok "Grok hooks installed: $grok_hooks"
}
