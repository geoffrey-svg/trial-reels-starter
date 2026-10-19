#!/usr/bin/env python3
"""
Eén voorbeeldbeeld in de eigen stijl, om te laten zien hoe de tekst in beeld eruitziet.

    python3 engine/scripts/voorbeeld.py                         op een effen achtergrond
    python3 engine/scripts/voorbeeld.py --video clip.mp4         op een beeld uit een eigen video
    python3 engine/scripts/voorbeeld.py --tekst "Eigen tekst"

Het beeld komt in mijn-trial-reels/voorbeeld-<tijd>.jpg.
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

from instellingen import MIJN, InstellingFout, in_woorden, laad
from maak_reels import FFMPEG, RondeFout, hdr_filter, meet, passend
from tekstblok import CANVAS, TekstFout, render

VOORBEELDTEKST = "Dit doen de meeste mensen fout met hun reels 👇"


def achtergrond(video):
    if not video:
        return Image.new("RGBA", CANVAS, (88, 104, 122, 255))
    with tempfile.TemporaryDirectory() as d:
        beeld = Path(d) / "beeld.png"
        # Precies zoals bij het maken: bijna staand bijsnijden, anders vullen met een wazige versie
        m = meet(Path(video))
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(video), "-frames:v", "1",
                            "-filter_complex", (hdr_filter() if m["hdr"] else "") + passend(m), str(beeld)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not beeld.exists():
            sys.exit(f"Kon geen beeld uit {video} halen.")
        return Image.open(beeld).convert("RGBA")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video")
    ap.add_argument("--tekst", default=VOORBEELDTEKST)
    a = ap.parse_args()
    try:
        cfg = laad()
        beeld = achtergrond(a.video)
        beeld.alpha_composite(render(a.tekst.replace("\\n", "\n"), cfg))
    except (InstellingFout, TekstFout, RondeFout) as e:
        sys.exit(str(e))
    MIJN.mkdir(parents=True, exist_ok=True)
    uit = MIJN / f"voorbeeld-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    beeld.convert("RGB").save(uit, quality=90)
    print(in_woorden(cfg))
    print(f"Voorbeeld: {uit}")


if __name__ == "__main__":
    main()
