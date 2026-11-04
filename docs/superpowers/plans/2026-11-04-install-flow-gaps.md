# Install flow review: gaps (plan only, not implemented)

The owner asked (2026-11-04) for a review of the whole install flow and what is supposed to happen, with
anything missing planned, not implemented, after D6. It covers the flow Boot → Try Live / Install →
installer pages → `seclegion-install` → `seclegion-post` → first boot → desktop. It was checked against
the code on `clean-room-rebuild` after the D2-D4 merges.

## What works now (checked in code and tests)

- **GRUB:** Install, Try Live, Rescue, Memtest, Firmware, plus safe-graphics variants (`grub.cfg`).
- **Install mode:** offered even when the target is still activating with no Ethernet
  (`facts.detect_install_mode`, 7 tests).
- **Live:** the SecLegion desktop (skel + uwsm), with no Hyprland tutorial and lock disabled. VM gate
  M2-live-desktop is owed by ISO #12.
- **Pages:** welcome → language → disk → [alongside] → [encryption] → user → hardware → extras → review →
  progress → finished (`model.py`).
- **Disk page:** one card per disk with a partition map. The choices are erase, use free space
  (≥ 40 GiB), or replace one partition. Refused partitions are greyed out with the reason
  (`test_disk_page.py`, 29 tests).
- **Safety:** `configurator.validate` is the only judge. The root side re-validates with fresh facts.
  Refusals fail closed (`test_partition_mode.py`, 38 tests).
- **Review:** summary rows with Edit buttons, and a warning in the mode's own words. The user types the
  disk model, or the partition name in partition mode.
- **Install:**
  - offline archinstall: UKI, systemd-boot, btrfs subvolumes, zram, NetworkManager;
  - then seclegion-post: packages, skel, hwdetect plan, greetd + regreet, ufw, snapper, firstboot, and the
    Windows boot entry when installing alongside (VM gates I2/I3).
- **First boot:** snapper baseline and keyboard layout. The welcome app offers the vendor fetchers.
- **Arabic:** the window mirrors (RTL), pinned by a negative-gated test.

## Gaps, by priority

