# Current workflow migration

Status: SKELETON (M0). Not started. No change has been made to the owner's host by M0.

## Purpose

How the owner's current Hyprland workflow moves into SecLegion, applying the live-host-first rule: dynamic changes are tried on the running system first (backed up, one-command rollback); anything needing reboot, bootloader, initramfs, display manager or system service is done only in the ISO/VM.

## Implements

[owner-directives-r7.md item 5](spec/v1/owner-directives-r7.md)
