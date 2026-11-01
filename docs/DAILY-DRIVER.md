<!-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors -->
<!-- SPDX-License-Identifier: MIT -->
# Daily-driver bar (migration milestone 1)

Written 2026-10-28 against `f9ff269`. Goal: the owner moves to a new laptop that dual-boots Windows 11
and SecLegion OS, and keeps developing SecLegion (and other projects) on SecLegion. The old laptop stays
untouched as the fallback.

**New laptop: Lenovo Legion Slim 5 16AHP9.** Ryzen 7 8845HS (Zen 4, Radeon 780M iGPU `1002:1900`), RTX 4060
Laptop (Ada, nvidia-open), hybrid graphics with a MUX (firmware GPU mode: Hybrid / Discrete). Still unknown
until a live boot: Wi-Fi chip (this model ships MediaTek or Realtek, both mainline), audio amp, panel mode,
RAM and disk. `lspci -nnk` and `seclegion-hwreport` from the live USB answer them.

What the repo already covers for it: hwdetect's AMD-iGPU + NVIDIA hybrid path
(fixture `hw/fixtures/amd-gtx1650`: gpu-amd, nvidia-open, hybrid-offload, nvidia-prime,
`AQ_DRM_DEVICES` iGPU first, `nvidia-drm.modeset=1`). The RTX 4060 IDs are in `hw/nvidia-table.toml`.
None of it has run on metal.

## The bar
A row passes only when its check passes on the new laptop: in milestone 3 from a live USB/SSD, in
milestone 5 again on the installed system. "Repo" is what the repo has today.

- **B1 Boots.** PASS: UEFI boots the UKI to regreet; `bootctl status` shows it.
  Repo: VM only. Secure Boot is planned for 1.4, so it must be off.
- **B2 Display/GPU.** PASS, in Hybrid mode: Hyprland runs on the 780M; `hyprctl monitors` shows the
  panel's native mode and refresh; `vulkaninfo --summary` lists both GPUs; `prime-run glxinfo -B` reports
  the RTX 4060; `nvidia-smi` works; the dGPU drops to D3 when idle
  (`cat /sys/bus/pci/devices/0000:01:00.0/power/runtime_status` = suspended). HDMI and USB-C outputs
  hotplug (on Legions HDMI is often wired to the dGPU). Repeat in Discrete mode: one GPU, Hyprland on
  NVIDIA. Repo: the hybrid rules above. Never run on metal.
- **B3 Wi-Fi, Bluetooth.** PASS: `nmcli dev wifi connect …` works and reconnects after resume;
  `bluetoothctl` pairs. Repo: linux-firmware, NetworkManager, bluez. No per-chip rules.
- **B4 Audio, mic, webcam, keys.** PASS: `wpctl status` lists sinks and sources; both speakers play
  (Legion amps sometimes need a kernel quirk); mic records; webcam shows in `v4l2-ctl --list-devices`;
  brightness, volume, keyboard-backlight and Fn+Q keys work. Repo: sof-firmware, pipewire, swayosd.
- **B5 Suspend, lid, battery.** PASS: 3× `systemctl suspend` and a lid close resume with Wi-Fi, both
  GPUs and the lock screen. Hawk Point has s2idle only (`cat /sys/power/mem_sleep` = `[s2idle]`).
  NVIDIA needs `nvidia-suspend`/`nvidia-resume` enabled and `PreserveVideoMemoryAllocations: 1` in
  `/proc/driver/nvidia/params`. Battery drain over 8 h of suspend is under 10%. `powerprofilesctl` switches
  the Lenovo platform profile. Repo: logind lid/idle settings, tested as files only; NVIDIA
  suspend rule in hwdetect (gap 1), not
  applied yet (gap 1b).
- **B1b Dual boot with Windows 11.** PASS: the alongside install leaves Windows booting unchanged
  (BitLocker unlocks without asking for the recovery key); both OSes appear in the firmware boot menu or
  in one boot menu; Windows clock and SecLegion clock agree after switching; SecLegion can read the
  Windows NTFS partition when Windows fast startup is off. Repo: alongside mode passes in a VM (I3), but it
  creates its own ESP and adds no Windows entry (open owner decision); U3 dual-boot guide and NTFS
  fixtures exist. Never run next to a real BitLocker-protected Windows.
