# ==============================================================================
# OffSec Operator Zsh Configuration
# Arch Linux — Cyber Security & Penetration Testing Environment
# ==============================================================================

# --- Environment & Path ---
export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/bin:$PATH"
export EDITOR="nano"
export VISUAL="nano"

# --- History Configuration ---
HISTFILE="$HOME/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_VERIFY
setopt SHARE_HISTORY
setopt AUTO_CD

# --- Starship Prompt Initialization ---
if command -v starship &>/dev/null; then
    eval "$(starship init zsh)"
fi

# --- Zsh Syntax Highlighting & Autosuggestions ---
if [[ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
fi
if [[ -f /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
    source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# --- FZF (Fuzzy Finder) Keybindings & Completion ---
if [[ -f /usr/share/fzf/key-bindings.zsh ]]; then
    source /usr/share/fzf/key-bindings.zsh
fi
if [[ -f /usr/share/fzf/completion.zsh ]]; then
    source /usr/share/fzf/completion.zsh
fi

# --- Zoxide (Smarter cd command) ---
if command -v zoxide &>/dev/null; then
    eval "$(zoxide init zsh)"
fi

# --- Modern CLI Suite Aliases ---
if command -v eza &>/dev/null; then
    alias ls='eza --icons --group-directories-first'
    alias ll='eza -la --icons --git --group-directories-first'
    alias la='eza -a --icons --group-directories-first'
    alias lt='eza --tree --icons --level=2'
    alias tree='eza --tree --icons'
else
    alias ls='ls --color=auto'
    alias ll='ls -lah --color=auto'
fi

if command -v bat &>/dev/null; then
    alias cat='bat --style=plain --paging=never'
    alias bat='bat'
fi

if command -v btop &>/dev/null; then
    alias top='btop'
fi

# --- System & Navigation Aliases ---
alias grep='grep --color=auto'
alias df='df -hT'
alias free='free -h'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias mkdir='mkdir -pv'
alias reload='source ~/.zshrc'

# --- Pentest & CTF Target / VPN Utilities ---
target() {
    if [[ -z "${1:-}" ]] || [[ "$1" == "clear" ]]; then
        rm -f /tmp/target_ip
        unset TARGET_IP
        echo -e "\033[1;33m[!] Target IP cleared.\033[0m"
    else
        echo "$1" > /tmp/target_ip
        export TARGET_IP="$1"
        echo -e "\033[1;32m[+] Target locked: $1\033[0m (saved to /tmp/target_ip and \$TARGET_IP)"
    fi
}

vpn() {
    echo -e "\033[1;34m=== ACTIVE VPN INTERFACES ===\033[0m"
    local interfaces=$(ip -4 -br addr show | grep -E 'tun|wg|tap')
    if [[ -n "$interfaces" ]]; then
        echo "$interfaces"
    else
        echo -e "\033[1;33m[!] No active tun0/wg0 interface found.\033[0m"
    fi
}

myip() {
    echo -e "\033[1;36mLocal LAN IP:\033[0m $(ip -4 addr show scope global | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)"
    local vpn_ip=$(~/.local/bin/get_vpn_ip.sh 2>/dev/null)
    if [[ -n "$vpn_ip" ]]; then
        echo -e "\033[1;32mActive VPN IP (tun0/wg0):\033[0m $vpn_ip"
    fi
}

# --- Interactive Session Startup Banner ---
if [[ -o interactive ]] && [[ -z "${FASTFETCH_SHOWN:-}" ]]; then
    export FASTFETCH_SHOWN=1
    if command -v fastfetch &>/dev/null; then
        fastfetch
    fi
fi


# --- First Login SecLegion Setup Wizard ---
if [[ -o interactive ]] && [[ ! -f "$HOME/.config/.ae-welcome-done" ]] && [[ -t 0 ]]; then
    if [[ -x "$HOME/.config/hypr/scripts/ae-welcome.sh" ]]; then
        "$HOME/.config/hypr/scripts/ae-welcome.sh"
    fi
fi
