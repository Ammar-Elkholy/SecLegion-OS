# ISO #12 on metal: problems, causes and fixes (plan for ISO #13)

The owner booted ISO #12 on the Legion (2026-11-07) and sent 5 photos: the boot screen, the welcome
page, the language page, and the disk page. This plan traces every problem in them and the ones they
point to. For each it gives the problem, the technical cause (with file and line), the fix, and the
test that proves the fix. Nothing is implemented yet.

## Why the VM gates passed but the laptop failed

All 38 VM gates pass on ISO #12, yet the installer is unusable on the laptop. The gates never run the
GUI the way the laptop does:
- The install gates call `seclegion-install --force-install-mode` from a root shell. That skips the
  GUI's fact gathering and its install-mode check.
- Nothing runs `facts.gather()` as the unprivileged `seclegion-installer` user inside the kiosk.
- The VMs have 4 GiB RAM, so the ISO is never copied to RAM. The laptop copies it, which changes how
  the boot USB looks.
- The VMs have one virtual disk, no NVIDIA GPU, a 1280x800 screen and no real Windows partitions.

Every fix below comes with a test that runs in the laptop's conditions (P8).

## Problems

### P1. Every disk says "The installer was not started in install mode" (blocker)
- **Cause:** `facts._out()` (`installer/installd/facts.py:64`) runs commands with `check=True`.
  `systemctl is-active seclegion-install.target` exits 3 unless the target is `active`.
  - On the laptop the target stays `activating`, because a target is ordered after everything it
    `Wants=`, including multi-user.target and the network.
  - `_out` turns the exit 3 into `""`, so `detect_install_mode()` gets `""` and returns False.
  - The Phase B fix (accept "activating") only ever saw string inputs in its unit tests. It never ran
    on a real `systemctl`.
- **Fix:** read the state with `systemctl show -P ActiveState seclegion-install.target`, which exits
  0 in every state, through a helper that never drops stdout.
- **Tests:**
  - A unit test with a fake runner that returns rc=3 and "activating" must give `install_mode=True`.
  - A negative gate: the old `_out` makes that test fail.
  - The VM gate in P8.

### P2. The drives show no partitions and no analysis (blocker; also a design flaw)
- **Cause:** `p3_disk.py:262-300` builds the partition list and options only when the disk is
  allowed. A refused disk gets a greyed-out, empty map and no rows. P1 refused every disk, so the
  laptop showed three empty cards.
- **Fix:** always show a disk's full analysis, even when the disk is refused:
  - the partition map, with every partition, its label, filesystem, size and detected OS (Windows,
    Linux, EFI, recovery, BitLocker);
  - the free space;
  - the reason for each refusal.

  Only the choices are disabled.
- **Test:** a refused disk still renders its partition rows.

### P3. The boot USB is probably offered as an install target (safety)
- **Cause:** `facts.py:44` finds the boot medium from the device mounted at `/run/archiso/bootmnt`.
  The laptop copied the ISO to RAM (photo: "Copying rootfs image to RAM"), and archiso then unmounts
  bootmnt. So `boot_medium` is None and the DataTraveler (`/dev/sda`) looks like a normal disk.

  The VMs never copy to RAM, so no gate saw this. Still to confirm: that the archiso hook unmounts
  after the copy; the P8 gate checks it.
- **Fix:** identify the boot medium from `archisosearchuuid=` on `/proc/cmdline`: the disk whose
  iso9660 filesystem has that UUID (lsblk `uuid`). The bootmnt mount stays as a fallback. The card
  says "SecLegion USB (boot medium)".
- **Test:**
  - A unit test with the laptop's lsblk shape and no bootmnt.
  - A VM gate that boots with `copytoram=y` and expects the `boot_medium` refusal on the ISO disk.

### P4. Error spam on boot
- **Causes:**
  - Hundreds of `nouveau ... gsp: ... ctrl cmd:0x00731341 failed` lines: nouveau loads on the RTX
    40-series dGPU, and its GSP support is incomplete there. The installer draws with cairo on the
    iGPU and does not need the dGPU.
  - `memdiskfind: not found`: `HOOKS` in `iso/profile/airootfs/etc/mkinitcpio.conf.d/archiso.conf`
    includes `memdisk`. That hook needs syslinux, and the ISO boots with GRUB only.
- **Fix:**
  - Drop `memdisk` from HOOKS.
  - Add `modprobe.blacklist=nouveau` to the Install and Rescue entries.
  - Add `quiet loglevel=3 rd.udev.log_level=3 systemd.show_status=auto` to every entry.
  - Keep a "verbose boot" entry in the Advanced submenu.
  - Live keeps nouveau (external HDMI on the dGPU), but quiet. The proper Live fix (nvidia-open in the
    live image) is listed under P9.
  - The installed system already blacklists nouveau through nvidia-utils when hwdetect picks
    nvidia-open. A VM test with the Legion fixture confirms the blacklist file is present.
