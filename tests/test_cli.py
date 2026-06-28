import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

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


def test_cli_out_duration_and_extra_format(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    write_sound(
        sounds / "blip.py",
        """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.ones((100, 2), dtype=np.float32) * 0.1)
""".lstrip(),
    )
    out = tmp_path / "custom.wav"
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)

    cli.main(["blip", "--out", str(out), "--duration", "0.001", "--flac"])

    audio, sr = sf.read(out)
    assert out.is_file()
    assert out.with_suffix(".flac").is_file()
    assert len(audio) == round(sr * 0.001)


def test_cli_seed_reaches_dsp_noise(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    output = tmp_path / "output"
    sounds.mkdir()
    write_sound(
        sounds / "noise.py",
        """
from shipwright import sound, Buffer, dsp

@sound("noise")
def noise():
    return Buffer(dsp.to_stereo(dsp.noise(0.01, amp=0.2)))
""".lstrip(),
    )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)
    monkeypatch.setattr(config, "OUTPUT_DIR", output)

    cli.main(["noise", "--seed", "7"])
    first, _ = sf.read(output / "noise.wav")
    clear()
    cli.main(["noise", "--seed", "7"])
    second, _ = sf.read(output / "noise.wav")

    np.testing.assert_array_equal(first, second)


def test_cli_seed_is_deterministic_when_rendering_all_in_parallel(tmp_path, monkeypatch):
    sounds = tmp_path / "sounds"
    output = tmp_path / "output"
    sounds.mkdir()
    for name in ["a", "b"]:
        write_sound(
            sounds / f"{name}.py",
            f"""
from shipwright import sound, Buffer, dsp

@sound("{name}")
def build():
    return Buffer(dsp.to_stereo(dsp.noise(0.01, amp=0.2)))
""".lstrip(),
        )
    monkeypatch.setattr(config, "SOUNDS_DIR", sounds)
    monkeypatch.setattr(config, "OUTPUT_DIR", output)

    cli.main(["all", "--seed", "99", "--jobs", "2"])
    first_a, _ = sf.read(output / "a.wav")
    first_b, _ = sf.read(output / "b.wav")
    clear()
    cli.main(["all", "--seed", "99", "--jobs", "2"])
    second_a, _ = sf.read(output / "a.wav")
    second_b, _ = sf.read(output / "b.wav")

    np.testing.assert_array_equal(first_a, second_a)
    np.testing.assert_array_equal(first_b, second_b)


def test_cli_init_creates_minimal_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.main(["init", "game_audio"])

    root = tmp_path / "game_audio"
    assert (root / "shipwright.toml").is_file()
    assert (root / "sounds" / "starter_blip.py").is_file()
    assert len(list((root / "sounds").glob("*.py"))) == 1
    assert (root / "instruments" / "__init__.py").is_file()
    assert (root / "instruments" / "basic.py").is_file()
    assert (root / "soundfonts" / "README.md").is_file()
    assert (root / "output" / ".gitkeep").is_file()
    assert "created shipwright project" in capsys.readouterr().out


def test_cli_init_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli.main(["init", "."])

    assert (tmp_path / "shipwright.toml").is_file()
    assert (tmp_path / "sounds" / "starter_blip.py").is_file()


def test_cli_init_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init", "game_audio"])

    with pytest.raises(SystemExit, match="refusing to overwrite"):
        cli.main(["init", "game_audio"])

    cli.main(["init", "game_audio", "--force"])


def test_cli_init_project_renders_starter_sound(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init", "game_audio"])
    root = tmp_path / "game_audio"
    monkeypatch.chdir(root)
    monkeypatch.setattr(config, "ROOT", root)
    monkeypatch.setattr(config, "SOUNDS_DIR", root / "sounds")
    monkeypatch.setattr(config, "OUTPUT_DIR", root / "output")

    cli.main(["starter_blip"])

    assert (root / "output" / "starter_blip.wav").is_file()
