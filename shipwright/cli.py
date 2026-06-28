"""The project CLI. Init a project, edit a file in sounds/, run this,
listen, repeat."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

from . import __version__, config
from .registry import Buffer, RenderSpec, clear, get, names


_INIT_FILES = {
    "shipwright.toml": """[shipwright]
sr = 44100
block = 512
master_ceiling = 0.97
target_lufs = -18
export_subtype = "PCM_16"
dither = true
sounds_dir = "sounds"
output_dir = "output"
""",
    ".gitignore": """# Rendered audio
output/*
!output/.gitkeep

# Python
__pycache__/
*.py[cod]

# macOS
.DS_Store
""",
    "sounds/starter_blip.py": '''from shipwright import Buffer, dsp, sound


@sound("starter_blip")
def starter_blip():
    tone = dsp.sine(880, 0.16, amp=0.45)
    click = dsp.noise(0.03, amp=0.04)
    sig = dsp.layer(tone, click)
    sig = dsp.ad_env(sig, attack=0.002, release=0.08)
    sig = dsp.lowpass(sig, 2400)
    return Buffer(dsp.to_stereo(dsp.normalize(sig, 0.7)))
''',
    "output/.gitkeep": "",
}


def load_sounds():
    if not config.SOUNDS_DIR.is_dir():
        raise SystemExit(
            f"no sounds directory at {config.SOUNDS_DIR}\n"
            "cd into a project with a sounds/ folder, or set SHIPWRIGHT_SOUNDS."
        )
    root = str(config.ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
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


def _display_path(path):
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def _seed_for_name(seed, name):
    digest = hashlib.blake2b(f"{seed}:{name}".encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def init_project(name, force=False):
    if not name:
        raise SystemExit("init needs a project name, e.g. shipwright init my_audio")

    root = Path.cwd() if name == "." else Path(name).expanduser()
    existing = [root / rel for rel in _INIT_FILES if (root / rel).exists()]
    if existing and not force:
        listed = ", ".join(str(_display_path(path)) for path in existing[:3])
        if len(existing) > 3:
            listed += f", +{len(existing) - 3} more"
        raise SystemExit(f"refusing to overwrite existing project files: {listed}\nuse --force to overwrite")

    root.mkdir(parents=True, exist_ok=True)
    for rel, body in _INIT_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    print(f"created shipwright project at {_display_path(root)}")
    print("  next: cd", _display_path(root))
    print("        shipwright starter_blip")


def _format_specs(args):
    specs = [("wav", "WAV", config.EXPORT_SUBTYPE)]
    if args.ogg:
        specs.append(("ogg", "OGG", "VORBIS"))
    if args.flac:
        specs.append(("flac", "FLAC", "PCM_16"))
    if args.mp3:
        specs.append(("mp3", "MP3", None))
    return specs


def _base_output(name, out, multiple):
    if out is None:
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return config.OUTPUT_DIR / f"{name}.wav"
    path = Path(out).expanduser()
    if multiple or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{name}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fit_duration(audio, sample_rate, duration):
    if duration is None:
        return audio
    frames = max(0, int(round(duration * sample_rate)))
    if len(audio) > frames:
        return audio[:frames]
    if len(audio) < frames:
        pad_shape = (frames - len(audio),) if audio.ndim == 1 else (frames - len(audio), audio.shape[1])
        pad = np.zeros(pad_shape, dtype=audio.dtype)
        return np.concatenate([audio, pad], axis=0)
    return audio


def _render_audio(name, duration=None, sample_rate_override=None):
    if name not in names():
        raise SystemExit(f"unknown sound '{name}'. Available sounds: {_available()}")

    obj = get(name)()
    if isinstance(obj, Buffer):
        from .engine import render_buffer

        audio = render_buffer(obj)
        sample_rate = sample_rate_override or obj.sr or config.SR
    elif isinstance(obj, RenderSpec):
        from .engine import render_spec

        if duration is not None:
            obj.duration = duration
        audio = render_spec(obj)
        sample_rate = config.SR
    else:
        raise SystemExit(
            f"sound '{name}' returned {type(obj).__name__}; expected Buffer or RenderSpec."
        )
    return obj, _fit_duration(audio, sample_rate, duration), sample_rate


def _write_formats(base, audio, sample_rate, formats, gain_db=0.0, target_lufs=None):
    from .engine import write_audio

    written = []
    for ext, fmt, subtype in formats:
        path = base.with_suffix(f".{ext}")
        write_audio(
            path,
            audio,
            sample_rate,
            format=fmt,
            subtype=subtype,
            gain_db=gain_db,
            target_lufs=target_lufs,
        )
        written.append(path)
    return written


def _write_stems(name, spec, base, gain_db=0.0, target_lufs=None):
    from .engine import render_stems, write_audio

    stem_dir = base.with_suffix("")
    stem_dir = stem_dir.parent / f"{stem_dir.name}_stems"
    stem_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for stem_name, audio in render_stems(spec).items():
        path = stem_dir / f"{stem_name}.wav"
        write_audio(path, audio, config.SR, format="WAV", gain_db=gain_db, target_lufs=target_lufs)
        written.append(path)
    return written


def _play(path):
    players = [
        ("afplay", [str(path)]),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]),
        ("aplay", [str(path)]),
        ("paplay", [str(path)]),
    ]
    for exe, args in players:
        found = shutil.which(exe)
        if found:
            subprocess.run([found, *args], check=False)
            return
    raise SystemExit("no audio player found; install ffplay or use the rendered file directly")


def render_one(name, args, multiple=False):
    if args.seed is not None:
        local_seed = _seed_for_name(args.seed, name)
        np.random.seed(local_seed)
        import shipwright.dsp as dsp
        import shipwright.engine as engine

        dsp.set_thread_seed(local_seed)
        engine.set_thread_seed(local_seed)
    obj, audio, sample_rate = _render_audio(name, duration=args.duration, sample_rate_override=args.sr)
    base = _base_output(name, args.out, multiple)
    written = _write_formats(
        base,
        audio,
        sample_rate,
        _format_specs(args),
        gain_db=args.gain,
        target_lufs=args.lufs if args.lufs is not None else config.TARGET_LUFS,
    )
    stem_count = 0
    if args.stems:
        if not isinstance(obj, RenderSpec):
            raise SystemExit("--stems only works for RenderSpec music sounds")
        stem_count = len(
            _write_stems(
                name,
                obj,
                base,
                gain_db=args.gain,
                target_lufs=args.lufs if args.lufs is not None else config.TARGET_LUFS,
            )
        )
    dur = len(audio) / sample_rate
    peak = abs(audio).max() if len(audio) else 0.0
    msg = f"  {name:14s} -> {_display_path(written[0])}   {dur:4.1f}s  peak {peak:.2f}"
    if len(written) > 1:
        msg += f"  +{len(written) - 1} format(s)"
    if stem_count:
        msg += f"  +{stem_count} stem(s)"
    if args.play:
        _play(written[0])
    return msg


def _snapshot():
    return {f: f.stat().st_mtime for f in config.SOUNDS_DIR.glob("*.py")}


def _changed(old, new):
    files = sorted({*old, *new})
    return [f for f in files if old.get(f) != new.get(f)]


def _render_targets(targets, args):
    if len(targets) > 1 and args.jobs != 1:
        jobs = min(args.jobs or os.cpu_count() or 1, len(targets))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            return list(pool.map(lambda t: render_one(t, args, multiple=True), targets))
    return [render_one(t, args, multiple=len(targets) > 1) for t in targets]


def build_init_parser():
    p = argparse.ArgumentParser(
        prog="shipwright init",
        description="Scaffold a new shipwright project.",
    )
    p.add_argument("name", help="project directory to create, or '.' for the current directory")
    p.add_argument("--force", action="store_true", help="overwrite existing project files")
    return p


def build_parser():
    p = argparse.ArgumentParser(
        prog="shipwright",
        description="Render sounds defined in a project's sounds/ to output/.",
        epilog="Run 'shipwright init NAME' to scaffold a new project.",
    )
    p.add_argument("target", nargs="?", help="sound name to render, or 'all'. Omit to list sounds.")
    p.add_argument("-C", "--project", metavar="DIR",
                   help="run as if started in DIR (walks up to find shipwright.toml)")
    p.add_argument("--out", help="output file for one target, or output directory for all")
    p.add_argument("--sr", type=int, help="override sample rate for this run")
    p.add_argument("--duration", type=float, help="override rendered duration in seconds")
    p.add_argument("--gain", type=float, default=0.0, help="post-render gain in dB")
    p.add_argument("--lufs", type=float, help="normalize to integrated LUFS before export")
    p.add_argument("--seed", type=int, help="seed numpy and shipwright noise")
    p.add_argument("--ogg", action="store_true", help="also write a Vorbis .ogg next to the .wav")
    p.add_argument("--flac", action="store_true", help="also write a FLAC next to the .wav")
    p.add_argument("--mp3", action="store_true", help="also write an MP3 if libsndfile supports it")
    p.add_argument("--stems", action="store_true", help="write per-track WAV stems for RenderSpec sounds")
    p.add_argument("--play", action="store_true", help="audition the rendered WAV after writing it")
    p.add_argument("--jobs", type=int, default=0, help="parallel jobs for rendering all; 1 disables parallelism")
    p.add_argument("--watch", action="store_true", help="re-render TARGET or all on every save (Ctrl-C to stop)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "init":
        init_args = build_init_parser().parse_args(argv[1:])
        init_project(init_args.name, force=init_args.force)
        return

    args = build_parser().parse_args(argv)

    config.configure(start=args.project, sr=args.sr)
    import shipwright.dsp as dsp
    dsp.SR = config.SR
    if args.seed is not None:
        np.random.seed(args.seed)
        dsp.set_seed(args.seed)

    if args.watch:
        if not args.target:
            raise SystemExit("--watch needs a sound name or 'all', e.g. shipwright --watch sea_bed")
        load_sounds()
        if args.target != "all" and args.target not in names():
            raise SystemExit(f"unknown sound '{args.target}'. Available sounds: {_available()}")
        print(f"watching {config.SOUNDS_DIR} - rendering '{args.target}' on save (Ctrl-C to stop)")

        last = _snapshot()
        try:
            targets = names() if args.target == "all" else [args.target]
            for line in _render_targets(targets, args):
                print(line)
        except Exception as e:
            print("  error:", e)
        try:
            while True:
                time.sleep(0.4)
                current = _snapshot()
                changed = _changed(last, current)
                if not changed:
                    continue
                last = current
                print("  changed:", ", ".join(str(_display_path(f)) for f in changed))
                try:
                    load_sounds()
                    targets = names() if args.target == "all" else [args.target]
                    for line in _render_targets(targets, args):
                        print(line)
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
    for line in _render_targets(targets, args):
        print(line)


if __name__ == "__main__":
    main()
