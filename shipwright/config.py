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
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None

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
    if tomllib is not None:
        with path.open("rb") as f:
            return tomllib.load(f)
    return _load_simple_toml(path)


def _load_project_config(root):
    """The ``[shipwright]`` render settings (falls back to the file root)."""
    full = _load_toml(root)
    return full.get("shipwright", full)


def _parse_scalar(value):
    if value.startswith(("\"", "'")) and value.endswith(("\"", "'")):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return float(value)


def _parse_value(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",") if item.strip()]
    return _parse_scalar(value)


def _load_simple_toml(path):
    """Small fallback for Python 3.10: scalars and one-line arrays under the
    ``[shipwright]``, ``[build]`` and ``[build.<name>]`` tables."""
    data = {}
    section = []  # the keys identifying the current table; [] is the file root
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = [part.strip() for part in line[1:-1].split(".")]
            target = data
            for key in section:
                target = target.setdefault(key, {})
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        target = data
        for part in section:
            target = target.setdefault(part, {})
        target[key] = _parse_value(value)
    return data


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
