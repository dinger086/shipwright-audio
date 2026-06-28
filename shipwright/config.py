"""Global settings + paths. One place to change sample rate / output dir.

Data dirs are anchored to the current working directory so the installed
command works in whatever project you run it from. Override any of them
with SHIPWRIGHT_ROOT, SHIPWRIGHT_SOUNDS, SHIPWRIGHT_OUTPUT, or
SHIPWRIGHT_SOUNDFONTS.
"""
import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None


def _load_project_config(root):
    path = root / "shipwright.toml"
    if not path.is_file():
        return {}
    if tomllib is not None:
        with path.open("rb") as f:
            data = tomllib.load(f)
        return data.get("shipwright", data)
    return _load_simple_toml(path)


def _load_simple_toml(path):
    """Small fallback for Python 3.10: top-level key = scalar pairs only."""
    data = {}
    active = data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line == "[shipwright]":
            active = data
            continue
        if line.startswith("["):
            active = {}
            continue
        if "=" not in line or active is not data:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")):
            parsed = value[1:-1]
        elif value.lower() in {"true", "false"}:
            parsed = value.lower() == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = float(value)
        data[key] = parsed
    return data


def _dir(env, default):
    return Path(os.environ[env]).expanduser() if env in os.environ else default


def _project_path(key, default):
    value = Path(_PROJECT.get(key, default)).expanduser()
    return value if value.is_absolute() else ROOT / value


ROOT = _dir("SHIPWRIGHT_ROOT", Path.cwd())
_PROJECT = _load_project_config(ROOT)

SR = int(os.environ.get("SHIPWRIGHT_SR", _PROJECT.get("sr", 44100)))
BLOCK = int(os.environ.get("SHIPWRIGHT_BLOCK", _PROJECT.get("block", 512)))
MASTER_CEILING = float(
    os.environ.get("SHIPWRIGHT_MASTER_CEILING", _PROJECT.get("master_ceiling", 0.97))
)
TARGET_LUFS = (
    None
    if _PROJECT.get("target_lufs") is None and "SHIPWRIGHT_TARGET_LUFS" not in os.environ
    else float(os.environ.get("SHIPWRIGHT_TARGET_LUFS", _PROJECT.get("target_lufs")))
)
EXPORT_SUBTYPE = str(os.environ.get("SHIPWRIGHT_EXPORT_SUBTYPE", _PROJECT.get("export_subtype", "PCM_16")))
DITHER = str(os.environ.get("SHIPWRIGHT_DITHER", _PROJECT.get("dither", "true"))).lower() not in {
    "0",
    "false",
    "no",
}

SOUNDS_DIR = _dir("SHIPWRIGHT_SOUNDS", _project_path("sounds_dir", ROOT / "sounds"))
SOUNDFONT_DIR = _dir("SHIPWRIGHT_SOUNDFONTS", _project_path("soundfont_dir", ROOT / "soundfonts"))
OUTPUT_DIR = _dir("SHIPWRIGHT_OUTPUT", _project_path("output_dir", ROOT / "output"))
