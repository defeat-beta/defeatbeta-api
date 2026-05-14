"""Recalculate formula cells in an .xlsx via LibreOffice headless.

openpyxl writes formula strings but does not evaluate them, so previewers
that rely on cached values (including Claude's file preview) show blanks
until the workbook is opened in a real spreadsheet app. This script
re-opens the file under `libreoffice --headless --calc`, lets it evaluate
every formula, and writes the cached values back into the same file.

If LibreOffice is not installed, prints a warning and exits 0 — the
workbook is still valid for Excel / Numbers / WPS users who will get
on-open recalc for free.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


LIBREOFFICE_BINARIES = (
    "libreoffice",
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def find_libreoffice() -> str | None:
    for candidate in LIBREOFFICE_BINARIES:
        # Absolute path: check existence directly.
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def recalc(xlsx_path: str) -> int:
    if not os.path.isfile(xlsx_path):
        print(f"error: {xlsx_path} does not exist", file=sys.stderr)
        return 1

    binary = find_libreoffice()
    if binary is None:
        print(
            "warning: LibreOffice not found on PATH. Skipping recalc. "
            "The workbook is valid but previewers may show blank cells "
            "until you open it in Excel / Numbers / WPS.",
            file=sys.stderr,
        )
        return 0

    xlsx_path = os.path.abspath(xlsx_path)
    out_dir = os.path.dirname(xlsx_path)
    target_name = os.path.basename(xlsx_path)

    # LibreOffice won't overwrite the source file when output dir equals
    # input dir — convert into a temp dir first, then move back over.
    with tempfile.TemporaryDirectory(prefix="dcf_recalc_") as tmpdir:
        cmd = [
            binary,
            "--headless",
            "--calc",
            "--convert-to",
            "xlsx",
            "--outdir",
            tmpdir,
            xlsx_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("error: LibreOffice recalc timed out after 120s", file=sys.stderr)
            return 2

        if result.returncode != 0:
            print(
                "error: LibreOffice exited with status "
                f"{result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                file=sys.stderr,
            )
            return result.returncode

        recalculated = os.path.join(tmpdir, target_name)
        if not os.path.isfile(recalculated):
            print(
                f"error: expected output file {recalculated} not produced by LibreOffice",
                file=sys.stderr,
            )
            return 3

        shutil.move(recalculated, xlsx_path)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path", help="Path to the .xlsx file to recalculate.")
    args = parser.parse_args()
    return recalc(args.xlsx_path)


if __name__ == "__main__":
    sys.exit(main())
