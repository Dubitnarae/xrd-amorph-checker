"""파일 형식 선택(`load_pattern`)과 측정일 결정.

측정일은 파일 내부 타임스탬프를 쓰지 않는다(장비 PC 시계가 2003년으로 틀어져 있음).
파일명 → 폴더 경로 → 사용자 입력 순으로 정하고, 내부 연도가 비정상이면 경고한다.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path, PureWindowsPath

from xrdcheck.io.generic_xy import read_generic_xy
from xrdcheck.io.rtf_meta import read_rtf_meta
from xrdcheck.io.xpert_csv import is_xpert_csv, read_xpert_csv
from xrdcheck.io.xrdml import read_xrdml
from xrdcheck.model import Pattern

SUPPORTED_SUFFIXES = (".xrdml", ".csv", ".xy", ".txt", ".dat")
MIN_PLAUSIBLE_YEAR = 2010  # 이보다 이른 내부 연도는 장비 시계 오류로 본다

_DATE8 = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
_DATE6 = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")
_YEAR_DIR = re.compile(r"^(20\d{2})$")
_MMDD_DIR = re.compile(r"^(\d{2})(\d{2})(?!\d)")
_YEAR_IN_TEXT = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


class UnsupportedFileError(ValueError):
    pass


def _make_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        date = dt.date(y, m, d)
    except ValueError:
        return None
    if not (2000 <= date.year <= dt.date.today().year + 1):
        return None
    return date


def date_from_filename(name: str) -> dt.date | None:
    """파일명에서 YYYYMMDD 또는 YYMMDD(6자리 숫자 덩어리)를 찾는다. 예: SMP-01a-260910-001 → 2026-09-10."""
    stem = Path(name).stem
    for m in _DATE8.finditer(stem):
        if date := _make_date(int(m[1]), int(m[2]), int(m[3])):
            return date
    for m in _DATE6.finditer(stem):
        if date := _make_date(2000 + int(m[1]), int(m[2]), int(m[3])):
            return date
    return None


def date_from_folder(path: str) -> dt.date | None:
    """폴더 경로에서 '연도 폴더(2026) 아래 MMDD로 시작하는 폴더(0911-xrd)'를 찾는다."""
    parts = PureWindowsPath(path).parts[:-1]  # 파일명 제외
    for i, part in enumerate(parts):
        if m := _DATE8.search(part):
            if date := _make_date(int(m[1]), int(m[2]), int(m[3])):
                return date
        if y := _YEAR_DIR.match(part):
            for sub in parts[i + 1:]:
                if md := _MMDD_DIR.match(sub):
                    if date := _make_date(int(y[1]), int(md[1]), int(md[2])):
                        return date
    return None


def year_of_timestamp(raw: str) -> int | None:
    m = _YEAR_IN_TEXT.search(raw or "")
    return int(m[1]) if m else None


def resolve_measurement_date(p: Pattern, user_date: dt.date | None = None) -> None:
    """파일명 → 폴더 경로(RTF의 원본 경로 우선) → 사용자 입력 순으로 측정일을 정한다."""
    candidates: dict[str, dt.date | None] = {"파일명": date_from_filename(p.source_path.name)}
    folder = None
    for path in (p.meta.get("original_path"), str(p.source_path.resolve())):
        if path and (folder := date_from_folder(path)):
            break
    candidates["폴더 경로"] = folder
    candidates["사용자 입력"] = user_date
    p.meta["date_candidates"] = {k: (v.isoformat() if v else None) for k, v in candidates.items()}

    for source, date in candidates.items():
        if date:
            p.measurement_date, p.date_source = date, source
            break
    else:
        p.warn("측정일을 정하지 못했습니다 — 파일명이나 폴더에 날짜가 없습니다. 직접 입력해 주세요.")

    year = year_of_timestamp(p.file_timestamp_raw)
    if year is None:
        return
    resolved = p.measurement_date
    if year < MIN_PLAUSIBLE_YEAR or year > dt.date.today().year + 1 or (resolved and year != resolved.year):
        basis = f" 측정일은 {p.date_source} 기준 {resolved.isoformat()}로 정했습니다." if resolved else ""
        p.warn(f"파일 내부 측정일시의 연도({year})가 비정상입니다 — 장비 PC 시계 오류로 보입니다.{basis}")


def _sibling_rtf(path: Path) -> Path | None:
    for cand in path.parent.glob(path.stem + ".*"):
        if cand.suffix.lower() == ".rtf":
            return cand
    return None


def load_pattern(path: str | Path, *, user_date: dt.date | None = None, read_rtf: bool = True) -> Pattern:
    """확장자와 내용을 보고 알맞은 파서로 읽은 뒤, 같은 이름의 RTF 메타와 측정일을 붙인다."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".rtf":
        raise UnsupportedFileError(f"RTF 보고서에는 수치 데이터가 없습니다. 같은 이름의 .xrdml 또는 .csv를 여세요: {path.name}")
    if suffix == ".xrdml":
        p = read_xrdml(path)
    elif suffix == ".csv":
        head = path.read_text(encoding="cp1252", errors="replace")
        p = read_xpert_csv(path) if is_xpert_csv(head) else read_generic_xy(path)
    elif suffix in SUPPORTED_SUFFIXES:
        p = read_generic_xy(path)
    else:
        raise UnsupportedFileError(f"지원하지 않는 파일 형식입니다({path.suffix}): {path.name}")

    if read_rtf and (rtf := _sibling_rtf(path)):
        rtf_meta = read_rtf_meta(rtf)
        p.meta.update(rtf_meta)
        p.meta["rtf_path"] = str(rtf)

    resolve_measurement_date(p, user_date)
    return p