- **Test:**
  - `test_m1_*` static checks on grub.cfg and HOOKS.
  - The M0/M1 VM gates re-run, because quiet changes what reaches the serial console.

### P5. The SecLegion logo is blurry
- **Cause:** every consumer uses `desktop/branding/seclegion-logo.png`, which is **64x64**: the
  installer sidebar, the welcome page, the About dialog, the installed branding package and os-release
  `LOGO`. GTK scales it up to about 250 px.

  The owner's originals are in `/mnt/Dev_Lab/SecLegion/`:
  - `SecLegion_Logo_Png.png`: 5376x5376, transparent; the right source;
  - `Transparent Emblem (512x512).png`;
  - `SecLegion.png`: 5376x5376, with a background.
- **Fix:**
  - Add `tools/gen-logo` (ImageMagick, deterministic). It renders 64/128/256/512/1024 px PNGs and
    hicolor icon sizes from `SecLegion_Logo_Png.png`, crops the transparent margins, and never
    redraws.
  - Ship them in seclegion-branding.
  - The installer picks a size of at least the drawn size times the scale factor.
  - Check the GRUB theme, regreet, fastfetch and the welcome app for the same 64 px file.
- **Test:** a unit test that every shipped logo is at least as large as its drawn size × 2.

### P6. Keyboard list has only English (US) and Arabic
- **Cause:** `p2_language.py:12` hard-codes two layouts. That followed an earlier owner note ("us and
  Arabic only"), which the owner has now reversed for keyboards. System languages stay English and
  Arabic.
- **Fix:**
  - A searchable list of every XKB layout and variant from `/usr/share/X11/xkb/rules/base.lst`
    (xkeyboard-config is on the ISO as a dependency of libxkbcommon).
  - Group the common ones first, like Kali and Omarchy do.
  - Console keymap: map XKB to the console with systemd's `/usr/share/systemd/kbd-model-map`, falling
    back to `us`.
  - Hyprland and regreet get `kb_layout`/`kb_variant`.
  - For a non-Latin layout, add `us` as a second layout with Alt+Shift switching, as Arabic does now.
  - **Password safety:** the kiosk types with the US layout. The keyboard page gets a test field. The
    account page says which layout passwords are typed in. The installed system always keeps `us`
    reachable, so the password typed in the installer still works at the login screen.
- **Test:**
  - A unit test that the list has at least 100 layouts and the mapping is correct (fr→fr, de→de,
    ara→us+ara).
  - The configurator rejects an unknown layout.
  - The post step writes the Hyprland input layout.

### P7. Disk choice is too simple: no real partitioning (main redesign)
The owner wants what Windows Setup, Kali and Calamares offer:
- see every drive and its partitions;
- pick a partition;
- format, delete, create, shrink ("split") and set what each one is used for;
- keep a flexible memory of the choices before anything is written.

**How others do it:**

| Installer | Drive view | Actions |
| --- | --- | --- |
| Omarchy (archinstall TUI) | drives only | erase one whole drive; LUKS forced |
| Windows Setup | drive + partition table | delete, new (size), format, extend; no shrink of NTFS |
| Kali (d-i partman) | full tree | guided (whole disk, LVM, encrypted LVM) or manual: create, delete, resize, format, mount point |
| Calamares (Manjaro, Ubuntu-likes) | map + table | erase, alongside with a shrink slider, replace partition, manual editor |

**SecLegion design** (Calamares-style guided options plus a Windows/Kali-style manual editor):
1. **Storage page:**
   - One card per drive, showing its full partition table: name, label, filesystem, size, used space
     (from `ntfsinfo`/`dumpe2fs`/`btrfs`, read by root, see 7e), detected OS, and badges (boot USB,
     mounted, BitLocker, too small).
   - A proportional map; clicking a segment selects its row.
2. **Guided choices**, kept from ISO #12 and tested:
   - erase the drive;
   - use free space;
   - replace one partition;
   - **new: install alongside by shrinking a partition**, with a size slider (minimum from the
     filesystem's used space plus a margin; 20 GiB at least for SecLegion).
3. **Manual editor** ("Edit partitions…"):
   - A table with per-row actions: Delete, Format (ext4, btrfs, fat32, ntfs, swap, none), Resize,
     Use as (`/`, `/home`, `/boot` (ESP), swap, not used).
   - For free space: New (size, filesystem, use as).
   - Undo, Reset and a "Pending changes" list. Nothing is written until Review → Install.
4. **Memory:**
   - A `StoragePlan` (an ordered list of operations on lsblk facts) lives in `Model`. It survives
     Back and Next and the time zone, user and review pages.
   - After a failed install it is re-validated against re-scanned facts (G4). A changed disk drops
     the plan with a message.
5. **Rules**, enforced by the configurator as the only judge:
   - exactly one `/` of at least 20 GiB;
   - an ESP: a new one, or an existing FAT32 one of at least 300 MiB. A Windows 100 MiB ESP is too
     small for UKIs, so it is not reused and a new ESP is created;
   - 1 MiB alignment, no overlaps;
   - the boot USB and mounted partitions are untouchable;
   - BitLocker cannot be resized or formatted: the message says to shrink it in Windows Disk
     Management or suspend BitLocker first;
   - NTFS shrink is refused when the volume is dirty or hibernated (Fast Startup): ntfsresize's own
     check, shown in plain words;
   - LUKS: an optional per-`/` switch.
6. **Backend:**
   - New `installer/installd/storage/` with:
     - `plan.py` (pure operations and validation);
     - `probe.py` (root-side used-space and BitLocker probes);
     - `apply.py` (root side).
   - `apply.py` runs the operations in a fixed order. Shrinks go first, each with `--no-action` /
     `-n` dry runs before the real run: ntfsresize, then sgdisk for the table; resize2fs; btrfs
     filesystem resize. Then delete, create, format, cryptsetup, mount under `/mnt` with the btrfs
     subvolumes `@ @home @log @pkg @.snapshots`.
   - Then archinstall runs with `disk_config.config_type = "pre_mounted_config"`, so archinstall only
     installs.
   - Guided modes keep their tested archinstall path for now; they can move onto the same backend
     later.
7. **GUI facts need root for used space and BitLocker:** the unprivileged GUI asks a read-only
   helper, `pkexec /usr/bin/seclegion-install --probe-json`, through the existing kiosk polkit rule.
   Without it, Windows partitions show "not checked" (today's defer_unreadable behaviour).
8. **Tests:**
   - Unit tests: plan rules (each refusal), the command sequence on a fake runner, the plan surviving
     page moves.
   - VM gates, each hashing every partition the plan does not touch:
     - M4-manual: delete one partition, create `/` and `/home`, keep a data partition;
     - M4-shrink-ntfs: a test NTFS made with mkntfs, shrunk, `ntfsresize --check` OK, file hash
       unchanged;
     - M4-reuse-esp: a 512 MiB ESP is reused, and the other loaders on it are kept.

### P8. Missing gate: the real kiosk GUI on laptop-like hardware (process fix)
- **Fix:**
  - `seclegion-installer-gui --print-facts` prints the facts plus each disk's refusal, exactly as the
    disk page computes them.
  - New VM gate M2-kiosk-facts. It boots the Install entry with `-nic none`, `copytoram=y`, 8 GiB RAM,
    two NVMe disks (one with an NTFS partition) and a 2560x1600 virtio-gpu.
  - It then runs `runuser -u seclegion-installer -- seclegion-installer-gui --print-facts` and
    expects:
    - `install_mode: true`;
    - `boot_medium` equal to the ISO disk;
    - both NVMe disks with no refusal;
    - their partitions listed.

  Plus a screenshot of the disk page (QMP screendump) for the owner. This gate fails on ISO #12, so
  it proves P1 and P3 are fixed.

### P9. Other problems found in the photos and the review
- **HiDPI:** the 16" 2560x1600 panel draws the installer at scale 1, so the text is tiny and the
  welcome content sits low and off-centre.
  - Fix: the kiosk sets the output scale with `wlr-randr --scale` (add the `wlr-randr` package):
    1.5 at a width of 2560 px or more, 2 at 3840 px or more.
  - Test: the M2-kiosk-facts screenshot at 2560x1600.
- **Arabic RTL but English text (G8):** add the gettext catalog. 1.1 in the old plan; the owner chose
  Arabic as a system language, so move it to ISO #13.
- **No real install progress (G5):** stage lines, from the old plan.
- **Live session dGPU:** consider nvidia-open in the live image, so Try Live drives the HDMI port
  without nouveau errors. It costs about 350 MB of ISO size. The owner decides.
- **Not checked on metal yet:** time zone, account, review, the install itself, first boot. The
  M2-kiosk-facts screenshots should cover the pages up to review.

## Order and effort (agent hours)

| Phase | Items | Hours |
| --- | --- | --- |
| A, ISO #13 blockers | P1, P2, P3, P8 gate | 4 |
| B, polish | P4 boot noise, P5 logo, P6 keyboards, P9 HiDPI | 6 |
| C, storage redesign | P7.1-P7.2 analysis + shrink-alongside, then P7.3-P7.8 manual editor | 22 |
| D | G5 progress, G8 Arabic text | 7 |

ISO #13 can ship after A+B (about 10 h): installable on the laptop with the current three guided
modes. ISO #14 then adds the storage redesign. Or the build waits for C, about 32 h in all.
The owner picks.

Lanes: A and B in series (one agent each, worktrees); C as three agents: plan + rules, backend +
VM gates, GUI.
