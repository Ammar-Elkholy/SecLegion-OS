<!-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors -->
<!-- SPDX-License-Identifier: MIT -->
# After the flash: every step to the new SecLegion laptop

You have a verified USB stick: ISO #11 (`seclegion-2026.10.31-x86_64.iso`, sha256 `7fe0becd…`), written
to the Kingston DataTraveler and read back with `FLASH-VERIFIED-OK`. This page takes you from that stick
to working on SecLegion. Do the steps in order. Tick each box as you go.

Total time: about 2-3 h, plus 30 min of hardware checks at the end.

**Keep the old laptop unchanged** until step 9 passes. It is your fallback.

---

## Step 1. Prepare Windows 11 on the Legion (in Windows, ~30-60 min)

Encryption is the slow part: decryption can take 30+ minutes.

- [ ] **Save the BitLocker recovery key off the laptop.** Either go to
  account.microsoft.com/devices/recoverykey, or run this in an admin terminal and photograph the output:
  ```
  manage-bde -protectors -get C:
  ```
- [ ] **Turn device encryption off:** Settings > Privacy & security > Device encryption > Off.
  Wait until this command says `Fully Decrypted` (re-run it every few minutes):
  ```
  manage-bde -status C:
  ```
  The installer refuses a disk that has a BitLocker volume on it. Suspending BitLocker is not enough.
  You can turn it back on once both systems boot.
- [ ] **Turn Fast Startup off:** Control Panel > Power Options > "Choose what the power buttons do" >
  "Change settings that are currently unavailable" > untick "Turn on fast startup" > Save.
- [ ] **Free space for SecLegion:** press Win+X > Disk Management > right-click C: > Shrink Volume.
  - The minimum is 40 GiB (40960 MB).
  - For daily development give it **300 GiB or more** (307200 MB). Docker, VMs and ISO builds each
    need about 60 GiB.
  - Leave the freed space as "Unallocated". Do not create a partition in it.
- [ ] **Keep the clock in UTC** so Windows and Linux agree. In an admin terminal:
  ```
  reg add "HKLM\System\CurrentControlSet\Control\TimeZoneInformation" ^
      /v RealTimeIsUniversal /t REG_DWORD /d 1 /f
  ```
- [ ] **Shut down fully:**
  ```
  shutdown /s /t 0
  ```

## Step 2. Firmware settings (~5 min)

Power on and press **F2** (or use the Novo pinhole > BIOS Setup).

- [ ] Security > **Secure Boot: Disabled.** SecLegion does not sign for Secure Boot yet.
- [ ] Configuration > **Graphics Device: Hybrid** (Dynamic Graphics). Discrete mode comes later.
- [ ] Boot: UEFI mode, USB boot **enabled**.
- [ ] Press F10 to save and exit.

## Step 3. Boot the USB in Try Live mode (~20 min, nothing is written to the disk)

- [ ] Plug in the stick and power on. Press **F12** and pick the USB (it may show as "KingstonDataTraveler").
- [ ] In the SecLegion boot menu, choose **Try SecLegion OS (Live)** (hotkey `l`).
  - If the screen stays black or freezes, reboot and use **Live (safe graphics)** from the submenu.
- [ ] Connect to Wi-Fi: use the network icon in the bar, or run `nmcli dev wifi connect "<SSID>" --ask`.
- [ ] Open a terminal with **Super+Enter** and run this hardware report:
  ```bash
  lspci -nnk; lsusb; cat /sys/power/mem_sleep; nmcli dev wifi list; wpctl status; v4l2-ctl --list-devices
  ```
  Save the output to a phone photo or a second stick. Claude needs it later to refresh the hardware data.
- [ ] Check each item. A failure here is a report for Claude, not a reason to panic:

  | Check | How | Good result |
  |---|---|---|
  | Both GPUs | `prime-run glxinfo -B`, `nvidia-smi` | NVIDIA shows up; the desktop runs on AMD |
  | Wi-Fi | open a web page | it loads |
  | Bluetooth | `bluetoothctl power on && bluetoothctl scan on` | devices appear |
  | Speakers, mic | play a video; `wpctl status` | sound from both speakers; a mic is listed |
  | Keys | volume, brightness, mute keys | the on-screen indicator reacts |
  | Webcam | `v4l2-ctl --list-devices` | a camera is listed |
  | Suspend | `systemctl suspend` 3 times; wake with the power key | screen and Wi-Fi come back |

- [ ] **Stop if** Wi-Fi, the display or suspend is broken. Keep using the old laptop and send Claude the
  photos.

