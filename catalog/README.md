# catalog

The Tier-1 security tools catalog (PRD 8.2). Every `catalog/*.toml` holds `[[tool]]` tables; a new batch only adds a file. `tools/seclegion-tools` reads them (`list`, `info`, `test`, `lint`); `tests/tools` runs the same lint.

Batch 1 (this directory): `recon.toml` (nmap, masscan), `network.toml` (wireshark-cli, tcpdump, netcat, socat), `web.toml` (nikto, gobuster, ffuf, sqlmap). Batch 2 (john, hashcat, hydra, responder, impacket, aircrack-ng, exploitdb) adds files such as `passwords.toml`, `wireless.toml`.

## Fields (all required unless marked)

| field | meaning |
|---|---|
| `name` | catalog name, unique across files |
| `package` | exact pacman package name (`netcat` is `openbsd-netcat`) |
| `source` | `arch-core`, `arch-extra`, or `seclegion` (vendored clean-chroot builds in `[seclegion]`: ffuf, responder, grimblast; spec A8). AUR, BlackArch, Kali and custom builds are not allowed without the owner's decision |
| `category` | `recon`, `network`, `web`, `passwords`, `wireless`, `forensics`, `reversing` |
| `purpose` | one line |
| `privileges`, `privileges_why` | `none`, `cap_net_raw` or `root`, and why |
| `safe_test` | argv list, never a shell string |
| `safe_test_expect` | regex that must match stdout+stderr |
| `safe_test_exit` | optional, expected exit status (default 0) |
| `safe_test_timeout` | optional, seconds, 1 to 10 (default 10) |
| `removal`, `update_policy`, `docs` | documentation strings |
| `needs_internet` | must be `false` |

The version is not stored: `seclegion-tools list/info` read it from `pacman -Q` at run time.

## Safe-test rule (enforced by `seclegion-tools lint`)

A safe test touches only loopback (`127.0.0.1`, `::1`, `localhost`) or nothing (`--version`, `-h`). Lint parses argv and fails on: a shell string, a shell or wrapper as program (`sh`, `env`, ...), shell metacharacters, any hostname, URL, IP, CIDR or wildcard that is not loopback, any interface other than `lo`, flags that read targets from elsewhere (`-iL`, `-iR`, and masscan `-c`), and for `nmap`/`masscan` any target other than exactly `127.0.0.1`.

`seclegion-tools test --all` prints PASS, FAIL or SKIP (tool not installed) per tool and exits non-zero on any FAIL.