- **B6 Encryption.** PASS: `lsblk -f` shows crypto_LUKS under btrfs; the passphrase is asked at boot.
  Repo: erase-luks passes in a VM (I3). TPM unlock is 1.4 and not needed.
- **B7 Rollback.** PASS: `snapper list` has pre/post pairs; `seclegion-rescue rollback N` boots N.
  Repo: **V2 WIP, unverified.**
- **B8 Updates.** PASS: `sudo pacman -Syu` exits 0. Repo: interim done (D-UPD-1): the installed
  [seclegion] section is commented out; `pacman -Syu` needs the network (VM-unverified).
- **B9 Browser.** PASS: Firefox (and Brave) log in and play video. Repo: Firefox installed;
  `seclegion-brave-fetch`.
- **B10 git, ssh, gpg.** PASS: `git --version`, `ssh -T git@<host>`, `gpg -K`. Repo: git, openssh
  (client), gnupg in post-packages.list (gap 2; VM gate owed).
- **B11 Docker.** PASS: `docker run --rm hello-world` as the user (docker group) with ufw on.
  Repo: docker in post-packages.list, service enabled, user in the docker group (gap 2; VM gate owed).
- **B12 Claude Code + Claude desktop.** PASS: `claude --version`; the desktop app opens and signs in.
  Repo: `claude` ships through `seclegion-claude-fetch` (gap 5); the desktop app does not (see gap 5).
  Old laptop: native `~/.local/bin/claude` 2.1.302, foreign package
  `claude-desktop` 4.29.0-1.
- **B13 SecLegion toolchain.** PASS: `make bootstrap && pytest -q`, `tools/build-iso`, one `-m iso`
  VM gate. Repo: base-devel, docker, socat installed (gap 2); qemu/ovmf/swtpm only with the virt opt-in.
- **B14 VMs (ws2019).** PASS: `virsh -c qemu:///session start ws2019` boots. Repo: seclegion-virt is
  opt-in (V1 doing).
- **B15 Editor.** PASS: VS Code opens the repo. Repo: `seclegion-vscode-fetch`.
- **B16 Work leaves the device.** PASS: every repo has a pushed remote and a backup target exists.
  Repo: **no git remote has ever been set** (owner decision).

## Gaps, in priority order
P0 blocks living on it; P1 is needed before the old laptop retires; P2 can follow.

1. **P0 Legion Slim 5 hwdetect fixture** (agent, 1 session): `hw/fixtures/legion-slim5-16ahp9` from the
   780M + RTX 4060 IDs (Hybrid and Discrete variants), plus an NVIDIA suspend rule (services enabled,
   video memory preserved) if Arch's nvidia-utils does not already do it. Refresh the fixture from the
   real `/sys` after the live boot. Covers B2, B5.
   **Repo done (merge of 62faad0):** fixtures `legion-slim5-16ahp9-{hybrid,discrete}` (dGPU `10de:28e0`);
   the NVIDIA rules add `nvidia-suspend/-resume/-hibernate.service` (new plan key `services`) and
   `nvidia.NVreg_PreserveVideoMemoryAllocations=1`. **But nothing applies the plan yet** (gap 1b).
1b. **P0 Apply the hwdetect plan at install** (agent): `seclegion-post` runs hwdetect and installs the
   plan's `packages`, adds `kernel_params` to `/etc/kernel/cmdline`, enables `services`, writes `env`.
   Today hwdetect only prints the plan (gaming.py reads it for the opt-in set), so the Legion would boot
   without the NVIDIA driver or `AQ_DRM_DEVICES`. Covers B2, B5.
   **Repo done (merge 821463f):** `installer/installd/hwplan.py`; packages join the one `pacman -S`,
   params go to `/etc/kernel/cmdline` (one `mkinitcpio -P`), services enabled, env in
   `/etc/environment.d/50-seclegion-hw.conf`; a failing hwdetect only warns. `AQ_DRM_DEVICES` uses
   colon-free udev links `/dev/dri/seclegion-{igpu,dgpu}` (merge 30b0ab2). VM gate owed.
