#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# shellcheck disable=SC2034

iso_name="seclegion"
iso_label="SECLEGION_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="SecLegion OS contributors"
# DEV BUILD marker: drop it only for a signed release.
iso_application="SecLegion OS Live/Install (DEV BUILD)"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="seclegion"
# UEFI only, booted by GRUB. No BIOS mode and no systemd-boot.
bootmodes=('uefi.grub')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86,arm64' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
kernel_params_aarch64="clk_ignore_unused pd_ignore_unused arm64.nopauth"
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers.d"]="0:0:750"
  ["/etc/sudoers.d/10-seclegion-live"]="0:0:440"
  ["/home/seclegion-live"]="1000:1000:750"
  ["/home/seclegion-live/.config"]="1000:1000:750"
  ["/home/seclegion-live/.config/hypr"]="1000:1000:750"
  ["/home/seclegion-live/.config/hypr/hypridle.conf"]="1000:1000:640"
  ["/home/seclegion-live/.config/hypr/user.lua"]="1000:1000:640"
  ["/root"]="0:0:750"
  ["/root/.gnupg"]="0:0:700"
  ["/usr/share/seclegion/kiosk/run"]="0:0:755"
  ["/usr/share/seclegion/kiosk/error"]="0:0:755"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/bin/seclegion-selftest"]="0:0:755"
  ["/usr/local/bin/seclegion-live-session"]="0:0:755"
  ["/usr/local/bin/hyprlock"]="0:0:755"
)
