#!/bin/sh
# Caveman setup module. Intended to be sourced.

module_caveman() {
  log_info "Setting up caveman"

  if [ -f "$HOME/.grok/skills/caveman/SKILL.md" ]; then
    log_ok "Caveman already installed for Grok"
  else
    require_cmd npx
    log_info "Installing Caveman for Grok"
    run_cmd npx -y github:JuliusBrussee/caveman -- --only grok
  fi

  if [ -f "$HOME/.agents/skills/caveman/SKILL.md" ]; then
    log_ok "Caveman already installed for Codex"
  else
    require_cmd npx
    log_info "Installing Caveman for Codex"
    run_cmd npx --allow-git=all -y skills add JuliusBrussee/caveman --skill '*' -a codex --yes -g
  fi
}