2. **P0 Dev profile** (agent, 1 session): git, openssh (client; sshd units stay masked), gnupg,
   base-devel, docker + user in the docker group, socat, virt opt-in with KVM/libvirt groups.
   Covers B10, B11, B13, B14. **Repo done, VM gate owed:** plain entries in `post-packages.list`
   (no meta package); git/base-devel/docker/socat in `iso/packages/cache.list`, openssh and gnupg
   reach the cache as dependencies (gcr-4, pacman). post enables `docker.service` and runs
   `usermod -a -G docker <user>`; the sshd units stay masked (unit tests in `tests/install/test_post.py`).
   The virt groups come from `seclegion-virt-setup` (V1). Owed: `-m iso -k i2_run` on a new ISO.
   `tools/check-container-start` now reads a `*.list` line that is only an engine's name as a package
   entry (it still flags any other text there); Python names the engine in pieces, like its tests do.
3. **P0 Updates** (owner decides, agent builds, 1 session): a hosted [seclegion] URL, or an interim that
   keeps `pacman -Syu` green until it exists. Covers B8.
   Interim done (D-UPD-1): the installed `[seclegion]` section is commented out; core/extra updates work.
4. **P0 Bar check script** (agent, 1 session; commit 59a1e1e on branch
   `worktree-agent-a4fc44cac83d929bc`, to review): runs the non-interactive checks of B1–B13, prints
   PASS/FAIL per row, safe on a live USB. Milestones 3 and 5 run it.
5. **P0 Claude Code + Claude desktop** (agent, 1 session): fetchers in the vscode/brave pattern, no
   third-party repo. Covers B12.
   **Repo done (Claude Code), VM gate owed:** `seclegion-claude-fetch` pins Claude Code 2.1.308 (Anthropic's
   `stable` channel; linux-x64 sha256 from the release `manifest.json`, whose GPG signature was verified
   against Anthropic's published key). The fetched binary goes to `/opt/claude-code/claude`;
   `/usr/bin/claude` is a wrapper that turns Claude Code's own updater off (`DISABLE_AUTOUPDATER`,
   `DISABLE_UPDATES`). Registered in post-packages.list, first boot, the welcome app and `tools/vendor-bump`.
   **Claude desktop: not added (owner decision).** Anthropic publishes an official Linux build, but only as a
   beta `.deb` for Debian 12+/Ubuntu 22.04+ (apt repository `downloads.claude.ai/claude-desktop/apt/stable`
   or a pool `.deb`; its apt `Packages` index lists a sha256 per file). Their page
   (code.claude.com/docs/en/desktop-linux) says Arch is unsupported and to use the CLI there. Using it would
   mean unpacking a Debian package into a local PKGBUILD, which is a repack of a build made for another
   distribution, so nothing was added. If the owner accepts that, it is one more fetcher (version
   `1.17282.0`, amd64, was the newest in the Packages index when checked).
6. **P0 Secure Boot off** (owner, firmware setting) until the 1.4 Secure Boot wizard. Covers B1.
   With Windows 11 this matters: BitLocker/device encryption is bound to Secure Boot through the TPM, so
   turning it off makes Windows ask for the recovery key. Before any firmware change, save the BitLocker
   recovery key (account.microsoft.com/devices/recoverykey, or `manage-bde -protectors -get C:`) and
   suspend BitLocker for the change. Pulling the Secure Boot wizard forward from 1.4 is the alternative.
7. **P0 Dual-boot chainload entry + drill** (agent, 1 session; branch `worktree-agent-a217d37ad377b7041`,
   to review). Owner decision 2026-10-28: SecLegion keeps
   its own ESP; its systemd-boot menu gets a Windows Boot Manager entry; the Windows ESP is never written.
   Constraint: systemd-boot loads EFI binaries only from its own ESP/XBOOTLDR. Preferred design: an entry
   that starts `edk2-shell` (extra) with a script that finds the Windows ESP by its PARTUUID and runs
   `\EFI\Microsoft\Boot\bootmgfw.efi`. Rejected: copying `EFI/Microsoft` (goes stale on Windows updates).
   Fallback that always works: the firmware boot menu (F12).
   Status: the entry is built (`installer/installd/winboot.py`, called from `seclegion-post` in alongside
   mode only; the script matches the file, not the PARTUUID, see `docs/dual-boot.md`). Unit-tested, and
   the script was run in QEMU/OVMF behind real systemd-boot against a stand-in Windows ESP. The I3
   alongside VM test checks the entry. Open: the Windows 11 + TPM + BitLocker drill below.
   Then a VM drill with Windows 11 + TPM + BitLocker:
   shrink, alongside install, both OSes boot, BitLocker does not prompt. Owner prep on the laptop: Windows
   fast startup off, shrink C: in Disk Management, Windows RTC to UTC
   (`RealTimeIsUniversal`). Covers B1b.
