<!-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors -->
<!-- SPDX-License-Identifier: MIT -->
# From ISO to USB to the Legion Slim 5, then moving the work over

Owner runbook for migration milestones 2-5 (`docs/DAILY-DRIVER.md`). Every command that writes a disk, a
USB stick or the firmware is the owner's: agents never run them. Rows `B1`-`B16` are the bar in
DAILY-DRIVER.md.

## 0. Ready check (do not flash before this)
- ISO #7 or later. ISO #6 boots the "Install" entry to a **placeholder** kiosk, and the installer is not
  on it, so it can only be used for the live tests in section 4. From ISO #7 the Install entry runs the
  GTK installer (package `seclegion-installer`); from Try Live, `sudo seclegion-install --answers FILE`
  is the text fallback.
- `docs/STATUS.md` says the ISO passed `-m iso -k "i2_run or i3"` (install, alongside) and the kiosk
  install gate.
- The ISO is in `/mnt/Dev_Lab/iso-artifacts/isoN/` with its `SHA256SUMS`.

## 1. Prepare Windows 11 on the Legion (in Windows, before anything else)
1. Save the BitLocker recovery key off the laptop: account.microsoft.com/devices/recoverykey, or in an admin
   terminal `manage-bde -protectors -get C:`. Write it down or print it.
2. Turn device encryption **off** (Settings > Privacy & security > Device encryption) and wait until
   `manage-bde -status C:` says "Fully Decrypted". Today the installer refuses any disk with a BitLocker
   volume on it, and suspending BitLocker is not enough for that check. You can turn it back on after
   both systems boot; Windows will then bind it to the new boot setup.
3. Turn Fast Startup off (Control Panel > Power Options > "Choose what the power buttons do").
4. Shrink C: in Disk Management. Leave at least 40 GiB unallocated; for daily development give it
   300 GiB or more (Docker images, VMs, ISO builds need ~60 GiB each).
5. Keep Windows' clock in UTC so both systems agree (admin terminal, one line):
   ```
   reg add HKLM\System\CurrentControlSet\Control\TimeZoneInformation /v RealTimeIsUniversal /t REG_DWORD /d 1 /f
   ```
6. Shut down with `shutdown /s /t 0`.

## 2. Firmware (Legion: F2 at power-on for setup, F12 for the boot menu, or the Novo pinhole)
- Security > Secure Boot: **Disabled** (SecLegion's Secure Boot is planned for 1.4).
- Configuration > Graphics Device: start in **Hybrid** (Dynamic Graphics). Discrete is tested later (B2).
- Boot: UEFI only; USB boot enabled.

## 3. Write the USB (on the current Arch laptop)
```bash
cd /mnt/Dev_Lab/iso-artifacts/isoN && sha256sum -c SHA256SUMS
```
```bash
lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
```
Plug the stick in, run `lsblk` again, and take the new `usb` disk (for example `/dev/sdb`). Check the size and
model: the wrong name erases that disk. Unmount any of its partitions first.
```bash
sudo dd if=seclegion-<date>-x86_64.iso of=/dev/sdX bs=4M oflag=direct conv=fsync status=progress
```
```bash
sudo cmp -n "$(stat -c %s seclegion-<date>-x86_64.iso)" seclegion-<date>-x86_64.iso /dev/sdX && echo USB-OK
```

## 4. Live tests on the Legion (nothing is written to its disk)
F12 > the USB > **Try SecLegion OS (Live)**. In a terminal:
```bash
lspci -nnk; lsusb; cat /sys/power/mem_sleep; nmcli dev wifi list; wpctl status; v4l2-ctl --list-devices
```
- Save the output to a second USB or a phone photo: it gives the Wi-Fi chip, audio and panel for the hwdetect
  fixture refresh (gap 1).
- Check B2 (both GPUs, `prime-run glxinfo -B`, `nvidia-smi`), B3 (Wi-Fi, Bluetooth), B4 (speakers, mic, keys)
  and B5 (`systemctl suspend` three times). The bar check script (gap 4) runs these when it lands:
  `seclegion-barcheck`.
- Anything red: stop here, report it, and keep using the old laptop.

## 5. Install alongside Windows
F12 > USB > **Install SecLegion OS**. Choose **alongside**, LUKS on, your username and password.
After the reboot:
- B1: `bootctl status` shows the UKI. B1b: boot Windows from the SecLegion menu (or F12 until gap 7 lands),
  check that BitLocker does not ask (if you turned it back on) and the clocks agree.
- B6: `lsblk -f` shows `crypto_LUKS`. B10/B11/B13: `git --version`, `gpg -K`, `docker run --rm hello-world`.

## 6. Move the work (old laptop stays untouched as the fallback)
On the old laptop:
1. SecLegion: commit or write patch files for every worktree you want to keep, then
   `git -C /mnt/Dev_Lab/SecLegion-OS bundle create ~/seclegion.bundle --all`.
   Do the same for every other repo (or push them, once a remote exists: gap 9 / B16).
2. Secrets by hand, on an encrypted stick, never through a cloud folder: `~/.ssh`, `~/.gnupg`
   (`gpg --export-secret-keys --armor` plus `gpg --export-ownertrust`), password manager export if any.
3. Claude Code: `~/.claude/` (settings, plugins, `projects/*/memory`), and the Claude desktop config.
4. VS Code: settings sync, or `~/.config/Code/User/`.
5. VMs: `/mnt/Dev_Lab/VMs/ws2019/ws2019.qcow2` and `~/.config/libvirt/qemu/ws2019.xml` (B14, virt opt-in).
6. Browser: Firefox/Brave sync.

On SecLegion:
```bash
git clone ~/seclegion.bundle ~/Dev/SecLegion-OS
```
```bash
cd ~/Dev/SecLegion-OS && make bootstrap && .venv/bin/python -m pytest -q
```
```bash
tools/build-iso
```
B13 passes when the suite is green, `tools/build-iso` produces an ISO and one `-m iso` VM gate passes.
From then on, develop SecLegion on SecLegion; keep the old laptop until B16 (a pushed remote and a
backup) passes.
