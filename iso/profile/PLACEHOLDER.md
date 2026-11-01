# STOCK RELENG PROFILE - BEING REPLACED (plan r13)

This directory started as an unmodified copy of `/usr/share/archiso/configs/releng`
(archiso). M1 (plan r13 J1a) replaced the boot side: `profiledef.sh` and `grub/` are
SecLegion's own (UEFI + GRUB only; the stock `syslinux/` and `efiboot/` are gone). The
packages, `airootfs/` and root login are still stock and carry Arch behaviour; M2 replaces
them. Do not ship this profile before then.

The GRUB entries pass `console=ttyS0,115200 console=tty0` so the kernel and a getty speak
on the serial port that the boot harness (`tests/iso`) reads.
