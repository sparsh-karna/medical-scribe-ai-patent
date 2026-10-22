#!/usr/bin/env python3
"""
Download PriMock57 consultation audio (Babylon Health, CC-BY 4.0) for the
audio-input pipeline. Each consultation has separate doctor and patient
channels (16 kHz mono WAV), matching the transcripts in
sample_data/primock57_library/.

  python scripts/download_primock57_audio.py day1_consultation01 day2_consultation05
  python scripts/download_primock57_audio.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/babylonhealth/primock57/raw/main/audio"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data" / "primock57_audio"
LIBRARY = ROOT / "sample_data" / "primock57_library"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("consultations", nargs="*", help="e.g. day1_consultation01")
    parser.add_argument("--all", action="store_true", help="download all 57 consultations (~1.6 GB)")
    args = parser.parse_args()

    if args.all:
        names = sorted(p.stem for p in LIBRARY.glob("day*_consultation*.json"))
    else:
        names = args.consultations
    if not names:
        parser.error("name at least one consultation, or pass --all")

    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        for role in ("doctor", "patient"):
            dest = OUT / f"{name}_{role}.wav"
            if dest.exists():
                print(f"exists  {dest.name}")
                continue
            url = f"{BASE}/{name}_{role}.wav"
            try:
                with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
                    f.write(resp.read())
            except Exception as e:
                print(f"FAILED  {url}: {e}", file=sys.stderr)
                continue
            print(f"saved   {dest.name} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
