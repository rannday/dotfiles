export HISTSIZE=200000
export HISTFILESIZE=400000
export HISTCONTROL=ignoreboth:erasedups
export HISTTIMEFORMAT="%F %T "
shopt -s histappend cmdhist 2>/dev/null || true
#PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }history -a; history -c; history -r"
decl=$(declare -p PROMPT_COMMAND 2>/dev/null || true)
if [[ $decl != "declare -a PROMPT_COMMAND="* ]]; then
  if [[ -n ${PROMPT_COMMAND-} ]]; then
    PROMPT_COMMAND=("$PROMPT_COMMAND")
  else
    PROMPT_COMMAND=()
  fi
fi
for pc in "history -a" "history -c" "history -r"; do
  case " ${PROMPT_COMMAND[*]} " in *" $pc "*) ;; *) PROMPT_COMMAND+=("$pc");; esac
done
unset decl pc
