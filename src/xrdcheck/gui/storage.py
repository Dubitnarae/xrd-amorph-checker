"""사용자 설정 저장소(%APPDATA%\\xrdcheck). 기본값은 패키지 안의 data/ 파일을 쓰고, 바꾼 값만 여기에 둔다."""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path

from xrdcheck.analysis.phases import load_library
from xrdcheck.settings import load_settings


def default_config_dir() -> Path:
    if env := os.environ.get("XRDCHECK_CONFIG_DIR"):
        return Path(env)
    return Path(os.environ.get("APPDATA", Path.home())) / "xrdcheck"


class UserStore:
    def __init__(self, directory: str | Path | None = None):
        self.dir = Path(directory) if directory else default_config_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.dir / "settings.json"
        self.phases_path = self.dir / "phases.json"
        self.gui_ini = self.dir / "gui.ini"

    def overrides(self) -> dict:
        if self.settings_path.exists():
            try:
                return json.loads(self.settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass  # 깨진 사용자 설정은 무시하고 기본값
        return {}

    def load_settings(self) -> dict:
        return load_settings(overrides=self.overrides())

    def save_settings(self, overrides: dict) -> None:
        self.settings_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    def library_text(self) -> str:
        if self.phases_path.exists():
            return self.phases_path.read_text(encoding="utf-8")
        return default_library_text()

    def load_library(self) -> list[dict]:
        if self.phases_path.exists():
            try:
                return load_library(self.phases_path)
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        return load_library()

    def save_library_text(self, text: str) -> None:
        if text.strip() == default_library_text().strip():
            self.phases_path.unlink(missing_ok=True)  # 기본값과 같으면 사용자 사본을 두지 않음
        else:
            self.phases_path.write_text(text, encoding="utf-8")


def default_library_text() -> str:
    return resources.files("xrdcheck").joinpath("data/phases.json").read_text(encoding="utf-8")


def validate_library_text(text: str) -> str | None:
    """상 라이브러리 JSON 검사. 문제가 없으면 None, 있으면 한국어 설명."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return f"JSON 문법 오류: {e.msg} ({e.lineno}행 {e.colno}열)"
    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, list) or not phases:
        return "'phases' 목록이 없습니다."
    for i, ph in enumerate(phases, 1):
        if not isinstance(ph, dict) or not ph.get("name"):
            return f"{i}번째 상에 'name'이 없습니다."
        lines = ph.get("lines")
        if not isinstance(lines, list) or not lines:
            return f"'{ph['name']}'에 'lines'가 없습니다."
        for ln in lines:
            try:
                if float(ln["d_A"]) <= 0 or float(ln["rel"]) <= 0 or not str(ln["hkl"]):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                return f"'{ph['name']}'의 선 {ln}에 hkl·d_A(>0)·rel(>0)이 필요합니다."
    return None
