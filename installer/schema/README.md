# schema

archinstall JSON format used by `installer/installd/configurator.py` (D-R14-2).
Sources (read only): https://archinstall.archlinux.page/installing/guided.html and, at tag
`4.5` of github.com/archlinux/archinstall, `examples/config-sample.json`,
`examples/creds-sample.json`, `archinstall/lib/models/device.py`.
The tag-4.5 sample files are stale (version 2.8.6), so keys for UKI, disk_encryption and
btrfs subvolumes come from guided.html and device.py. Unverified against a real run
(I2 verifies): `network_config.type` "nm", `profile_config` minimal shape, users
`!password` plaintext key, `locale_config.sys_lang` "en_US.UTF-8", `mount_options`.
