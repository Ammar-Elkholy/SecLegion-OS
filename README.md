# SecLegion OS

A personal Arch-based security workstation, in the spirit of Omarchy. Hyprland is the only session, the
installer is archinstall underneath, and every package comes from the official Arch repositories or the
project's own signed `[seclegion]` repo: no third-party repos, no telemetry.

**Status: 1.0 (ISO #11, 2026-10-31).** Progress meter 81% (1.0 = 80%, perfected = 100%). All 36 VM gates
pass on this ISO; results are in [TESTING.md](TESTING.md), current work in [docs/STATUS.md](docs/STATUS.md).

## Download

- **ISO (one file, Google Drive):**
  https://drive.google.com/file/d/1GwBHFBnmCiHaOUqgsTNOkrvhYSPKD5RY/view
- sha256 `7fe0becda986554cc45398213286843acd03430ffe2d693d6e36fe3d86b47771` (check with `sha256sum`)
- The same ISO is in the GitHub release `iso11-2026.10.31` as three parts; `JOIN.txt` there joins them.

Flash it (replace `/dev/sdX` with the USB stick shown by `lsblk`; everything on it is erased):

```
sudo dd if=seclegion-2026.10.31-x86_64.iso of=/dev/sdX bs=4M oflag=direct conv=fsync status=progress
```

Then follow [docs/USB-MIGRATION.md](docs/USB-MIGRATION.md) (Windows prep, firmware, live checks, install).
After installing, [docs/NEXT-ON-NEW-OS.md](docs/NEXT-ON-NEW-OS.md) lists the hardware checks and the work left.

## What you get

- **Desktop:** Hyprland with waybar, swaync, hyprlock/hypridle, a theme engine (`seclegion-theme`), a GTK4
  Settings app and the `seclegion-set` CLI. Login through greetd + regreet. `Super+/` shows every keybind.
- **Installer:** a GUI (English and Arabic) over archinstall. Erase the disk, install alongside Windows in
  free space, or partition manually. Optional LUKS encryption.
- **System:** systemd-boot with a unified kernel image, btrfs subvolumes with snapper snapshots and
  rollback (`seclegion-rescue`), ufw on, sshd off, a first-boot wizard and hardware detection for
  hybrid AMD/NVIDIA laptops.
- **Security tools:** a curated catalog (nmap, masscan, tcpdump, wireshark, hashcat, john, hydra,
  impacket, responder, gobuster, ffuf, nikto, exploitdb, …); see [docs/security-tools.md](docs/security-tools.md).
- **Opt-in extras:** KVM/libvirt labs with NAT and isolated networks (`seclegion-virt`), local AI
  through ollama, off by default (`seclegion-ai`), gaming with multilib and Steam (`seclegion-gaming`).
  Vendor apps (Brave, VS Code, Claude) are fetched on first boot, never shipped.

## Repository layout

| Path | Contents |
|---|---|
| `pkgs/` | PKGBUILDs for the `seclegion-*` packages, built and signed into the local `[seclegion]` repo |
| `iso/` | archiso profile, package lists, GRUB theme |
| `installer/` | archinstall configurator, post-install, GUI and schemas |
| `desktop/` | Hyprland, waybar, swaync and theme components |
| `tools/` | build, theme, settings, evidence and progress tools |
| `tests/` | pytest: unit tests by default, QEMU/OVMF VM gates marked `iso` |

## Building

```
make bootstrap   # .venv with pytest, ruff, reuse, shellcheck (no root)
make lint        # shellcheck, ruff, reuse, container-start check
make test        # unit tests
tools/build-iso  # build the packages, then the ISO, in a container -> out/
make evidence    # regenerate and verify TESTING.md
tools/seclegion-progress --all
```

The ISO build needs the `docker` group and 25 GiB free on a Linux filesystem under `/var/tmp`. VM gates
need QEMU with edk2-ovmf: `SECLEGION_ISO=out/<iso> .venv/bin/python -m pytest -m iso tests/install`.
See [docs/testing.md](docs/testing.md).

## Licence

MIT, see [LICENSE](LICENSE). Per-file licences are tracked with REUSE ([docs/PROVENANCE.md](docs/PROVENANCE.md)).
The SecLegion branding images are all rights reserved until a licence is chosen.
