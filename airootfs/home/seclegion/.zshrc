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

# --- SecLegion OS Context-Aware Fastfetch Banner ---
seclegion_fastfetch() {
    if ! command -v fastfetch &>/dev/null; then
        return
    fi

    local logo_dir="$HOME/.config/fastfetch/seclegion_logos"
    local main_logo="$logo_dir/design_13.txt"
    local greet_marker="/tmp/.seclegion_boot_greet_${UID:-$(id -u)}"

    # Responsive layout: If terminal is narrow (< 75 columns), display logo on top
    local term_cols=$(tput cols 2>/dev/null || echo 80)
    local ff_opts=("--disable-linewrap" "true")
    if [[ "$term_cols" -lt 75 ]]; then
        ff_opts+=("--logo-position" "top")
    fi

    # First terminal/login of the session: ALWAYS display Design 13 (Main Logo with Slogan)
    if [[ ! -f "$greet_marker" ]]; then
        touch "$greet_marker" 2>/dev/null
        if [[ -f "$main_logo" ]]; then
            fastfetch --logo-type file --logo "$main_logo" "${ff_opts[@]}"
            return
        fi
    fi

    # Subsequent tab, window, or tmux split: Randomly select from ALL 6 designs (INCLUDING Design 13!)
    local all_logos=(
        "$logo_dir/design_11.txt"
        "$logo_dir/design_13.txt"
        "$logo_dir/design_15.txt"
        "$logo_dir/design_21.txt"
        "$logo_dir/design_24.txt"
        "$logo_dir/design_27.txt"
    )
    local available_logos=()
    for l in "${all_logos[@]}"; do
        [[ -f "$l" ]] && available_logos+=("$l")
    done

    if [[ ${#available_logos[@]} -gt 0 ]]; then
        local count=${#available_logos[@]}
        local rand_idx=$(( (RANDOM % count) + 1 ))
        fastfetch --logo-type file --logo "${available_logos[$rand_idx]}" "${ff_opts[@]}"
    elif [[ -f "$main_logo" ]]; then
        fastfetch --logo-type file --logo "$main_logo" "${ff_opts[@]}"
    else
        fastfetch "${ff_opts[@]}"
    fi
}

if [[ -o interactive ]] 2>/dev/null || [[ $- == *i* ]]; then
    seclegion_fastfetch
fi
