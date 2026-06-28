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
