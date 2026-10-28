"""X'Pert CSV 내보내기 파서 (`[Measurement conditions]` + `[Scan points]`)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xrdcheck.model import CU_KALPHA1_A, Pattern


class XpertCsvError(ValueError):
    pass


def is_xpert_csv(text: str) -> bool:
    head = text[:4000]
    return "[Measurement conditions]" in head or "[Scan points]" in text


def _num(meta: dict, key: str) -> float | None:
    try:
        return float(meta[key])
    except (KeyError, ValueError):
        return None


def read_xpert_csv(path: str | Path) -> Pattern:
    path = Path(path)
    text = path.read_text(encoding="cp1252", errors="replace")
    if not is_xpert_csv(text):
        raise XpertCsvError(f"X'Pert CSV 형식이 아닙니다: {path.name}")
    lines = text.splitlines()

    meta: dict[str, str] = {}
    data_start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.lower().startswith("angle,"):  # [Scan points] 아래 열 이름 줄
            data_start = i + 1
            meta["_columns"] = s
            break
        if s.startswith("[") or "," not in s:
            continue
        key, _, val = s.partition(",")
        meta[key.strip()] = val.strip().strip('"').strip()
    if data_start is None:
        raise XpertCsvError(f"데이터 시작 줄(Angle,Intensity)을 찾지 못했습니다: {path.name}")

    rows = []
    for line in lines[data_start:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    if not rows:
        raise XpertCsvError(f"측정 데이터가 없습니다: {path.name}")
    data = np.array(rows)

    p = Pattern(
        two_theta=data[:, 0],
        counts=data[:, 1],
        source_path=path,
        file_format="xpert_csv",
        sample_name=meta.get("Sample identification", "") or path.stem,
        kalpha1_A=_num(meta, "K-Alpha1 wavelength") or CU_KALPHA1_A,
        kalpha2_A=_num(meta, "K-Alpha2 wavelength"),
        kalpha2_ratio=_num(meta, "Ratio K-Alpha2/K-Alpha1"),
        counting_time_s=_num(meta, "Time per step"),
        file_timestamp_raw=meta.get("File date and time", ""),
        meta=meta,
    )
    if "K-Alpha1 wavelength" not in meta:
        p.warn("파장 정보가 없어 Cu Kα1(1.540598 Å)로 가정했습니다.")
    n_declared = _num(meta, "No. of points")
    if n_declared is not None and int(n_declared) != p.n_points:
        p.warn(f"헤더의 점 개수({int(n_declared)})와 실제 데이터 개수({p.n_points})가 다릅니다.")
    return p
