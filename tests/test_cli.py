import os
from pathlib import Path

import numpy as np
import pytest

from shipwright import cli
from shipwright import config
from shipwright.registry import clear


def write_sound(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_registry():
    clear()
    yield
    clear()


def test_import_does_not_create_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert not Path("output").exists()


def test_cli_lists_sounds(tmp_path, monkeypatch, capsys):
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    write_sound(
        sounds / "blip.py",
        """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.zeros((8, 2), dtype=np.float32))
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")

    cli.main([])

    assert capsys.readouterr().out.strip() == "sounds: blip"
    assert not (tmp_path / "output").exists()


def test_cli_unknown_sound_has_friendly_error(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    write_sound(
        sounds / "blip.py",
        """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.zeros((8, 2), dtype=np.float32))
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)

    with pytest.raises(SystemExit, match="unknown sound 'missing'. Available sounds: blip"):
        cli.main(["missing"])


def test_cli_renders_buffer_sound(tmp_path, monkeypatch, capsys):
    sounds = tmp_path / "sounds"
    output = tmp_path / "rendered"
    sounds.mkdir()
    write_sound(
        sounds / "blip.py",
        """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.zeros((16, 2), dtype=np.float32))
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)
    monkeypatch.setattr(config, "OUTPUT_DIR", output)

    cli.main(["blip"])

    assert (output / "blip.wav").is_file()
    assert "blip" in capsys.readouterr().out


def test_cli_rejects_invalid_sound_return(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    write_sound(
        sounds / "bad.py",
        """
from shipwright import sound

@sound("bad")
def bad():
    return object()
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)

    with pytest.raises(SystemExit, match="expected Buffer or RenderSpec"):
        cli.main(["bad"])


def test_cli_routes_render_spec_without_real_dawdreamer(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    output = tmp_path / "output"
    sounds.mkdir()
    write_sound(
        sounds / "song.py",
        """
from shipwright import sound, RenderSpec

@sound("song")
def song():
    return RenderSpec(tracks=[])
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)
    monkeypatch.setattr(config, "OUTPUT_DIR", output)

    def fake_render_spec(spec):
        return np.zeros((16, 2), dtype=np.float32)

    import shipwright.engine

    monkeypatch.setattr(shipwright.engine, "render_spec", fake_render_spec)

    cli.main(["song"])

    assert (output / "song.wav").is_file()
