"""설정값(판정 기준) 읽기. 기본값은 data/default_settings.json, 사용자 파일은 그 위에 덮어쓴다."""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def default_settings() -> dict:
    text = resources.files("xrdcheck").joinpath("data/default_settings.json").read_text(encoding="utf-8")
    return json.loads(text)


def load_settings(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    s = default_settings()
    if path:
        s = _merge(s, json.loads(Path(path).read_text(encoding="utf-8")))
    if overrides:
        s = _merge(s, overrides)
    return s


def flatten(d: dict, prefix: str = "") -> list[tuple[str, object]]:
    """보고서용: 중첩 설정을 'a.b = 값' 목록으로 편다."""
    rows = []
    for k, v in d.items():
        if k.startswith("_"):
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            rows += flatten(v, key + ".")
        else:
            rows.append((key, v))
    return rows
