if [ -r "$HOME/.env" ]; then
  set -a
  . "$HOME/.env"
  set +a
fi

# Editors
if type -P zed >/dev/null 2>&1; then
  export VISUAL=zed
fi

if type -P nvim >/dev/null 2>&1; then
  export EDITOR=nvim
elif type -P vim >/dev/null 2>&1; then
  export EDITOR=vim
elif type -P nano >/dev/null 2>&1; then
  export EDITOR=nano
fi

export VISUAL="${VISUAL:-$EDITOR}"

# zeditor, fff-mcp
if [ -d "$HOME/.local/bin" ] && find "$HOME/.local/bin" -mindepth 1 -maxdepth 1 -type f -perm -u=x | read -r _; then
  case ":$PATH:" in
    *:"$HOME/.local/bin":*) ;;
    *) PATH="$HOME/.local/bin:$PATH" ;;
  esac
fi

#export PATH="$HOME/.atuin/bin:$HOME/.local/bin:$PATH"
#command -v atuin >/dev/null && eval "$(atuin init bash)"

# Ensure base system paths exist.
case ":$PATH:" in
  *:/usr/bin:*) ;;
  *) PATH="/usr/local/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" ;;
esac

# PostgreSQL 17
if [ -d /opt/postgresql17/bin ]; then
  case ":$PATH:" in
    *":/opt/postgresql17/bin:"*) ;;
    *) export PATH="/opt/postgresql17/bin:$PATH" ;;
  esac
fi

# Rust
if command -v cargo >/dev/null 2>&1 || [ -d "$HOME/.cargo" ] || [ -d "$HOME/.rustup" ]; then
  export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
  export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
  export RUST_BACKTRACE="${RUST_BACKTRACE:-1}"
  export CARGO_REGISTRIES_CRATES_IO_PROTOCOL="${CARGO_REGISTRIES_CRATES_IO_PROTOCOL:-sparse}"

  case ":$PATH:" in
    *:"$CARGO_HOME/bin":*) ;;
    *) PATH="$CARGO_HOME/bin:$PATH" ;;
  esac

  mkdir -p "$CARGO_HOME" "$RUSTUP_HOME"
fi

# Go
if command -v go >/dev/null 2>&1 || [ -d "$HOME/go" ]; then
  export GOPATH="$HOME/go"
  export GOTMPDIR="${GOTMPDIR:-$HOME/go/tmp}"
  export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
  export GOMODCACHE="${GOMODCACHE:-$GOPATH/pkg/mod}"

  case ":$PATH:" in
    *:"$GOPATH/bin":*) ;;
    *) PATH="$GOPATH/bin:$PATH" ;;
  esac

  mkdir -p "$GOTMPDIR" "$GOCACHE" "$GOMODCACHE"
fi

# Node
NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"

if [ -s "$NVM_DIR/nvm.sh" ]; then
  export NVM_DIR
  . "$NVM_DIR/nvm.sh"
fi

# Grok CLI
if [ -d "$HOME/.grok/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.grok/bin:"*) ;;
    *) export PATH="$HOME/.grok/bin:$PATH" ;;
  esac
fi

# D-Bus session bus for dinit-managed sessions.
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export XDG_RUNTIME_DIR
fi

if [ -S "${XDG_RUNTIME_DIR}/bus" ] && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
  export DBUS_SESSION_BUS_ADDRESS
fi
