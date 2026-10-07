#command -v zeditor >/dev/null 2>&1 && alias zed='zeditor'
command -v xdg-open >/dev/null 2>&1 && alias o='xdg-open'

if command -v zellij >/dev/null 2>&1; then
    alias zb1='zellij attach b1 || zellij --new-session-with-layout one-pane --session b1'
    alias zb2v='zellij attach b2v || zellij --new-session-with-layout two-pane-vertical --session b2v'
    alias zb2h='zellij attach b2h || zellij --new-session-with-layout two-pane-horizontal --session b2h'
    alias zb3r='zellij attach b3r || zellij --new-session-with-layout three-pane-right --session b3r'
    alias zb3l='zellij attach b3l || zellij --new-session-with-layout three-pane-left --session b3l'
    alias zb4='zellij attach b4 || zellij --new-session-with-layout four-pane --session b4'
fi

gitstatus() {
  local projects_dir="${HOME}/Projects"
  local gitdir
  local repo
  local rel
  local ahead
  local behind
  local dirty
  local status_line
  local branch_ab
  local green=""
  local red=""
  local reset=""

  if [ -t 1 ]; then
    if command -v tput >/dev/null 2>&1; then
      green="$(tput setaf 2)"
      red="$(tput setaf 1)"
      reset="$(tput sgr0)"
    else
      green='\033[32m'
      red='\033[31m'
      reset='\033[0m'
    fi
  fi

  while IFS= read -r gitdir; do
    repo="${gitdir%/.git}"
    rel="${repo#${projects_dir}/}"

    if ! branch_ab="$(git -C "$repo" status --porcelain=v2 --branch 2>/dev/null | grep '^# branch.ab ' | head -n 1)"; then
      printf '%s error\n' "$rel"
      continue
    fi

    if [ -z "$branch_ab" ]; then
      printf '%s no-upstream\n' "$rel"
      continue
    fi

    ahead="${branch_ab#\# branch.ab +}"
    ahead="${ahead%% *}"
    behind="${branch_ab#\# branch.ab +${ahead} -}"
    behind="${behind%% *}"

    if git -C "$repo" diff --quiet --ignore-submodules -- && git -C "$repo" diff --cached --quiet --ignore-submodules --; then
      dirty=""
    else
      dirty=" dirty"
    fi

    if [ "${ahead}" -eq 0 ] && [ "${behind}" -eq 0 ]; then
      printf '%s %b✓%b%s\n' "$rel" "$green" "$reset" "$dirty"
    elif [ "${behind}" -gt 0 ] && [ "${ahead}" -eq 0 ]; then
      printf '%s %b✗%b behind%s\n' "$rel" "$red" "$reset" "$dirty"
    elif [ "${ahead}" -gt 0 ] && [ "${behind}" -eq 0 ]; then
      printf '%s %b✗%b ahead%s\n' "$rel" "$red" "$reset" "$dirty"
    else
      printf '%s %b✗%b diverged%s\n' "$rel" "$red" "$reset" "$dirty"
    fi
  done < <(
    {
      find "$projects_dir" -mindepth 2 -maxdepth 2 -type d -name .git -print 2>/dev/null
      find "$projects_dir/work" "$projects_dir/varda" -mindepth 2 -maxdepth 2 -type d -name .git -print 2>/dev/null
    } | sort -u
  )
}

update() {
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -Syu --needed
    command -v yay  >/dev/null 2>&1 && yay  -Syu --needed
    command -v paru >/dev/null 2>&1 && paru -Syu --needed
    # fff mcp
    curl -L https://dmtrkovalenko.dev/install-fff-mcp.sh | bash
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get upgrade
    sudo apt-get autoremove --purge
  elif command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo apt upgrade
    sudo apt autoremove --purge
  else
    echo "No supported package manager found."
    return 1
  fi

  if command -v rustup >/dev/null 2>&1; then
    rustup update
  fi

  if command -v codex >/dev/null 2>&1; then
    codex update
  fi
  if command -v grok >/dev/null 2>&1; then
    grok update
  fi

  if command -v npx >/dev/null 2>&1; then
    npx -y github:JuliusBrussee/caveman -- --only grok --force
  fi
}
