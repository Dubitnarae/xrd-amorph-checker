"""HighScore RTF 보고서에서 메타 정보(원본 경로, Dataset Name)만 읽는다. 수치 데이터는 없다."""

from __future__ import annotations

import re
from pathlib import Path

_HEX = re.compile(r"\\'([0-9a-fA-F]{2})")


def _unescape(s: str) -> str:
    s = _HEX.sub(lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", errors="replace"), s)
    return s.replace("\\\\", "\\").replace("\\{", "{").replace("\\}", "}").strip()


def _field(text: str, label: str) -> str:
    # 예: "File name:\tab C:\\X'Pert Data\\2026\\...\\SMP-01a.xrdml\par"
    m = re.search(re.escape(label) + r":\s*\\tab\s*(.*?)\\par", text)
    return _unescape(m.group(1)) if m else ""


def read_rtf_meta(path: str | Path) -> dict:
    text = Path(path).read_bytes().decode("cp1252", errors="replace")
    meta = {}
    original = _field(text, "File name")
    if original:
        meta["original_path"] = original
    name = _field(text, "Dataset Name")
    if name:
        meta["dataset_name"] = name
    return meta
