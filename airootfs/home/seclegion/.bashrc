#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

alias ls='ls --color=auto'
alias grep='grep --color=auto'
PS1='[\u@\h \W]\$ '

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
        local rand_idx=$(( RANDOM % count ))
        fastfetch --logo-type file --logo "${available_logos[$rand_idx]}" "${ff_opts[@]}"
    elif [[ -f "$main_logo" ]]; then
        fastfetch --logo-type file --logo "$main_logo" "${ff_opts[@]}"
    else
        fastfetch "${ff_opts[@]}"
    fi
}

if [[ $- == *i* ]]; then
    seclegion_fastfetch
fi
