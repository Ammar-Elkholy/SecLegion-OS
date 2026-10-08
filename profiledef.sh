#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="SecLegion-OS"
iso_label="SECLEGION_$(date +%Y%m)"
iso_publisher="SecLegion OS <https://github.com/Ammar-Elkholy/SecLegion-OS>"
iso_application="SecLegion OS Live & Installer"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
build_modes=('iso')
bootmodes=('bios.syslinux'
           'uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers.d/seclegion"]="0:0:440"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/home/seclegion/"]="1000:1000:755"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/install"]="0:0:755"
  ["/usr/local/bin/installer"]="0:0:755"
  ["/usr/local/bin/installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/bin/seclegion-bootstrap-tier2.sh"]="0:0:755"
  ["/usr/local/bin/seclegion-gpu-run"]="0:0:755"
  ["/usr/local/bin/install-from-existing.sh"]="0:0:755"
)
