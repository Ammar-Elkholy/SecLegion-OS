#!/usr/bin/env bash
# ==============================================================================
# SecLegion OS — Interactive ASCII Art Gallery Viewer (TrueColor, 30 Designs)
# ==============================================================================

CYAN="\033[38;2;0;240;255m"
GREEN="\033[38;2;0;255;136m"
WHITE="\033[38;2;255;255;255m"
BOLD="\033[1m"
RESET="\033[0m"
GALLERY="/home/aelkholy/Dev_Lab/AE_ARCH/assets/ascii_gallery"

show_menu() {
    clear
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e "${GREEN}${BOLD}   SECLEGION OS — 30 FASTFETCH ASCII LOGO DESIGNS (TRUECOLOR)${RESET}"
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e " Select a design number to preview live alongside Fastfetch metrics:"
    echo -e "   ${CYAN}[01..10]${RESET} The Glitched 'S' (Minimal, sharp, fractured, chaotic)"
    echo -e "   ${CYAN}[11..20]${RESET} Full 'SecLegion' Typography (Slant, block, shadow, inline)"
    echo -e "   ${CYAN}[21..25]${RESET} Cyber Emblems (Hexagon, shield, brackets, circuit diamond)"
    echo -e "   ${CYAN}[26..30]${RESET} The Matrix Drop (Falling binary/hex rain streaming S)"
    echo -e "   ${GREEN}[all]${RESET}    Print all 30 continuously to scroll without clearing"
    echo -e "   ${WHITE}[q]${RESET}      Quit viewer"
    echo -e "${CYAN}--------------------------------------------------------------------${RESET}"
}

preview_logo() {
    local file="$1"
    local title="$2"
    clear
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e "${GREEN}${BOLD} $title ${RESET}"
    echo -e "${CYAN}${BOLD}====================================================================${RESET}\n"
    
    python3 -c "
logo_lines = open('$file').read().splitlines()
specs = [
    '${WHITE}󰀄 USER${RESET} aelkholy@A-273',
    '${GREEN}󰣇 OS${RESET}   SecLegion OS 2026.10 (Arch Linux Base)',
    '${CYAN}󰌽 KER${RESET}  7.2.7 x86_64',
    '${WHITE}󰏗 PKG${RESET}  1330',
    '${GREEN}󰆍 TERM${RESET} kitty',
    '${CYAN}󰞷 SH${RESET}   zsh',
    '${WHITE}󰥔 UP${RESET}   4 hours, 35 mins',
    '${GREEN}󰍛 RAM${RESET}  7.6 GiB / 16.0 GiB (47%)',
    '${CYAN}󰋊 SSD${RESET}  27.1 GiB / 116.1 GiB (23%)',
    '${GREEN} ${CYAN} ${WHITE} ${GREEN} ${CYAN} ${WHITE}'
]

max_lines = max(len(logo_lines), len(specs))
for i in range(max_lines):
    l = logo_lines[i] if i < len(logo_lines) else ''
    s = specs[i] if i < len(specs) else ''
    import re
    clean_l = re.sub(r'\033\[[0-9;]*m', '', l)
    pad = ' ' * max(2, 40 - len(clean_l))
    print(f'{l}{pad}{s}')
"
    echo -e "\n${CYAN}--------------------------------------------------------------------${RESET}"
    echo -e " Source file: ${WHITE}$file${RESET}"
    echo -e "${CYAN}--------------------------------------------------------------------${RESET}"
    read -p " Press Enter to return to menu..."
}

if [[ "$1" == "all" ]]; then
    /home/aelkholy/Dev_Lab/AE_ARCH/show_all_30.sh
    exit 0
fi

while true; do
    show_menu
    read -p " Enter choice [1-30 / all / q]: " choice
    case "$choice" in
        q|Q) exit 0 ;;
        all)
            /home/aelkholy/Dev_Lab/AE_ARCH/show_all_30.sh
            read -p " Press Enter to return to menu..."
            ;;
        *)
            printf -v num "%02d" "$choice" 2>/dev/null || num=""
            match=$(ls "$GALLERY"/design_${num}.txt 2>/dev/null | head -n1 || true)
            if [[ -z "$match" ]]; then
                match=$(ls "$GALLERY"/${num}_*.txt 2>/dev/null | head -n1 || true)
            fi
            if [[ -n "$match" && -f "$match" ]]; then
                preview_logo "$match" "Design $num"
            else
                echo -e "${WHITE}Invalid selection. Enter a number between 1 and 30.${RESET}"
                sleep 1
            fi
            ;;
    esac
done
