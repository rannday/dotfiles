command -v starship >/dev/null 2>&1 && eval "$(starship init bash)"

command -v zoxide   >/dev/null 2>&1 && eval "$(zoxide init bash --cmd cd)"

if [[ -x "$HOME/.atuin/bin/atuin" ]]; then
    [[ -f "$HOME/.atuin/bin/env" ]] && . "$HOME/.atuin/bin/env"
    [[ -f "$HOME/.bash-preexec.sh" ]] && source "$HOME/.bash-preexec.sh"
    eval "$("$HOME/.atuin/bin/atuin" init bash)"
fi
