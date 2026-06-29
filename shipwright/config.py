"""Project configuration and resolved paths.

Shipwright is project-first: settings live in a project's ``shipwright.toml``,
and that file is also the marker used to locate the project. ``configure()``
walks up from a starting directory to the first ``shipwright.toml`` and resolves
the render defaults and data directories against it. It is called once at import
for the current directory, and again by the CLI once ``-C`` / discovery has run.

Two escape hatches remain for pointing the tool at a project without one:
``SHIPWRIGHT_ROOT`` (the project root) and ``SHIPWRIGHT_SOUNDS`` (the sounds
directory, handy for running the bundled examples).
"""
import os
import tomllib
from pathlib import Path

PROJECT_MARKER = "shipwright.toml"


def find_project_root(start=None):
    """Walk up from ``start`` (default cwd) to the first dir holding a
    ``shipwright.toml``. Falls back to ``start`` itself when no marker is found,
    so a bare directory with a ``sounds/`` folder still works."""
    start = Path(start).expanduser().resolve() if start else Path.cwd()
    if start.is_file():
        start = start.parent
    for d in (start, *start.parents):
        if (d / PROJECT_MARKER).is_file():
            return d
    return start


def _load_toml(root):
    """Load the whole ``shipwright.toml`` as a nested dict (tables and all)."""
    path = root / PROJECT_MARKER
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (ValueError, OSError) as e:
        # tomllib raises TOMLDecodeError (a ValueError). This runs at import, so
        # let the message through as a clean SystemExit instead of a traceback.
        raise SystemExit(f"could not parse {path}: {e}")


def _load_project_config(root):
    """The ``[shipwright]`` render settings (falls back to the file root)."""
    full = _load_toml(root)
    return full.get("shipwright", full)


def _resolve_dir(env, value):
    """A project directory: ``$env`` if set, else ``value`` anchored to ROOT."""
    if env and env in os.environ:
        return Path(os.environ[env]).expanduser()
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


def configure(start=None, sr=None):
    """Resolve ROOT, render defaults, and data dirs against a project root.

    Pass ``start`` to begin discovery somewhere other than the cwd (the CLI's
    ``-C/--project``). ``sr`` overrides the sample rate for this run.
    """
    global ROOT, PROJECT, BUILD, SR, BLOCK, MASTER_CEILING, TARGET_LUFS
    global EXPORT_SUBTYPE, DITHER, SOUNDS_DIR, SOUNDFONT_DIR, OUTPUT_DIR

    if "SHIPWRIGHT_ROOT" in os.environ:
        ROOT = Path(os.environ["SHIPWRIGHT_ROOT"]).expanduser().resolve()
    else:
        ROOT = find_project_root(start)
    full = _load_toml(ROOT)
    PROJECT = full.get("shipwright", full)
    BUILD = full.get("build") if isinstance(full.get("build"), dict) else {}

    SR = int(sr if sr is not None else PROJECT.get("sr", 44100))
    BLOCK = int(PROJECT.get("block", 512))
    MASTER_CEILING = float(PROJECT.get("master_ceiling", 0.97))
    TARGET_LUFS = None if PROJECT.get("target_lufs") is None else float(PROJECT["target_lufs"])
    EXPORT_SUBTYPE = str(PROJECT.get("export_subtype", "PCM_16"))
    DITHER = str(PROJECT.get("dither", "true")).lower() not in {"0", "false", "no"}

    SOUNDS_DIR = _resolve_dir("SHIPWRIGHT_SOUNDS", PROJECT.get("sounds_dir", "sounds"))
    SOUNDFONT_DIR = _resolve_dir(None, PROJECT.get("soundfont_dir", "soundfonts"))
    OUTPUT_DIR = _resolve_dir(None, PROJECT.get("output_dir", "output"))
    return ROOT


configure()
