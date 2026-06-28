"""The harness, as a console command. The whole point: edit a file in
sounds/, run this, listen.

    shipwright                 list all sounds
    shipwright sea_bed         render one -> output/sea_bed.wav
    shipwright all             render everything
    shipwright sea_bed --ogg   also write a Godot-ready .ogg
    shipwright --watch sea_bed re-render on every save (tight loop)

Sounds are loaded from ./sounds and written to ./output relative to the
current directory (override with SHIPWRIGHT_ROOT / SHIPWRIGHT_SOUNDS /
SHIPWRIGHT_OUTPUT).
"""
import argparse
import importlib.util
import time

import soundfile as sf

from . import __version__, config
from .engine import render_buffer, render_spec
from .registry import Buffer, get, names


def load_sounds():
    if not config.SOUNDS_DIR.is_dir():
        raise SystemExit(
            f"no sounds directory at {config.SOUNDS_DIR}\n"
            "cd into a project with a sounds/ folder, or set SHIPWRIGHT_SOUNDS."
        )
    for f in sorted(config.SOUNDS_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


def render_one(name, ogg=False):
    obj = get(name)()
    audio = render_buffer(obj) if isinstance(obj, Buffer) else render_spec(obj)
    out = config.OUTPUT_DIR / f"{name}.wav"
    sf.write(out, audio, config.SR)
    if ogg:
        sf.write(out.with_suffix(".ogg"), audio, config.SR, format="OGG", subtype="VORBIS")
    dur = len(audio) / config.SR
    print(f"  {name:14s} -> output/{out.name}   {dur:4.1f}s  peak {abs(audio).max():.2f}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="shipwright",
        description="Render sounds defined in ./sounds to ./output.",
    )
    p.add_argument("target", nargs="?",
                   help="sound name to render, or 'all'. Omit to list sounds.")
    p.add_argument("--ogg", action="store_true",
                   help="also write a Godot-ready .ogg next to the .wav")
    p.add_argument("--watch", action="store_true",
                   help="re-render TARGET on every save (Ctrl-C to stop)")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.watch:
        if not args.target:
            raise SystemExit("--watch needs a sound name, e.g. shipwright --watch sea_bed")
        load_sounds()
        print(f"watching {config.SOUNDS_DIR} — rendering '{args.target}' on save (Ctrl-C to stop)")
        last = 0
        while True:
            m = max((f.stat().st_mtime for f in config.SOUNDS_DIR.glob("*.py")), default=0)
            if m != last:
                last = m
                try:
                    load_sounds()
                    render_one(args.target, args.ogg)
                except Exception as e:
                    print("  error:", e)
            time.sleep(0.4)

    load_sounds()
    if not args.target:
        print("sounds:", ", ".join(names()))
        return
    targets = names() if args.target == "all" else [args.target]
    print(f"rendering {len(targets)} sound(s) @ {config.SR} Hz")
    for t0 in targets:
        render_one(t0, args.ogg)


if __name__ == "__main__":
    main()
