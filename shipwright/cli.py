"""The harness, as a console command. The whole point: edit a file in
sounds/, run this, listen.

    shipwright                 list all sounds
    shipwright sea_bed         render one -> output/sea_bed.wav
    shipwright all             render everything
    shipwright sea_bed --ogg   also write a Vorbis .ogg
    shipwright --watch sea_bed re-render on every save (tight loop)

Sounds are loaded from ./sounds and written to ./output relative to the
current directory (override with SHIPWRIGHT_ROOT / SHIPWRIGHT_SOUNDS /
SHIPWRIGHT_OUTPUT).
"""
import argparse
import importlib.util
from pathlib import Path
import time

from . import __version__, config
from .registry import Buffer, RenderSpec, clear, get, names


def load_sounds():
    if not config.SOUNDS_DIR.is_dir():
        raise SystemExit(
            f"no sounds directory at {config.SOUNDS_DIR}\n"
            "cd into a project with a sounds/ folder, or set SHIPWRIGHT_SOUNDS."
        )
    clear()
    for f in sorted(config.SOUNDS_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        if spec is None or spec.loader is None:
            raise SystemExit(f"could not load sound file: {f}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


def _available():
    sound_names = names()
    return ", ".join(sound_names) if sound_names else "(none)"


def _output_path(name):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return config.OUTPUT_DIR / f"{name}.wav"


def _display_path(path):
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def render_one(name, ogg=False):
    if name not in names():
        raise SystemExit(f"unknown sound '{name}'. Available sounds: {_available()}")

    obj = get(name)()
    if isinstance(obj, Buffer):
        from .engine import render_buffer
        audio = render_buffer(obj)
        sample_rate = obj.sr
    elif isinstance(obj, RenderSpec):
        from .engine import render_spec
        audio = render_spec(obj)
        sample_rate = config.SR
    else:
        raise SystemExit(
            f"sound '{name}' returned {type(obj).__name__}; expected Buffer or RenderSpec."
        )

    import soundfile as sf

    out = _output_path(name)
    sf.write(out, audio, sample_rate)
    if ogg:
        sf.write(out.with_suffix(".ogg"), audio, sample_rate, format="OGG", subtype="VORBIS")
    dur = len(audio) / sample_rate
    peak = abs(audio).max() if len(audio) else 0.0
    print(f"  {name:14s} -> {_display_path(out)}   {dur:4.1f}s  peak {peak:.2f}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="shipwright",
        description="Render sounds defined in ./sounds to ./output.",
    )
    p.add_argument("target", nargs="?",
                   help="sound name to render, or 'all'. Omit to list sounds.")
    p.add_argument("--ogg", action="store_true",
                   help="also write a Vorbis .ogg next to the .wav")
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
        if args.target not in names():
            raise SystemExit(f"unknown sound '{args.target}'. Available sounds: {_available()}")
        print(f"watching {config.SOUNDS_DIR} — rendering '{args.target}' on save (Ctrl-C to stop)")

        def _mtime():
            return max((f.stat().st_mtime for f in config.SOUNDS_DIR.glob("*.py")), default=0)

        last = _mtime()
        try:
            render_one(args.target, args.ogg)   # initial render from the load above
        except Exception as e:
            print("  error:", e)
        try:
            while True:
                time.sleep(0.4)
                m = _mtime()
                if m == last:
                    continue
                last = m
                try:
                    load_sounds()
                    render_one(args.target, args.ogg)
                except Exception as e:
                    print("  error:", e)
        except KeyboardInterrupt:
            print("\nstopped.")
            return

    load_sounds()
    if not args.target:
        print("sounds:", _available())
        return
    targets = names() if args.target == "all" else [args.target]
    print(f"rendering {len(targets)} sound(s) @ {config.SR} Hz")
    for t0 in targets:
        render_one(t0, args.ogg)


if __name__ == "__main__":
    main()
