# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""I3: the VM install matrix beyond plain erase (erase is test_i2_run): erase-luks, alongside and partition.
Each is an evidence row (M4-luks, M4-alongside, M4-partition)."""
import pytest
from test_i2_run import gate_m4


@pytest.mark.iso
@pytest.mark.parametrize("mode,test_id", [("erase-luks", "M4-luks"), ("alongside", "M4-alongside"),
                                          ("partition", "M4-partition")])
def test_i3_matrix(mode, test_id):
    gate_m4(test_id, mode)