8. **P1 Finish V2** rollback (in progress) and build ISO #7. Covers B7.
9. **P1 Git remote / backup target** for all repos (owner decision). Covers B16.
10. **P1 Docker under ufw** (agent, small): published ports and build networking verified in a VM.
    Status: coded (D-DKR-1): `seclegion-post` appends a `DOCKER-USER` block to ufw's `after.rules` and
    `after6.rules`, so published ports are closed until `ufw route allow`. VM gate `M7a-docker-ufw`
    (rules and docker service; an actual published-port probe from the LAN is still open).
11. **P2 Lenovo extras:** battery conservation mode (`ideapad_laptop` `conservation_mode`) as a Settings
    toggle; Fn+Q power mode shown in waybar.
    Status: coded, not yet run on the Legion. Settings > Power toggle writes `conservation_mode` through a
    wheel udev rule (seclegion-settings); waybar shows the profile with its native `power-profiles-daemon`
    module (D-Bus, so Fn+Q shows at once).
12. **P2** CP-C installed-desktop checkpoint; Waybar tray hang; no sync DBs until the first `-Sy`;
    regreet Session row (accepted, D-GRT-1).

### Owner-reported (2026-10-30, seen on the current laptop OS; SecLegion must not repeat them)
13. **P1 System monitor shows no GPU.** The waybar `custom/sl-gpu` reads only amdgpu `card1`
    `gpu_busy_percent`, so the RTX 4060 (and any card that is not card1) never shows. Wanted: a SecLegion
    system monitor app (CPU, memory, disk, network, every GPU: iGPU + NVIDIA via `nvidia-smi` when present,
    temps, processes), opened from the waybar stats group.
    *Partial (2f08d28):* the waybar GPU module now shows every GPU. The GTK4 monitor app is lane L5b.
14. **P1 Fn+F7 (projection) stops working after HDMI use.** The display-switch key must always open a
    SecLegion display menu (laptop only / extend / mirror / external only), before and after hotplug.
    *Open:* lane L4 (owner check first: which key does `wev` see on Fn+F7?).
15. **P0 Workspaces 6+ stay stuck on an unplugged monitor.** After HDMI is removed, opening workspace 6+
    behaves as if the external screen were still there. On monitor removal every workspace must move to
    the remaining monitor; on re-plug the 6+ split may return.
    *Fixed in code (621199a), needs ISO #10 + a real unplug:* `seclegion-displayd` clears the ghost monitor.
16. **P1 External monitor gets the stock Hyprland wallpaper.** The SecLegion background must apply to
    every monitor, including one plugged in later.
    *Fixed in code (e4bc310), needs ISO #10:* `seclegion-wallpaper` paints every output, also on hotplug.
17. **P1 One SecLegion Wi-Fi module.** Today Wi-Fi connect/disconnect (nm-applet) and the speed readout
    are separate, and the speed reads far below the real rate. Wanted: one waybar module with an accurate
    up/down rate and a SecLegion Wi-Fi panel (scan, connect, forget, disconnect, hidden networks).
    *Partial (2f08d28):* the speed is now in bits/s (it read bytes). One module + panel is lane L6.
18. **P1 Settings app with full control.** seclegion-settings must work like macOS System Settings or
    Omarchy: every page changes the setting itself, with no commands shown for the user to run.
    *Open:* lanes L3a (privileged backend), L3b (UI), L7 (Displays page).

Not gaps: TPM2/FIDO2 unlock (the passphrase is fine).

## Found outside STATUS.md (for milestone 4)
- ws2019 is a `qemu:///session` libvirt VM: disk `/mnt/Dev_Lab/VMs/ws2019/ws2019.qcow2`, domain
  `~/.config/libvirt/qemu/ws2019.xml`, plus `~/VMs/ws2019` and `~/.ws2019.draft.txt`.
  System libvirt also has `vuliux` (shut off).
- `/mnt/Dev_Lab/SecLegion-OS/SecLegion-OS-new/` is an untracked copy of the repo inside the checkout.
  It makes `make lint` red (reuse, check-container-start) until it is moved out.
