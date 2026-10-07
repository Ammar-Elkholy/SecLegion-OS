#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="SecLegion-OS"
iso_label="SECLEGION_$(date +%Y%m)"
iso_publisher="SecLegion OS <https://github.com/aelkholy/SecLegion-OS>"
iso_application="SecLegion OS Live & Installer"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
build_modes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito' 'uefi-ia32.systemd-boot.esp' 'uefi-x64.systemd-boot.esp' 'uefi-ia32.systemd-boot.eltorito' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/bin/seclegion-bootstrap-tier2.sh"]="0:0:755"
)
