"""Gedeeld voor alle tests: een eigen tijdelijke map voor mijn-trial-reels en de sleutel, en de scripts op het pad."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="trs-test-"))
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
os.environ["TRS_MIJN"] = str(TMP / "mijn")
os.environ.pop("ZERNIO_API_KEY", None)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "engine" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def maak_video(pad, breedte, hoogte, seconden, geluid=True, extra=()):
    """Een proefvideo met ffmpeg (testbeeld, en een toon als er geluid moet zijn)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"testsrc2=s={breedte}x{hoogte}:r=25:d={seconden}"]
    if geluid:
        cmd += ["-f", "lavfi", "-i", f"sine=f=440:d={seconden}", "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", *extra, str(pad)]
    subprocess.run(cmd, check=True)
    return pad
