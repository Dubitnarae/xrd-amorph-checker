"""Phase 0: 패키지 뼈대 확인."""

import json
from importlib import resources

import xrdcheck


def test_version_matches_pyproject():
    """버전은 __init__.py와 pyproject.toml 두 곳 — 둘이 같아야 한다(build.ps1도 확인)."""
    import re
    from pathlib import Path

    toml = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "(.+)"', toml, re.M).group(1) == xrdcheck.__version__


def test_icon_is_packaged():
    assert resources.files("xrdcheck").joinpath("data/icon.ico").is_file()


def test_default_settings_is_valid_json():
    text = resources.files("xrdcheck").joinpath("data/default_settings.json").read_text(encoding="utf-8")
    assert isinstance(json.loads(text), dict)


def test_author():
    assert xrdcheck.__author__ == "KIM YEONGDO"