## Step 4. Install alongside Windows (~20-30 min)

- [ ] Reboot, press F12 > USB > **Install SecLegion OS** (hotkey `i`). Use **Install (safe graphics)** if
  the normal entry gave a black screen in step 3.
- [ ] The installer walks you through these pages:
  1. **Welcome.**
  2. **Language:** English or Arabic.
  3. **Disk: choose "alongside".** This puts SecLegion in the unallocated space and leaves Windows alone.
     **Do not choose "erase"**: that wipes Windows.
  4. **Alongside:** check that the size matches the space you freed in step 1.
  5. **Encryption: turn LUKS on.** Choose a strong passphrase you will type at every boot, and
     **write it down offline**. If you lose it, the data is gone.
  6. **User:** your username and a **new** login password. Do not reuse the old one: it was shared in
     a chat. Type it slowly with the **English** layout active.
  7. **Hardware report:** read what was detected (GPUs, Wi-Fi).
  8. **Optional extras:** pick the extras you want. Pick virtualisation if you need the ws2019 VM;
     local AI and gaming are optional and can be added later.
  9. **Review:** read everything once more, especially the disk line. Then start.
  10. **Progress**, then **Finished:** reboot and remove the USB when told.

## Step 5. First boot (~10 min)

- [ ] The boot menu (systemd-boot) shows SecLegion and Windows. Pick SecLegion.
- [ ] Type the **LUKS passphrase**.
- [ ] Log in on the login screen (regreet) with your username and password. Hyprland starts.
- [ ] The **first-boot wizard** runs. Connect to Wi-Fi when it asks: Brave, VS Code and Claude are
  downloaded on the first online boot, not shipped on the ISO.
