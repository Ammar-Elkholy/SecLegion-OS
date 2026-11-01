# Installing SecLegion OS next to Windows

Choose the "alongside" mode in the installer. SecLegion uses the largest contiguous free gap
on the disk (at least 40 GiB) and never touches your Windows partitions. Free that space first
in Windows (Disk Management, shrink the C: volume).

Before installing, the installer checks every NTFS partition on the chosen disk (read-only):

- **BitLocker** (`bitlocker`): the installer refuses. BitLocker must be **off** (decrypted), not
  merely suspended: a suspended volume still carries the BitLocker signature, and that signature is
  what the check sees. Keep your recovery key: changing the boot chain can trigger a recovery prompt.
- **Hibernated / Fast Startup** (`windows_hibernated`): shut Windows down fully: disable Fast
  Startup, or run `shutdown /s /t 0` from a command prompt. A normal "Shut down" with Fast
  Startup leaves the volume in a hibernated, dirty state.

The check reads the NTFS `$Volume` dirty flag directly (no NTFS driver needed). `ntfs-3g.probe
--readonly` was tried and does not report hibernation, so it is not used. An unclean Windows
shutdown also sets the flag; boot Windows and shut it down fully to clear it.

"Erase" modes wipe the whole disk, so these checks do not apply to them.

## Who checks what

The installer window runs as an unprivileged kiosk user, which cannot read raw partitions. It shows
"will be checked when installing" for such partitions and does not block on them. The authoritative
check runs as root inside `seclegion-install` (the only program the kiosk may run as root): it gathers
the facts itself and refuses a BitLocker or hibernated volume, or one it cannot read, before anything is
written, whatever the window showed.

## Windows in the boot menu

SecLegion keeps its own ESP and never writes the Windows ESP. In alongside mode `seclegion-post` looks
(read-only: `lsblk`, then a read-only mount) for a vfat EFI System partition holding
`EFI/Microsoft/Boot/bootmgfw.efi`. If it finds one, it installs `edk2-shell`, copies `Shell.efi` to
`EFI/seclegion/shellx64.efi` on SecLegion's ESP and adds a "Windows 11" entry
(`loader/entries/windows.conf`) that runs `EFI/seclegion/windows.nsh`. The script starts
`\EFI\Microsoft\Boot\bootmgfw.efi` from the first `FSn:` that has it. Nothing is copied from
`EFI/Microsoft`, so Windows updates cannot make the entry stale. Erase modes write none of this, and
neither does an alongside install that finds no Windows ESP (it is logged).

The script matches by file, not by PARTUUID: the UEFI shell has no substring match for the `map` output.
SecLegion's ESP never holds `EFI/Microsoft`, so the file identifies a Windows ESP. With two Windows ESPs
the first in firmware order wins. The fallback that always works is the firmware boot menu (F12).
