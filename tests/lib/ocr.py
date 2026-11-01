# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Optional OCR of screendumps via tesseract. OCR only confirms; serial is the oracle."""

import dataclasses
import shutil
import subprocess

SKIPPED_MISSING = "SKIPPED: tesseract missing"


@dataclasses.dataclass(frozen=True)
class OcrResult:
    status: str  # "OK" or a "SKIPPED: ..." / "FAILED: ..." string
    text: str = ""

    @property
    def skipped(self):
        return self.status.startswith("SKIPPED")


def ocr_image(path, tesseract=None):
    """OCR an image. `tesseract` overrides the binary lookup (None = search PATH)."""
    binary = tesseract if tesseract is not None else shutil.which("tesseract")
    if not binary:
        return OcrResult(SKIPPED_MISSING)
    proc = subprocess.run([binary, str(path), "stdout"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return OcrResult(f"FAILED: tesseract exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    return OcrResult("OK", proc.stdout)
