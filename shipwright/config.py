"""Global settings + paths. One place to change sample rate / output dir.

Data dirs are anchored to the current working directory so the installed
command works in whatever project you run it from. Override any of them
with SHIPWRIGHT_ROOT, SHIPWRIGHT_SOUNDS, SHIPWRIGHT_OUTPUT, or
SHIPWRIGHT_SOUNDFONTS.
"""
import os
from pathlib import Path

SR = 44100          # sample rate for everything
BLOCK = 512         # DawDreamer render block size
MASTER_CEILING = 0.97  # peak limit so renders never clip the file


def _dir(env, default):
    return Path(os.environ[env]).expanduser() if env in os.environ else default


ROOT = _dir("SHIPWRIGHT_ROOT", Path.cwd())
SOUNDS_DIR = _dir("SHIPWRIGHT_SOUNDS", ROOT / "sounds")
SOUNDFONT_DIR = _dir("SHIPWRIGHT_SOUNDFONTS", ROOT / "soundfonts")
OUTPUT_DIR = _dir("SHIPWRIGHT_OUTPUT", ROOT / "output")