Hours are agent hours, including tests. **[#12]** marks the gaps that break or confuse the flow on the
owner's Legion, so they should be fixed before ISO #12.

1. **G1 [#12] Bluetooth is off on the installed system** (0.5 h). `bluez` is installed, but
   `bluetooth.service` is never enabled.
   - Plan: `post.py` `steps()` enables `bluetooth.service`, and `fstrim.timer` for the SSD.
     `target_check.py` asserts both. Add a post unit test.
2. **G2 [#12] No timezone choice** (2 h). The target takes the live ISO's `/etc/localtime` (UTC), so the
   clock is 2-3 h off in Egypt. Kali asks for this.
   - Plan: a new `pages/p16_timezone.py` after language, with a searchable Region/City list from
     `/usr/share/zoneinfo/tzdata.zi`. Default `Africa/Cairo` for Arabic, else UTC.
   - The fragment `{"timezone"}` already fits `Answers.timezone`. Add a "Time zone" review row.
   - Tests: the fragment, validate, the review row.
3. **G3 [#12] No way out of the kiosk** (1.5 h). No page has Reboot or Power off, so after a failed
   install the user must hold the power button. The Finished page's `systemctl reboot` runs as
   `seclegion-installer` and is unproven in a VM.
   - Plan: a header menu on every page (Reboot, Power off, About). Add a polkit rule for
     `org.freedesktop.login1.reboot`/`power-off` for that user, unless logind already allows it for the
     kiosk session.
   - VM gate: Reboot from the Finished page reboots the guest.
4. **G4 [#12] Retry after a failure uses stale facts** (1.5 h). The GUI gathers facts once. After a failed
   partition or alongside run, the review page says OK and then the root side refuses.
   - Plan: retry re-gathers facts. If the chosen disk or partition changed, the installer returns to the
     disk page with "The disk changed during the failed install; choose again." Add a "Rescan disks"
     button (for a USB plugged in late).
   - Test: change the fixture between runs; the retry lands on the disk page.
5. **G5 [#12] Progress has no real percentage** (3 h). The bar has no stages; the log is the only sign
   of life.
   - Plan: `seclegion-install` and `post.py` print `SECLEGION-STAGE i/N text` (partitioning, base system,
     SecLegion packages, bootloader, finishing). `p9_progress` maps it to a fraction and a step label, and
     pulses within a stage.
   - Tests: the parser, plus a fake installer stream.
6. **G7 [#12] Partition mode defaults encryption off** (0.3 h). Erase defaults on.
   - Recommendation: default on in partition mode too. Alongside stays off for the Windows BitLocker/TPM
     flow.
   - Change the `p3_disk.luks` default, with a test.
7. **G10 [#12] Look issues** (0.5 h): the progress icon is a generic glyph; GTK warns
   `gtk.css:93 Expected a filter` (D1 CSS); the sidebar logo is soft at 1280 px.
   - Plan: fix the CSS rule and ship a symbolic icon.
   - The logo needs a higher-resolution or SVG export of the owner's artwork. Ask the owner; never redraw it.
8. **G11 [#12] VM gates still owed** (3 h, phase E):
   - `test_i3_matrix.py::test_partition_mode`;
   - gather-facts install mode with no network device;
   - M2-live-desktop.
9. **G12 [#12] Screenshot findings (D6, `out/screens-d6/`)** (1 h):
   - Progress and Finished still show a green Next in the footer (with "Installing..."); hide it there.
   - The progress/finished/error icons render as grey blobs: ship SecLegion symbolic icons with the
     installer instead of relying on an icon theme. On the error page at 800x600 the icon top is clipped.
   - A disk with no partitions still shows the empty "Or replace one partition" heading; hide it.
   - Below 720sp the sidebar collapses, but 800x600 keeps it (800 > 720): content is narrow there.
     Decide whether the breakpoint should be 860sp.
   - The picked partition can sit below the fold: scroll it into view when the page opens.
   - Tests: footer Next hidden on progress/finished; no empty group; picked row visible.
10. **G6 (1.1) Try Live has no "Install" launcher** (1.5 h). Kali has one on the desktop.
   - Plan: a live-only rofi entry and a welcome-app button, "Install SecLegion OS". It opens a dialog
     "Restart and choose Install in the boot menu" with a Restart button. Check the GRUB default entry.
   - Test: `test_m2_static` sees the desktop file.
11. **G8 (1.1) Arabic flips direction but the text stays English** (4 h).
    - Plan: a gettext catalog `installer/ui/gtk/po/ar.po` with `_()` around page strings.
    - Test: the review page shows Arabic labels.
12. **G9 (1.1) No boot splash** (3 h), although meter item U2-U4 names Plymouth. Boot shows kernel text,
    and LUKS asks at a plain prompt (Omarchy themes both).
    - Plan: a `seclegion-plymouth` theme from the logo, the `plymouth` hook for the UKI, and `quiet splash`.
    - VM gate: LUKS still unlocks through serial `send()`.

Before ISO #12 (G1-G5, G7, G10-G12): about 13.3 h. For 1.1 (G6, G8, G9): about 8.5 h.

## Checked and fine (no change)

- **Windows clock in a dual boot:** the `RealTimeIsUniversal` step is in `AFTER-FLASH.md` and
  `USB-MIGRATION.md`.
- **Wi-Fi during install:** not needed, because the install is offline. The vendor apps are fetched later
  from the welcome app.
- **Accounts:** one sudo user with a password. nullok is stripped and sshd is masked.
- **A second ESP in alongside or partition mode:** by design. The Windows ESP is only read.
- **Keyboards:** us and Arabic only, as the owner asked.
