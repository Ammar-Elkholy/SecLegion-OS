
# --- Interactive Fastfetch Banner (SecLegion OS) ---
if [[ $- == *i* ]] && [[ -z "$FASTFETCH_SHOWN" ]]; then
    export FASTFETCH_SHOWN=1
    command -v fastfetch &>/dev/null && fastfetch
fi
