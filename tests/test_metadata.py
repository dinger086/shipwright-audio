import re
from pathlib import Path

import shipwright


def test_package_version_matches_project_metadata():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    assert shipwright.__version__ == match.group(1)
