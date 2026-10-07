if command -v eza >/dev/null 2>&1; then
  alias ls='eza --icons --group-directories-first'
  alias ll='eza -alF --icons --git'
  alias la='eza -a'
  alias lt='eza -a --tree --level=2'
else
  alias ls='ls --color=auto'
  alias ll='ls -alF'
  alias la='ls -A'
fi

alias df='df -h'
alias du='du -h -d1'
alias free='free -m'
alias grep='grep --color=auto'
alias mkdir='mkdir -pv'
alias cp='cp -iv'
alias mv='mv -iv'
alias rm='rm -iv'
alias c='clear'
alias cls='clear'
#alias gh='history|grep'

if command -v btop >/dev/null 2>&1; then
  alias top='btop'
  alias htop='btop'
elif command -v htop >/dev/null 2>&1; then
  alias top='htop'
else
  alias htop='top'
fi

if command -v bat >/dev/null 2>&1; then
  alias cat='bat --paging=never --style=plain'
  alias batp='bat --paging=never --style=full --theme=TwoDark'
  alias batn='bat --paging=never --style=header,grid,numbers --theme=TwoDark'
fi

if command -v tldr >/dev/null 2>&1; then
  alias ?='tldr'
  alias tldru='tldr -u'
fi

if command -v nvim >/dev/null 2>&1; then
  alias vi='nvim'
  alias vim='nvim'
  alias view='nvim -R'
elif command -v vim >/dev/null 2>&1; then
  alias vi='vim'
  alias view='vim -R'
else
  alias vim='vi'
  alias view='vi'
fi

# Network diag
if command -v nmap >/dev/null 2>&1; then
  alias nmap-fast='nmap -T4 -F'
  alias nmap-quick='nmap -T4 -Pn'
  alias nmap-full='sudo nmap -T4 -p- -A'
  alias nmap-udp='sudo nmap -sU -T4'
  alias nmap-os='sudo nmap -O -T4'
  alias nmap-srv='sudo nmap -sV -T4'
  alias nmap-http='sudo nmap -p80,443 --script=http-enum'
fi
command -v mtr >/dev/null 2>&1 && alias trace='sudo mtr -rwzbc100'
command -v ngrep >/dev/null 2>&1 && alias ng='sudo ngrep -d any -W byline'
command -v masscan >/dev/null 2>&1 && alias masscan-fast='sudo masscan --rate 5000'
if command -v ip >/dev/null 2>&1; then
  alias ipb='ip -br a'
  alias ipp='ip -br link'
  alias ipr='ip route show'
fi
command -v ss  >/dev/null 2>&1 && alias ssu='ss -tulpn'
command -v dig >/dev/null 2>&1 && alias digg='dig +short'
command -v nc  >/dev/null 2>&1 && alias ncw='nc -vzw1'

if command -v curl >/dev/null 2>&1; then
  alias ipinfo='curl -s ipinfo.io'
  # https://github.com/chubin/wttr.in
  alias weather='curl wttr.in'
fi

# Legacy SSH when unavoidable
if command -v ssh >/dev/null 2>&1; then
  alias ssh-old='ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa -o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 -o Ciphers=+aes128-cbc,aes256-cbc,3des-cbc -o MACs=+hmac-sha1,hmac-md5'
  alias sshu='ssh-old'
fi

command -v pigz >/dev/null 2>&1 && { alias gzip='pigz'; alias gunzip='pigz -d'; }
command -v shellcheck >/dev/null 2>&1 && alias sc='shellcheck -x'
command -v duf >/dev/null 2>&1 && alias dff='duf'
command -v glances >/dev/null 2>&1 && alias gl='glances'
command -v fastfetch >/dev/null 2>&1 && alias ff='fastfetch'
command -v xclip >/dev/null 2>&1 && alias xclip='xclip -selection clipboard'
command -v fd >/dev/null 2>&1 && alias find='fd'
command -v mount >/dev/null 2>&1 && alias mounts='mount | grep -E ^/dev | column -t'
command -v tar >/dev/null 2>&1 && alias untar='tar xvf'
