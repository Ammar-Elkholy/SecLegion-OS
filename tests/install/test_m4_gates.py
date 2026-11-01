# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Checkpoint B evidence rows derived from the erase install (one VM install, cached) and the mutation suite.

  M4-erase / M4-luks / M4-alongside   test_i2_run.py, test_i3_matrix.py (gate_m4)
  M4-offline       the erase install ran in a VM with no NIC (`-nic none`) and succeeded
  M4-target-clean  target_check on the real target printed nothing, DL-TARGET 0, no user_credentials.json
  M4-mutation      every install mutant is caught (no VM; run_gate still records the ISO sha, so marked iso)
"""
import os
import sys
import tempfile

import pytest
from test_i2_run import finish_gate, run_install

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tests", "mutation", "install"))


def _write(result_dir, text):
    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
        out.write(text)


@pytest.mark.iso
def test_m4_offline():
    def body(result_dir, iso):
        run = run_install("erase")
        _write(result_dir, run.log)
        assert run.error is None, run.error
        assert "-nic none" in run.command, run.command
        return "the install ran with -nic none and succeeded", run.command, "n/a"

    finish_gate("M4-offline", "the install VM has no NIC (-nic none) and the install succeeds", body)


@pytest.mark.iso
def test_m4_target_clean():
    def body(result_dir, iso):
        run = run_install("erase")
        _write(result_dir, run.log)
        assert run.error is None, run.error
        return "target_check printed nothing and DL-TARGET 0; no user_credentials.json", run.command, "n/a"

    finish_gate("M4-target-clean", "target_check on the real target is silent with DL-TARGET 0 and "
                "find /mnt -name user_credentials.json finds nothing", body)


@pytest.mark.iso
def test_m4_mutation():
    import test_install_mutants as mut

    def body(result_dir, iso):
        lines, green = [], []
        with tempfile.TemporaryDirectory(prefix="m4-mut-") as tmp:
            for name in mut.ALL:
                caught = bool(mut.run_mutant(name, os.path.join(tmp, name)))
                lines.append(f"MUTANT {name} {'CAUGHT' if caught else 'GREEN'}")
                if not caught:
                    green.append(name)
        lines.append(f"MUTANTS {len(mut.ALL)} GREEN {len(green)}")
        _write(result_dir, "\n".join(lines) + "\n")
        assert not green, f"green mutants: {green}"
        return f"{len(mut.ALL)} mutants, all caught", "run_mutant over tests/mutation/install ALL", "n/a"

    finish_gate("M4-mutation", "every install mutant is caught (MUTANTS <n> GREEN 0)", body)
