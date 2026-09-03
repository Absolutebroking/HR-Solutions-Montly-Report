#!/usr/bin/env python3
"""
Refresh every month's dashboard data in one go.

Walks every "<Fiscal Year>/<Month>" folder next to this script (e.g.
"2026-2027/August-2026"), and for any folder that has a punches.csv in it,
runs process.py against that folder — regenerating that month's
attendance_data.json and data.js from whatever is currently in its CSVs.

Folders that don't have a punches.csv yet (months you haven't filled in)
are skipped quietly — that's expected for future months.

You don't need to run this directly: double-click refresh_dashboard.bat
(Windows) or refresh_dashboard.command (Mac), which call this for you.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROCESS_SCRIPT = os.path.join(ROOT, "process.py")


def find_month_folders():
    """Any second-level folder under a fiscal-year folder, e.g. 2026-2027/August-2026."""
    folders = []
    for entry in sorted(os.listdir(ROOT)):
        fy_path = os.path.join(ROOT, entry)
        # A fiscal-year folder looks like "2026-2027" — has a hyphen, both sides numeric.
        if not os.path.isdir(fy_path):
            continue
        parts = entry.split("-")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            continue
        for sub in sorted(os.listdir(fy_path)):
            month_path = os.path.join(fy_path, sub)
            if os.path.isdir(month_path):
                folders.append(os.path.join(entry, sub))
    return folders


def main():
    month_folders = find_month_folders()
    if not month_folders:
        print("No fiscal-year/month folders found next to this script (e.g. 2026-2027/August-2026).")
        return

    processed, skipped, failed = [], [], []

    for rel_folder in month_folders:
        abs_folder = os.path.join(ROOT, rel_folder)
        punches_path = os.path.join(abs_folder, "punches.csv")
        if not os.path.exists(punches_path):
            skipped.append(rel_folder)
            continue

        # Skip an untouched template (header row only, no data rows yet).
        with open(punches_path, encoding="utf-8-sig") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        if len(lines) <= 1:
            skipped.append(rel_folder)
            continue

        print(f"\n=== {rel_folder} " + "=" * max(1, 60 - len(rel_folder)))
        result = subprocess.run(
            [sys.executable, PROCESS_SCRIPT, rel_folder],
            cwd=ROOT,
        )
        if result.returncode == 0:
            processed.append(rel_folder)
        else:
            failed.append(rel_folder)

    print("\n" + "=" * 64)
    print(f"Processed {len(processed)} month(s): {', '.join(processed) if processed else '(none)'}")
    if skipped:
        print(f"Skipped {len(skipped)} empty/template month(s) — nothing entered yet.")
    if failed:
        print(f"⚠ {len(failed)} month(s) failed to process: {', '.join(failed)} — see errors above.")
    print("=" * 64)


if __name__ == "__main__":
    main()
