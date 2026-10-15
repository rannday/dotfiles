# Linux tools installed by the WSL development profile.
if [ -n "${WSL_DISTRO_NAME:-}" ]; then
  export PATH="$HOME/.local/bin:$HOME/.go/bin:$HOME/.go/current/bin:$HOME/go/bin:$HOME/.grok/bin:$PATH"
fi
