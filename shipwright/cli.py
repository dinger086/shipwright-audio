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
from types import SimpleNamespace

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

[build]
# `shipwright build` renders these targets to these formats.
# "all" (the default) means every sound in sounds/.
targets = ["all"]
formats = ["wav"]

# Per-sound overrides merge over the [build] defaults, e.g.:
# [build.starter_blip]
# formats = ["wav", "flac"]
# lufs = -16
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


def _ensure_known(targets):
    unknown = [t for t in targets if t not in names()]
    if unknown:
        raise SystemExit(f"unknown sound '{unknown[0]}'. Available sounds: {_available()}")


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
    print("        shipwright build")


_FORMAT_SPECS = {
    "wav": ("wav", "WAV", None),  # subtype filled from the project config at use
    "ogg": ("ogg", "OGG", "VORBIS"),
    "flac": ("flac", "FLAC", "PCM_16"),
    "mp3": ("mp3", "MP3", None),
}


def _specs_for_formats(formats):
    specs, seen = [], set()
    for fmt in formats:
        key = str(fmt).lower()
        if key in seen:
            continue
        seen.add(key)
        if key not in _FORMAT_SPECS:
            raise SystemExit(f"unknown format '{fmt}'. Known formats: wav, ogg, flac, mp3")
        ext, name, subtype = _FORMAT_SPECS[key]
        specs.append((ext, name, config.EXPORT_SUBTYPE if key == "wav" else subtype))
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
        try:
            write_audio(
                path,
                audio,
                sample_rate,
                format=fmt,
                subtype=subtype,
                gain_db=gain_db,
                target_lufs=target_lufs,
            )
        except Exception as e:
            # WAV is the primary deliverable; anything else (e.g. MP3 without
            # libsndfile support) is skipped with a warning so the build goes on.
            if fmt == "WAV":
                raise
            print(f"  ! skipped {ext}: {e}")
            continue
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


def _resolve_target_options(name, a):
    """Merge the build config for ``name``: ``[build]`` defaults, then the
    per-target ``[build.<name>]`` table, then any one-off CLI flags on top."""
    bld = config.BUILD or {}
    glob = {k: v for k, v in bld.items() if not isinstance(v, dict)}
    over = bld[name] if isinstance(bld.get(name), dict) else {}

    def pick(cli, key, default):
        if cli is not None:
            return cli
        if key in over:
            return over[key]
        if key in glob:
            return glob[key]
        return default

    formats = list(pick(None, "formats", ["wav"]))
    for fmt, on in (("ogg", a.ogg), ("flac", a.flac), ("mp3", a.mp3)):
        if on and fmt not in formats:
            formats.append(fmt)

    return SimpleNamespace(
        seed=pick(a.seed, "seed", None),
        duration=pick(a.duration, "duration", None),
        sr=pick(a.sr, "sr", None),
        out=a.out,
        gain=pick(a.gain, "gain", 0.0),
        lufs=pick(a.lufs, "lufs", config.TARGET_LUFS),
        stems=bool(pick(a.stems, "stems", False)),
        play=a.play,
        formats=formats,
    )


def render_one(name, opts, multiple=False):
    if opts.seed is not None:
        local_seed = _seed_for_name(opts.seed, name)
        np.random.seed(local_seed)
        import shipwright.dsp as dsp
        import shipwright.engine as engine

        dsp.set_thread_seed(local_seed)
        engine.set_thread_seed(local_seed)
    obj, audio, sample_rate = _render_audio(name, duration=opts.duration, sample_rate_override=opts.sr)
    base = _base_output(name, opts.out, multiple)
    written = _write_formats(
        base,
        audio,
        sample_rate,
        _specs_for_formats(opts.formats),
        gain_db=opts.gain,
        target_lufs=opts.lufs,
    )
    stem_count = 0
    if opts.stems:
        if not isinstance(obj, RenderSpec):
            raise SystemExit("--stems only works for RenderSpec music sounds")
        stem_count = len(
            _write_stems(name, obj, base, gain_db=opts.gain, target_lufs=opts.lufs)
        )
    dur = len(audio) / sample_rate
    peak = abs(audio).max() if len(audio) else 0.0
    primary = written[0] if written else base
    msg = f"  {name:14s} -> {_display_path(primary)}   {dur:4.1f}s  peak {peak:.2f}"
    if len(written) > 1:
        msg += f"  +{len(written) - 1} format(s)"
    if stem_count:
        msg += f"  +{stem_count} stem(s)"
    if opts.play and written:
        _play(written[0])
    return msg


def _watch_paths():
    """Files a ``--watch`` session reacts to: the project's sounds, any shared
    modules at the project root (e.g. a ``my_instruments.py``), and
    ``shipwright.toml`` itself so edits to ``[build]`` re-render."""
    paths = list(config.SOUNDS_DIR.glob("*.py"))
    paths += list(config.ROOT.glob("*.py"))
    toml = config.ROOT / config.PROJECT_MARKER
    if toml.is_file():
        paths.append(toml)
    return paths


def _snapshot():
    snap = {}
    for f in _watch_paths():
        try:
            snap[f] = f.stat().st_mtime
        except OSError:
            continue
    return snap


def _changed(old, new):
    files = sorted({*old, *new})
    return [f for f in files if old.get(f) != new.get(f)]


def _resolve_targets(cli_targets):
    """The sounds to build: CLI args win, else ``[build].targets``; an empty
    list or a literal ``"all"`` means every sound in the project."""
    chosen = list(cli_targets) if cli_targets else list((config.BUILD or {}).get("targets", []))
    if not chosen or "all" in chosen:
        return names()
    return chosen


