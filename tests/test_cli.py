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

    cli.main([])

    assert capsys.readouterr().out.strip() == "sounds: blip"
    assert not (tmp_path / "output").exists()


def test_cli_runs_from_subdirectory(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, {"blip": BLIP})
    sub = tmp_path / "sounds"
    monkeypatch.chdir(sub)

    cli.main([])

    assert capsys.readouterr().out.strip() == "sounds: blip"


def test_cli_project_flag_points_at_another_dir(tmp_path, monkeypatch, capsys):
    project = tmp_path / "game"
    project.mkdir()
    make_project(project, {"blip": BLIP})
    monkeypatch.chdir(tmp_path)

    cli.main(["-C", str(project)])

    assert capsys.readouterr().out.strip() == "sounds: blip"


def test_cli_unknown_sound_has_friendly_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"blip": BLIP})

    with pytest.raises(SystemExit, match="unknown sound 'missing'. Available sounds: blip"):
        cli.main(["missing"])


def test_cli_renders_buffer_sound(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path, {"blip": BLIP})

    cli.main(["blip"])

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
        cli.main(["bad"])


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

    cli.main(["song"])

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

    cli.main(["blip", "--out", str(out), "--duration", "0.001", "--flac"])

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

    cli.main(["noise", "--seed", "7"])
    first, _ = sf.read(tmp_path / "output" / "noise.wav")
    clear()
    cli.main(["noise", "--seed", "7"])
    second, _ = sf.read(tmp_path / "output" / "noise.wav")

    np.testing.assert_array_equal(first, second)


def test_cli_seed_is_deterministic_when_rendering_all_in_parallel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(
        tmp_path,
        {name: NOISE.format(name=name) for name in ["a", "b"]},
    )

    cli.main(["all", "--seed", "99", "--jobs", "2"])
    first_a, _ = sf.read(tmp_path / "output" / "a.wav")
    first_b, _ = sf.read(tmp_path / "output" / "b.wav")
    clear()
    cli.main(["all", "--seed", "99", "--jobs", "2"])
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

    cli.main(["starter_blip"])

    assert (root / "output" / "starter_blip.wav").is_file()
