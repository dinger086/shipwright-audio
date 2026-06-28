from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from shipwright import cli
from shipwright import config
from shipwright.registry import clear


def make_project(root: Path, sounds: dict[str, str], toml: str = "[shipwright]\n") -> None:
    """Write a minimal project: shipwright.toml (the marker) plus sounds/."""
    (root / "shipwright.toml").write_text(toml, encoding="utf-8")
    sdir = root / "sounds"
    sdir.mkdir(exist_ok=True)
    for name, body in sounds.items():
        (sdir / f"{name}.py").write_text(body.lstrip(), encoding="utf-8")


BLIP = """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.zeros((16, 2), dtype=np.float32))
"""


@pytest.fixture(autouse=True)
def reset_registry():
    clear()
    yield
    clear()


def test_import_does_not_create_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert not Path("output").exists()


def test_find_project_root_walks_up_to_marker(tmp_path):
    (tmp_path / "shipwright.toml").write_text("[shipwright]\n", encoding="utf-8")
    nested = tmp_path / "sounds" / "deep"
    nested.mkdir(parents=True)

    assert config.find_project_root(nested) == tmp_path


def test_cli_lists_sounds(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"blip": BLIP})

    cli.main(["list"])

    assert capsys.readouterr().out.strip() == "sounds: blip"
    assert not (tmp_path / "output").exists()


def test_cli_without_project_shows_help(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.main([])

    out = capsys.readouterr().out
    assert "usage: shipwright" in out
    assert "init" in out and "build" in out
    assert not (tmp_path / "output").exists()


def test_cli_runs_from_subdirectory(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, {"blip": BLIP})
    sub = tmp_path / "sounds"
    monkeypatch.chdir(sub)

    cli.main(["list"])

    assert capsys.readouterr().out.strip() == "sounds: blip"


def test_cli_project_flag_points_at_another_dir(tmp_path, monkeypatch, capsys):
    project = tmp_path / "game"
    project.mkdir()
    make_project(project, {"blip": BLIP})
    monkeypatch.chdir(tmp_path)

    cli.main(["list", "-C", str(project)])

    assert capsys.readouterr().out.strip() == "sounds: blip"


def test_cli_unknown_sound_has_friendly_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"blip": BLIP})

    with pytest.raises(SystemExit, match="unknown sound 'missing'. Available sounds: blip"):
        cli.main(["build", "missing"])


def test_cli_renders_buffer_sound(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"blip": BLIP})

    cli.main(["build", "blip"])

    assert (tmp_path / "output" / "blip.wav").is_file()
    assert "blip" in capsys.readouterr().out


def test_cli_rejects_invalid_sound_return(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {
            "bad": """
from shipwright import sound

@sound("bad")
def bad():
    return object()
"""
        },
    )

    with pytest.raises(SystemExit, match="expected Buffer or RenderSpec"):
        cli.main(["build", "bad"])


def test_cli_routes_render_spec_without_real_dawdreamer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {
            "song": """
from shipwright import sound, RenderSpec

@sound("song")
def song():
    return RenderSpec(tracks=[])
"""
        },
    )

    def fake_render_spec(spec):
        return np.zeros((16, 2), dtype=np.float32)

    import shipwright.engine

    monkeypatch.setattr(shipwright.engine, "render_spec", fake_render_spec)

    cli.main(["build", "song"])

    assert (tmp_path / "output" / "song.wav").is_file()


def test_cli_out_duration_and_extra_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {
            "blip": """
from shipwright import sound, Buffer
import numpy as np

@sound("blip")
def blip():
    return Buffer(np.ones((100, 2), dtype=np.float32) * 0.1)
"""
        },
    )
    out = tmp_path / "custom.wav"

    cli.main(["build", "blip", "--out", str(out), "--duration", "0.001", "--flac"])

    audio, sr = sf.read(out)
    assert out.is_file()
    assert out.with_suffix(".flac").is_file()
    assert len(audio) == round(sr * 0.001)


NOISE = """
from shipwright import sound, Buffer, dsp

@sound("{name}")
def build():
    return Buffer(dsp.to_stereo(dsp.noise(0.01, amp=0.2)))
"""


