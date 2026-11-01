<!-- SPDX-License-Identifier: MIT -->
# Continuing on the new SecLegion install

The work below is what is left after ISO #11. Each item can be done from the installed SecLegion OS itself.

## 1. Get the ISO and install
1. Download the three parts from the GitHub release and join them:
   `cat seclegion-*.iso.part-* > seclegion.iso && sha256sum -c SHA256SUMS`.
2. Flash and install by following `docs/USB-MIGRATION.md` (Windows prep, firmware, flash, live tests, install).
3. After the first login: `git clone git@github.com:Ammar-Elkholy/SecLegion-OS.git`, check out
   `clean-room-rebuild`, run `make bootstrap` (creates `./.venv`), then `make lint` and
   `.venv/bin/python -m pytest -q` to confirm the dev setup.

## 2. Hardware checks only real metal can answer (about 30 min)
- HDMI: plug and unplug an external display, then run `hyprctl monitors all`. Is a ghost monitor left?
- Fn+F7: run `wev` and press it. Which key arrives? (The display menu is bound to XF86Display and SUPER+SHIFT+P.)
- Wi-Fi: compare the bar's bits/s with a known transfer.
- dGPU on battery: `cat /sys/bus/pci/devices/<dGPU>/power/runtime_status` should reach `suspended`.
- The udev GPU links `/dev/dri/seclegion-{igpu,dgpu}` exist and Hyprland uses the iGPU.
- Suspend and resume lock the screen (hyprlock), and SUPER+L locks.

## 3. Development work left for 1.0 polish (agent work, about 8-12 h)
- W1 VM half: a key-matrix test over QMP on the installed base (every shipped bind does what it says).
- RL1: hosted `[seclegion]` repo on GitHub Releases. You generate the release signing key offline
  (D-RL1, never in git); the G75 reproducibility test then runs with an ephemeral key.
- CP-C GUI rows: S1-kiosk-ara (Arabic installer kiosk), M5-gui-ocr and M5-ara (installer GUI OCR checks).
- Follow-up: snapperd may cache NUMBER_LIMIT after the Settings snapshot-count change (check in a VM).
- Not yet seen on metal: pkexec with the /run polkit rule, GTK under cage as the installer user, and the
  hwdetect choice of nvidia-open for linux-lts.

## 4. Later (1.1)
CP-D, CP-G, S1, U2-U4, V1, CP-E (see `docs/progress.toml`, `tools/seclegion-progress --all`).

## Your decisions still open
- Ship your "Seclegion Wallpaper.png" as `default.png` instead of the generated gradient? (licence call)
- Branding licence (D-BR-1: all rights reserved until you pick one).
