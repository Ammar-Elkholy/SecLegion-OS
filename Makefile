# SecLegion OS - project entry points. See docs/testing.md.
# Dev tools come from ./.venv (make bootstrap) when present, else from PATH.
SHELL := /bin/bash
VENV_BIN := $(abspath .venv/bin)
export PATH := $(VENV_BIN):$(PATH)

PY_TOOLS := tools/check-branding tools/check-space tools/gen-testing-md tools/verify-evidence tools/check-container-start hw/tools/check-nvidia-table pkgs/seclegion-hwdetect/bin/seclegion-hwdetect pkgs/seclegion-hwdetect/bin/seclegion-hwreport tools/seclegion-tools tools/vendor-bump tools/canary desktop/display/seclegion-displayd desktop/display/seclegion-wallpaper
SH_TOOLS := tools/build-iso tools/pkg-source tools/lint-pkgs tools/docker-build.sh tools/container-build.sh tools/seclegion-vendor-fetch

.PHONY: help bootstrap lint lint-pkgs test iso vm evidence host-install host-test

# List the targets with the comment block above each one.
help:
	@awk '/^# / { d = d (d ? " " : "") substr($$0, 3); next } \
	     /^[a-z][a-z-]*:/ && d { sub(/:.*/, ""); printf "  %-10s %s\n", $$0, d } { d = "" }' $(MAKEFILE_LIST)

# Create ./.venv with the pinned-by-name dev tools (pytest, ruff, reuse, shellcheck).
bootstrap:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

# Each linter runs if installed; a missing one prints a loud SKIPPED warning (never a silent pass).
lint:
	@fail=0; \
	if command -v shellcheck >/dev/null; then shellcheck $(SH_TOOLS) || fail=1; \
	else echo "WARNING: lint SKIPPED shellcheck (not installed; run 'make bootstrap')"; fi; \
	if command -v ruff >/dev/null; then ruff check . $(PY_TOOLS) || fail=1; \
	else echo "WARNING: lint SKIPPED ruff (not installed; run 'make bootstrap')"; fi; \
	if command -v reuse >/dev/null; then reuse lint || fail=1; \
	else echo "WARNING: lint SKIPPED reuse (not installed; run 'make bootstrap')"; fi; \
	python3 tools/check-container-start || fail=1; \
	exit $$fail

# Check pkgs/ only: reuse lint-file on every tracked file, namcap on built packages (when installed).
lint-pkgs:
	@tools/lint-pkgs

# Run the unit and mutation tests (tests/unit, tests/mutation; the ISO boot tests run under `make vm`).
test:
	python3 -m pytest -q

# Build the ISO in the pinned container (tools/docker-build.sh is the only container entry point).
iso:
	tools/build-iso

# Boot the built ISO in QEMU/OVMF via the harness and record evidence (needs out/*.iso).
vm:
	python3 -m pytest -q tests/iso -p no:cacheprovider

# Verify evidence/ (forged or inconsistent results fail), then regenerate TESTING.md from it.
# Verify first so a bad result never reaches TESTING.md; the closing verify checks the output.
evidence:
	tools/verify-evidence --results-only
	tools/gen-testing-md
	tools/verify-evidence

# Put one desktop component on the running host: make host-install COMPONENT=border|notifications|waybar|lock|keys|gtk|fm|settings|osd|idle|theme-auto|display
host-install:
	@case "$(COMPONENT)" in border|notifications|waybar|lock|keys|gtk|fm|settings|osd|idle|theme-auto|display) ;; \
	  *) echo "usage: make host-install COMPONENT=border|notifications|waybar|lock|keys|gtk|fm|settings|osd|idle|theme-auto|display" >&2; exit 2 ;; esac
	tools/seclegion-host apply "$(COMPONENT)"

# Test seclegion-host against a fake HOME and PATH stubs (never the live session).
host-test:
	bash tests/host/test-apply-rollback.sh