def _resolve_jobs(a):
    if a.jobs is not None:
        jobs = a.jobs
    else:
        jobs = (config.BUILD or {}).get("jobs")
        jobs = 0 if jobs is None else jobs
    if jobs < 0:
        raise SystemExit(f"--jobs must be 0 (all CPUs) or a positive count, got {jobs}")
    return jobs


def _render_build(targets, a):
    jobs = _resolve_jobs(a)
    multiple = len(targets) > 1

    def render(name):
        return render_one(name, _resolve_target_options(name, a), multiple=multiple)

    if multiple and jobs != 1:
        n = min(jobs or os.cpu_count() or 1, len(targets))
        with ThreadPoolExecutor(max_workers=n) as pool:
            return list(pool.map(render, targets))
    return [render(t) for t in targets]


def _preflight(targets, a):
    """Validate ``--jobs`` and each target's formats before the build is
    announced, so a bad value errors up front instead of after the
    optimistic "building N sound(s)" line."""
    _resolve_jobs(a)
    for name in targets:
        _specs_for_formats(_resolve_target_options(name, a).formats)


def build_parser():
    p = argparse.ArgumentParser(
        prog="shipwright",
        description="Render the sounds defined in a project's sounds/ to output/.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    pi = sub.add_parser("init", help="scaffold a new shipwright project")
    pi.add_argument("name", help="project directory to create, or '.' for the current directory")
    pi.add_argument("--force", action="store_true", help="overwrite existing project files")

    pl = sub.add_parser("list", help="list the sounds available in the project")
    pl.add_argument("-C", "--project", metavar="DIR",
                    help="run as if started in DIR (walks up to find shipwright.toml)")

    pb = sub.add_parser("build", help="render sounds as described in shipwright.toml")
    pb.add_argument("targets", nargs="*",
                    help="sound names to render; omit to build [build].targets (default: all)")
    pb.add_argument("-C", "--project", metavar="DIR",
                    help="run as if started in DIR (walks up to find shipwright.toml)")
    pb.add_argument("--out", help="output file for one target, or output directory for many")
    pb.add_argument("--sr", type=int, default=None, help="override sample rate for this run")
    pb.add_argument("--duration", type=float, default=None, help="override rendered duration in seconds")
    pb.add_argument("--gain", type=float, default=None, help="post-render gain in dB")
    pb.add_argument("--lufs", type=float, default=None, help="normalize to integrated LUFS before export")
    pb.add_argument("--seed", type=int, default=None, help="seed numpy and shipwright noise")
    pb.add_argument("--ogg", action="store_true", help="also write a Vorbis .ogg")
    pb.add_argument("--flac", action="store_true", help="also write a FLAC")
    pb.add_argument("--mp3", action="store_true", help="also write an MP3 if libsndfile supports it")
    pb.add_argument("--stems", action="store_const", const=True, default=None,
                    help="write per-track WAV stems for RenderSpec sounds")
    pb.add_argument("--play", action="store_true", help="audition the rendered WAV after writing it")
    pb.add_argument("--jobs", type=int, default=None,
                    help="parallel jobs for building many; 1 disables parallelism")
    pb.add_argument("--watch", action="store_true", help="re-render on every save (Ctrl-C to stop)")
    return p


def _reconfigure(args):
    """(Re)resolve the project config and propagate the sample rate to dsp.
    Shared by ``main`` at startup and ``--watch`` when ``shipwright.toml`` changes."""
    config.configure(start=args.project, sr=getattr(args, "sr", None))
    import shipwright.dsp as dsp
    dsp.SR = config.SR


def _watch(args):
    # Watch output is often redirected or piped; keep it line-buffered so each
    # render shows up promptly instead of sitting in a block buffer.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    load_sounds()
    targets = _resolve_targets(args.targets)
    _ensure_known(targets)
    label = ", ".join(targets) if targets else "(none)"
    print(f"watching {config.SOUNDS_DIR} - rendering {label} on save (Ctrl-C to stop)")

    def render():
        try:
            for line in _render_build(_resolve_targets(args.targets), args):
                print(line)
        except (Exception, SystemExit) as e:
            # A typo in a sound or shipwright.toml shouldn't kill the watcher;
            # report it and keep waiting for the next save. SystemExit is caught
            # too since the CLI uses it for user-facing errors (and it is not an
            # Exception). KeyboardInterrupt still propagates to stop the watch.
            print("  error:", e)

    last = _snapshot()
    render()
    try:
        while True:
            time.sleep(0.4)
            current = _snapshot()
            changed = _changed(last, current)
            if not changed:
                continue
            last = current
            print("  changed:", ", ".join(str(_display_path(f)) for f in changed))
            toml_changed = any(f.name == config.PROJECT_MARKER for f in changed)
            try:
                if toml_changed:
                    _reconfigure(args)
                load_sounds()
            except (Exception, SystemExit) as e:
                print("  error:", e)
                continue
            render()
            if toml_changed:
                last = _snapshot()  # config may have moved the watched set
    except KeyboardInterrupt:
        print("\nstopped.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.command == "init":
        init_project(args.name, force=args.force)
        return
    if args.command is None:
        build_parser().print_help()
        return

    _reconfigure(args)

    if args.command == "list":
        load_sounds()
        print("sounds:", _available())
        return

    # args.command == "build"
    if args.watch:
        _watch(args)
        return

    load_sounds()
    targets = _resolve_targets(args.targets)
    if not targets:
        print("no sounds to build")
        return
    _ensure_known(targets)
    _preflight(targets, args)
    print(f"building {len(targets)} sound(s) @ {config.SR} Hz")
    for line in _render_build(targets, args):
        print(line)


if __name__ == "__main__":
    main()
