from shipwright import config


def test_project_config_loads_shipwright_table(tmp_path):
    (tmp_path / "shipwright.toml").write_text(
        """
[shipwright]
sr = 48000
master_ceiling = 0.9
target_lufs = -18
sounds_dir = "audio"
""".lstrip(),
        encoding="utf-8",
    )

    loaded = config._load_project_config(tmp_path)

    assert loaded["sr"] == 48000
    assert loaded["master_ceiling"] == 0.9
    assert loaded["target_lufs"] == -18
    assert loaded["sounds_dir"] == "audio"


def test_configure_exposes_build_table(tmp_path):
    (tmp_path / "shipwright.toml").write_text(
        """
[shipwright]
sr = 44100

[build]
targets = ["a", "b"]
formats = ["wav", "flac"]

[build.a]
formats = ["wav"]
lufs = -16
""".lstrip(),
        encoding="utf-8",
    )

    config.configure(start=tmp_path)

    assert config.BUILD["targets"] == ["a", "b"]
    assert config.BUILD["formats"] == ["wav", "flac"]
    assert config.BUILD["a"] == {"formats": ["wav"], "lufs": -16}


def test_simple_toml_fallback_parses_build_arrays_and_subtables(tmp_path):
    path = tmp_path / "shipwright.toml"
    path.write_text(
        """
[shipwright]
sr = 48000

[build]
targets = ["a", "b"]
formats = ["wav", "flac"]

[build.a]
formats = ["wav"]
lufs = -16
""".lstrip(),
        encoding="utf-8",
    )

    data = config._load_simple_toml(path)

    assert data["shipwright"]["sr"] == 48000
    assert data["build"]["targets"] == ["a", "b"]
    assert data["build"]["formats"] == ["wav", "flac"]
    assert data["build"]["a"] == {"formats": ["wav"], "lufs": -16}