- [ ] Press **Super+/** to see every keybind. Useful ones:

  | Keys | Does |
  |---|---|
  | Super+Enter | terminal |
  | Super+L | lock the screen |
  | Super+/ or Super+F1 | keybind cheat sheet |
  | Super+Shift+T | theme picker |
  | Super+Shift+P | display menu |
  | Super+Ctrl+P | cycle the power profile |
  | Super+Ctrl+N | night light |
  | Alt+Print | screenshot of a region |
  | Super+Ctrl+O | OCR a region to the clipboard |
  | Super+A | AI picker |

- [ ] Optional: stop sudo locking you out for 10 minutes after 3 typos. This allows 10 tries and a
  2-minute lock:
  ```bash
  sudo sed -i -e 's/^#\? *deny *=.*/deny = 10/' \
      -e 's/^#\? *unlock_time *=.*/unlock_time = 120/' /etc/security/faillock.conf
  ```
  If you are ever locked out, wait the lock time, then run `sudo faillock --user $USER --reset`.

## Step 6. Check the install (~10 min)

```bash
bootctl status | head -20
```
- [ ] The output shows systemd-boot and the SecLegion UKI.

```bash
lsblk -f
```
- [ ] It shows `crypto_LUKS` with btrfs inside, and the Windows partitions are still there.

```bash
snapper list
```
- [ ] Snapshots exist. Each update adds a pre/post pair.

```bash
sudo pacman -Syu
```
- [ ] It exits without errors.

```bash
git --version && gpg --version | head -1
```
- [ ] Both print a version.
- [ ] Docker, as your user: `docker run --rm hello-world` prints "Hello from Docker!". If it says
  permission denied, log out and back in once.

- [ ] **Windows still boots:** reboot, pick Windows in the menu (or use F12). Check that the clock is right.
  BitLocker should not ask for the key; if it does, type the key you saved in step 1.
- [ ] Optional: turn Windows device encryption back on now.

## Step 7. Move your secrets (old laptop > new, ~20 min)

Use an **encrypted USB stick or a direct cable or LAN copy, never a cloud folder**.

On the old laptop:
- [ ] `~/.ssh` (copy the whole folder).
- [ ] GPG keys:
  ```bash
  gpg --export-secret-keys --armor > gpg-secret.asc && gpg --export-ownertrust > gpg-trust.txt
  ```
- [ ] Claude Code: `~/.claude/`, which holds your settings, plugins and project memory.
- [ ] VS Code: turn on Settings Sync, or copy `~/.config/Code/User/`.
- [ ] The ws2019 VM: `/mnt/Dev_Lab/VMs/ws2019/ws2019.qcow2` and `~/.config/libvirt/qemu/ws2019.xml`.
- [ ] Browser: Firefox or Brave sync.

On SecLegion:
- [ ] Copy `~/.ssh` into place, then fix its permissions:
  ```bash
  chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_* && chmod 644 ~/.ssh/*.pub
  ```
- [ ] Import GPG:
  ```bash
  gpg --import gpg-secret.asc && gpg --import-ownertrust gpg-trust.txt
  ```
  Then **delete both export files**.
- [ ] Copy `~/.claude/` into your home folder.
- [ ] Test GitHub access:
  ```bash
  ssh -T git@github.com
  ```
  It should greet you as Ammar-Elkholy.

## Step 8. Set up SecLegion development (~30 min)

```bash
mkdir -p ~/Dev && git clone git@github.com:Ammar-Elkholy/SecLegion-OS.git ~/Dev/SecLegion-OS
```
```bash
cd ~/Dev/SecLegion-OS && git checkout clean-room-rebuild && make bootstrap
```
```bash
make lint && .venv/bin/python -m pytest -q
```
- [ ] Lint is green and the unit suite passes (about 1600 tests).
- [ ] `gh auth login` (GitHub CLI), if you use it.
- [ ] Start Claude Code in `~/Dev/SecLegion-OS`. The project instructions (`CLAUDE.md`) have paths from the
  old laptop. On your first prompt, ask Claude to update them for the new layout.
- [ ] Optional, for an ISO build: `tools/build-iso` needs the `docker` group and 25 GiB free under
  `/var/tmp`.

## Step 9. Hardware checks only the real laptop can answer (~30 min)

Write down each result for Claude.

- [ ] **HDMI:** plug in an external screen, unplug it, then run `hyprctl monitors all`. Is a ghost
  monitor left?
- [ ] **Fn+F7:** run `wev`, press Fn+F7, and note the key name it prints.
- [ ] **Wi-Fi speed:** download a large file and compare its speed with the bar's figure.
- [ ] **dGPU sleeps on battery:** unplug the charger and wait a minute. Find the NVIDIA card with
  `lspci | grep -i nvidia`, then:
  ```bash
  cat /sys/bus/pci/devices/0000:<bus-id>/power/runtime_status
  ```
  Good: `suspended`.
- [ ] **GPU links:** `ls -l /dev/dri/seclegion-*` shows `seclegion-igpu` and `seclegion-dgpu`.
- [ ] **Lock:** Super+L locks; closing the lid and reopening it shows the lock screen.
- [ ] **Docker with the firewall on:** `docker run --rm hello-world` still works.
- [ ] **ws2019 VM** (if you picked virtualisation): `virsh -c qemu:///session start ws2019` boots it.

When this all passes, the old laptop can retire. Keep it until your repos are pushed and a backup exists.

## Step 10. Continue the work with Claude

Paste this into Claude Code in `~/Dev/SecLegion-OS`, followed by your step 3 and step 9 results:

> I'm on SecLegion now. Here are the live-test and hardware-check results. Update CLAUDE.md for this
> machine, then continue with docs/NEXT-ON-NEW-OS.md and docs/STATUS.md.

What is still open (from `tools/seclegion-progress --all`; about 25-30 agent hours, ~15-20 h with ultracode):
- **1.0:** keyboard-shortcut VM test (W1); installer screen tests (CP-C); online package repo (RL1, needs
  your signing key); updates and migrations (W3); your-workflow checkpoint (CP-D); desktop issues
  (OD1, from step 9); release candidate on one ISO (CP-G).
- **1.1:** GUI installer and boot splash (U2-U4); kiosk trial (S1); VM networks (V1); hardware, AI and
  virtualisation checkpoint (CP-E).
- **Your decisions:** ship "Seclegion Wallpaper.png" as the default wallpaper? Which licence for the
  branding (D-BR-1)?

---

## If something goes wrong

| Problem | Fix |
|---|---|
| Black screen after the boot menu | Use the **safe graphics** entry. In Firmware, try Graphics: Hybrid. |
| The installer refuses the disk | BitLocker is still on: step 1, wait for "Fully Decrypted". |
| No Windows in the boot menu | Press F12 at power-on and pick Windows Boot Manager. |
| Wrong LUKS passphrase | Check the layout: the boot prompt may use the US layout, not Arabic. |
| sudo refuses the right password | Locked after 3 typos: wait 10 min (step 5). |
| An update broke something | `seclegion-rescue list-snapshots`, `sudo seclegion-rescue rollback --yes <N>` |
| Can't log in | USB > Rescue or Live: `cryptsetup open`, mount, `arch-chroot`, `passwd <user>` |
| A config file got messed up | `seclegion-update --refresh-config <name>` (your own overrides are kept). |
