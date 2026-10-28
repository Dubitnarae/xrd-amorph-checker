"""Phase 0: 패키지 뼈대 확인."""

import json
from importlib import resources

import xrdcheck


def test_version():
    assert xrdcheck.__version__ == "0.1.0"


def test_default_settings_is_valid_json():
    text = resources.files("xrdcheck").joinpath("data/default_settings.json").read_text(encoding="utf-8")
    assert isinstance(json.loads(text), dict)