def test_cli_seed_reaches_dsp_noise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"noise": NOISE.format(name="noise")})

    cli.main(["build", "noise", "--seed", "7"])
    first, _ = sf.read(tmp_path / "output" / "noise.wav")
    clear()
    cli.main(["build", "noise", "--seed", "7"])
    second, _ = sf.read(tmp_path / "output" / "noise.wav")

    np.testing.assert_array_equal(first, second)


def test_cli_seed_is_deterministic_when_rendering_all_in_parallel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {name: NOISE.format(name=name) for name in ["a", "b"]},
    )

    cli.main(["build", "all", "--seed", "99", "--jobs", "2"])
    first_a, _ = sf.read(tmp_path / "output" / "a.wav")
    first_b, _ = sf.read(tmp_path / "output" / "b.wav")
    clear()
    cli.main(["build", "all", "--seed", "99", "--jobs", "2"])
    second_a, _ = sf.read(tmp_path / "output" / "a.wav")
    second_b, _ = sf.read(tmp_path / "output" / "b.wav")

    np.testing.assert_array_equal(first_a, second_a)
    np.testing.assert_array_equal(first_b, second_b)


def test_cli_init_creates_minimal_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.main(["init", "game_audio"])

    root = tmp_path / "game_audio"
    assert (root / "shipwright.toml").is_file()
    assert (root / ".gitignore").is_file()
    assert (root / "sounds" / "starter_blip.py").is_file()
    assert len(list((root / "sounds").glob("*.py"))) == 1
    assert (root / "output" / ".gitkeep").is_file()
    # lean template: no scaffolded instruments/ or soundfonts/
    assert not (root / "instruments").exists()
    assert not (root / "soundfonts").exists()
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

    cli.main(["build", "starter_blip"])

    assert (root / "output" / "starter_blip.wav").is_file()


TONE = """
from shipwright import sound, Buffer
import numpy as np

@sound("{name}")
def make():
    return Buffer(np.ones((100, 2), dtype=np.float32) * 0.1)
"""


def test_cli_build_without_targets_renders_all_sounds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {n: TONE.format(name=n) for n in ("a", "b")})

    cli.main(["build"])

    assert (tmp_path / "output" / "a.wav").is_file()
    assert (tmp_path / "output" / "b.wav").is_file()


def test_cli_build_targets_come_from_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {n: TONE.format(name=n) for n in ("a", "b")},
        toml='[shipwright]\n\n[build]\ntargets = ["a"]\n',
    )

    cli.main(["build"])

    assert (tmp_path / "output" / "a.wav").is_file()
    assert not (tmp_path / "output" / "b.wav").exists()


def test_cli_build_per_target_format_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {"blip": TONE.format(name="blip")},
        toml='[shipwright]\n\n[build]\nformats = ["wav"]\n\n[build.blip]\nformats = ["wav", "flac"]\n',
    )

    cli.main(["build"])

    assert (tmp_path / "output" / "blip.wav").is_file()
    assert (tmp_path / "output" / "blip.flac").is_file()


def test_cli_build_toml_duration_applies_and_cli_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {"blip": TONE.format(name="blip")},
        toml="[shipwright]\n\n[build.blip]\nduration = 0.001\n",
    )

    cli.main(["build", "blip"])
    audio, sr = sf.read(tmp_path / "output" / "blip.wav")
    assert len(audio) == round(sr * 0.001)

    cli.main(["build", "blip", "--duration", "0.002"])
    audio, sr = sf.read(tmp_path / "output" / "blip.wav")
    assert len(audio) == round(sr * 0.002)


def test_cli_build_skips_failing_format_but_keeps_wav(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {"blip": TONE.format(name="blip")},
        toml='[shipwright]\n\n[build.blip]\nformats = ["wav", "mp3"]\n',
    )

    import shipwright.engine

    real_write = shipwright.engine.write_audio

    def flaky_write(path, audio, sr, *, format=None, **kw):
        if format == "MP3":
            raise RuntimeError("no mp3 support")
        return real_write(path, audio, sr, format=format, **kw)

    monkeypatch.setattr(shipwright.engine, "write_audio", flaky_write)

    cli.main(["build", "blip"])

    assert (tmp_path / "output" / "blip.wav").is_file()
    assert not (tmp_path / "output" / "blip.mp3").exists()
    assert "skipped mp3" in capsys.readouterr().out
