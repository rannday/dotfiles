#!/bin/sh
# Codex setup module. Intended to be sourced.

module_codex() {
  log_info "Setting up codex"

  require_cmd install

  pkg_install_missing_named jq

  if command -v codex >/dev/null 2>&1; then
    log_ok "Codex CLI already installed"
  else
    pkg_aur_install_missing_named openai-codex
  fi

  CODEX_DIR=$CONF_DIR/codex
  AGENTS_FILE=$CODEX_DIR/AGENTS.md
  WORKFLOW_FILE=$CODEX_DIR/workflow.md
  CONFIG_FILE=$CODEX_DIR/linux.config.toml
  SERENA_CONTEXT=$CODEX_DIR/serena-context.yml
  RULES_DIR=$CODEX_DIR/rules
  CREW_DIR=$CODEX_DIR/agents
  HOOK_JSON=$CODEX_DIR/linux.hooks.json
  SHARED_HOOKS=$CONF_DIR/../agents/hooks
  CODEX_HOME=$HOME/.codex
  SHARED_HOOK_TARGET=$HOME/.agents/hooks/bin
  CODEX_RULES=$CODEX_HOME/rules

  require_file "$AGENTS_FILE"
  require_file "$WORKFLOW_FILE"
  require_file "$CONFIG_FILE"
  require_file "$SERENA_CONTEXT"
  require_dir "$RULES_DIR"
  require_dir "$CREW_DIR"
  require_file "$HOOK_JSON"
  for hook_name in tool_gate.py codex_hooks.py; do
    require_file "$SHARED_HOOKS/$hook_name"
  done

  run_cmd install -d -m 0755 "$CODEX_HOME"
  run_cmd install -d -m 0755 "$CODEX_RULES"

  install_user_file "$AGENTS_FILE" "$CODEX_HOME/AGENTS.md" 0644
  install_user_file "$WORKFLOW_FILE" "$CODEX_HOME/workflow.md" 0644
  install_user_file "$CONFIG_FILE" "$CODEX_HOME/config.toml" 0644
  install_user_file "$SERENA_CONTEXT" "$CODEX_HOME/serena-context.yml" 0644
  install_user_file "$HOOK_JSON" "$CODEX_HOME/hooks.json" 0644
  for hook_name in tool_gate.py codex_hooks.py; do
    install_user_file "$SHARED_HOOKS/$hook_name" "$SHARED_HOOK_TARGET/$hook_name" 0644
  done
  for agent_file in "$CREW_DIR"/*.toml; do
    require_file "$agent_file"
    install_user_file "$agent_file" "$CODEX_HOME/agents/$(basename -- "$agent_file")" 0644
  done

  for rule_file in "$RULES_DIR"/*.rules; do
    require_file "$rule_file"
    [ "$(basename -- "$rule_file")" = "windows.rules" ] && continue
    install_user_file "$rule_file" "$CODEX_RULES/$(basename -- "$rule_file")" 0644
  done

  log_ok "Codex config installed: $CODEX_HOME"
}
