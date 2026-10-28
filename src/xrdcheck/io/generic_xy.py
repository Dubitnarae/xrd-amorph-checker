"""일반 2열 텍스트(.xy/.txt/.dat) 파서 — 다른 기관 데이터 대비."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from xrdcheck.model import Pattern

_SPLIT = re.compile(r"[\s,;]+")
MIN_POINTS = 10


class GenericXyError(ValueError):
    pass


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_generic_xy(path: str | Path) -> Pattern:
    """숫자 두 개 이상으로 시작하는 줄만 데이터로 읽고, 나머지(머리말·주석)는 건너뛴다."""
    path = Path(path)
    rows = []
    for line in _read_text(path).splitlines():
        s = line.strip()
        if not s or s[0] in "#;!'\"":
            continue
        parts = _SPLIT.split(s)
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue
    if len(rows) < MIN_POINTS:
        raise GenericXyError(f"2열 숫자 데이터가 {len(rows)}줄뿐입니다(최소 {MIN_POINTS}줄): {path.name}")

    data = np.array(rows)
    p = Pattern(
        two_theta=data[:, 0],
        counts=data[:, 1],
        source_path=path,
        file_format="generic_xy",
        sample_name=path.stem,
    )
    if np.any(np.diff(p.two_theta) <= 0):
        order = np.argsort(p.two_theta, kind="stable")
        p.two_theta, p.counts = p.two_theta[order], p.counts[order]
        p.warn("2θ가 오름차순이 아니어서 정렬했습니다.")
    p.warn("2열 텍스트에는 파장·단위 정보가 없어 Cu Kα, 강도 단위 counts로 가정했습니다.")
    if np.any(np.abs(p.counts - np.round(p.counts)) > 1e-6):
        p.warn("강도에 소수가 있습니다 — counts가 아닐 수 있어(cps 등) 통계 판정이 부정확할 수 있습니다.")
    return p
