#!/usr/bin/env bash
# ==============================================================================
# seclegion-gpu.sh — Dynamic Multi-GPU & Hardware Acceleration Engine
# SecLegion OS | Supports: Intel, AMD Radeon, NVIDIA Dedicated & Hybrid Laptops
# ==============================================================================

# 1. Dynamic DRM Card Assignment (Hyprland / Aquamarine)
if [ -d /dev/dri ]; then
    cards=($(ls -1 /dev/dri/card* 2>/dev/null | sort))
    if [ ${#cards[@]} -gt 1 ]; then
        primary_card=""
        for card in "${cards[@]}"; do
            card_name=$(basename "$card")
            if grep -q "^connected" /sys/class/drm/${card_name}-*/status 2>/dev/null; then
                primary_card="$card"
                break
            fi
        done
        if [ -n "$primary_card" ]; then
            secondary_card=""
            for card in "${cards[@]}"; do
                if [ "$card" != "$primary_card" ]; then
                    secondary_card="$card"
                    break
                fi
            done
            if [ -n "$secondary_card" ]; then
                export AQ_DRM_DEVICES="${primary_card}:${secondary_card}"
            else
                export AQ_DRM_DEVICES="${primary_card}"
            fi
        fi
    elif [ ${#cards[@]} -eq 1 ]; then
        export AQ_DRM_DEVICES="${cards[0]}"
    fi
fi

# 2. Hardware VA-API / Video Acceleration Drivers Auto-detection
if lspci 2>/dev/null | grep -E "(VGA|3D)" | grep -iq "nvidia"; then
    export NVD_BACKEND="direct"
    export ELECTRON_OZONE_PLATFORM_HINT="auto"
elif lspci 2>/dev/null | grep -E "(VGA|3D)" | grep -iq "amdgpu\|radeon"; then
    export LIBVA_DRIVER_NAME="radeonsi"
    export VDPAU_DRIVER="radeonsi"
elif lspci 2>/dev/null | grep -E "(VGA|3D)" | grep -iq "intel\|iris"; then
    export LIBVA_DRIVER_NAME="iHD"
fi
