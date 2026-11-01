# R0 spike: `docker-build.sh pkgs <dir>` and the build lock

## Approach

`tools/docker-build.sh pkgs pkgs/<name>` builds one PKGBUILD directory inside the existing
pinned build container and writes `.pkg.tar.zst` files to `$WORKDIR/out/pkgs/`, printing
`pkg-ok <filename>` for each.

Chosen: plain `makepkg` as an unprivileged user in the container, not `makechrootpkg`.
Why: the container is already a fresh, disposable root on every run (`--rm` semantics via
the wrapper's cleanup), with packages from the archive-pinned mirror. A nested chroot would
add devtools, bind mounts and a second package set to pin, for no extra isolation. Cost: the
build user has passwordless sudo inside the throwaway container (needed for `--syncdeps`),
and makedepends are installed into that container root, not a second chroot.

Inside the container (`tools/container-build.sh pkgs`): archive-pinned `pacman -Syu base-devel`,
user `builder` (useradd), PKGBUILD dir copied from the read-only `/src` to `/work/pkgbuild`,
then `makepkg --clean --cleanbuild --syncdeps --noconfirm` with `PKGDEST=/work/out/pkgs` and
`SOURCE_DATE_EPOCH` passed through. Output is chowned back to the invoking user on exit, as
for the other modes.

## Validation (wrapper, before anything else)

`<dir>` must be `pkgs/<name>[/...]` (or the same under the absolute repo path), characters
`[A-Za-z0-9._-]` only, no `.` or `..` component, `realpath -e` equal to the literal path (no
symlink component), a directory holding a plain-file `PKGBUILD`. Anything else exits 1 with
`REFUSED: pkgs:` before the workdir is touched or a container starts. The container script
re-checks the value of `PKG_DIR` (hard-coded `--env`, not an argument to the engine).

## Lock

`tools/lib/locks.sh` `sl_build_lock`: `flock` on fd of `/var/tmp/seclegion-build.lock`; prints
"waiting for build lock" if held; released when the wrapper exits. Taken for iso, theme and
pkgs after validation, before the engine is touched; never for `check`. Tests exercise the
function directly with a lock path argument (the wrapper passes none).

## Pinned / limits

- Pinned: image digest, archive date (from `iso/profile/pacman.conf`, full `-Syu`).
- Disk floor: pkgs 5 GiB, iso stays 25 GiB (unchanged; the roadmap's 35 GiB is not applied here).
- Sources: a PKGBUILD with network `source=()` downloads through the container's normal
  network; only `pkgs/hello` (no sources) is verified. Checksums come from the PKGBUILD.
- Not reproducible bit for bit beyond `SOURCE_DATE_EPOCH`; packages are unsigned.
- `--privileged` stays (decisions M0-5); makepkg does not need it, so a later narrowing of
  flags for pkgs mode is possible but not done.
