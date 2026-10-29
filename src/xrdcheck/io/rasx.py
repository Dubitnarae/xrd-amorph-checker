"""Rigaku SmartLab Studio .rasx 파서.

.rasx는 zip 묶음이다.
- Data0/Profile0.txt: 2θ, 강도, 감쇠 계수(탭 구분, 3열). 강도 × 감쇠 계수 = counts
- Data0/MesurementConditions0.xml(철자 그대로): 파장, 스캔 조건(시작·끝·간격·속도), 강도 단위, 측정 시각
여러 측정(Data1 …)이 들어 있으면 첫 번째만 쓴다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np

from xrdcheck.model import CU_KALPHA1_A, CU_KALPHA2_A, CU_KALPHA2_RATIO, Pattern

_DATA_DIR = re.compile(r"^Data(\d+)/", re.I)


class RasxError(ValueError):
    pass


def _text(root, tag: str) -> str:
    node = root.find(f".//{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def _float(root, tag: str) -> float | None:
    try:
        return float(_text(root, tag))
    except ValueError:
        return None


def _member(names: list[str], data_dir: str, prefix: str) -> str | None:
    for n in names:
        if n.lower().startswith(f"{data_dir}/{prefix}".lower()):
            return n
    return None


def read_rasx(path: str | Path) -> Pattern:
    path = Path(path)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise RasxError(f".rasx 파일이 zip 형식이 아닙니다: {path.name}") from e
    warnings: list[str] = []
    with zf:
        names = zf.namelist()
        dirs = sorted({int(m[1]) for n in names if (m := _DATA_DIR.match(n))})
        if not dirs:
            raise RasxError(f"측정 데이터(Data0/)가 없습니다: {path.name}")
        if len(dirs) > 1:
            warnings.append(f"측정이 {len(dirs)}개 들어 있습니다 — 첫 번째(Data{dirs[0]})만 사용합니다.")
        d = f"Data{dirs[0]}"
        prof = _member(names, d, "Profile")
        cond = _member(names, d, "MesurementConditions") or _member(names, d, "MeasurementConditions")
        if prof is None:
            raise RasxError(f"{d}/Profile 데이터가 없습니다: {path.name}")
        rows = []
        for line in zf.read(prof).decode("utf-8-sig", errors="replace").splitlines():
            parts = line.split()
            try:
                vals = [float(v) for v in parts[:3]]
            except ValueError:
                continue
            if len(vals) >= 2:
                rows.append(vals[:2] + [vals[2] if len(vals) > 2 else 1.0])
        if len(rows) < 10:
            raise RasxError(f"데이터 점이 {len(rows)}개뿐입니다: {path.name}")
        root = ET.fromstring(zf.read(cond).decode("utf-8-sig", errors="replace")) if cond else None

    data = np.array(rows)
    x, y = data[:, 0], data[:, 1] * data[:, 2]  # 감쇠기를 쓴 구간은 계수를 곱해야 실제 세기
    if np.any(data[:, 2] != 1):
        warnings.append("감쇠기가 쓰인 구간이 있어 감쇠 계수를 곱했습니다 — 그 구간의 통계 가중치는 근사입니다.")

    meta: dict = {"intensity_unit": "counts", "data_member": prof}
    ka1, ka2, counting_time, stamp = None, None, None, ""
    if root is not None:
        ka1 = _float(root, "WavelengthKalpha1")
        ka2 = _float(root, "WavelengthKalpha2")
        unit = _text(root, "ScanInformation/IntensityUnit") or "counts"
        step, speed = _float(root, "ScanInformation/Step"), _float(root, "ScanInformation/Speed")
        speed_unit = _text(root, "ScanInformation/SpeedUnit")
        if step and speed and "min" in speed_unit.lower():
            counting_time = step / speed * 60  # 연속 스캔: 한 점당 머문 시간(s)
        elif step and speed and speed_unit.lower().startswith("s"):
            counting_time = speed  # 스텝 스캔: 점당 계수 시간
        stamp = _text(root, "ScanInformation/StartTime")
        meta.update({
            "intensity_unit": unit,
            "sample_id": _text(root, "GeneralInformation/SampleName"),
            "operator": _text(root, "GeneralInformation/Operator"),
            "system": _text(root, "GeneralInformation/SystemName"),
            "scan_mode": _text(root, "ScanInformation/Mode"),
            "scan_axis": _text(root, "ScanInformation/AxisName"),
            "start_timestamp": stamp,
            "end_timestamp": _text(root, "ScanInformation/EndTime"),
            "speed": f"{speed:g} {speed_unit}" if speed else "",
            "anode": _text(root, "TargetName"),
            "tube_kV": _float(root, "Voltage"),
            "tube_mA": _float(root, "Current"),
            "comments": [c for c in (_text(root, "GeneralInformation/Comment"), _text(root, "GeneralInformation/Memo")) if c],
        })
        if unit.lower() in ("cps", "counts/s", "count/s"):
            if counting_time:
                y = y * counting_time
                warnings.append(f"강도 단위가 cps라서 점당 시간 {counting_time:g} s를 곱해 counts로 환산했습니다.")
            else:
                warnings.append("강도 단위가 cps인데 점당 시간을 알 수 없어 counts로 환산하지 못했습니다.")
    else:
        warnings.append("측정 조건(XML)이 없어 Cu Kα, 강도 단위 counts로 가정했습니다.")
    if ka1 is None:
        ka1 = CU_KALPHA1_A
        if root is not None:
            warnings.append("파장 정보가 없어 Cu Kα1(1.540598 Å)로 가정했습니다.")

    p = Pattern(
        two_theta=x,
        counts=y,
        source_path=path,
        file_format="rasx",
        sample_name=path.stem,  # 내부 SampleName은 "1"처럼 짧은 번호인 경우가 많아 파일명을 쓴다(meta의 sample_id)
        kalpha1_A=ka1,
        kalpha2_A=ka2 if ka2 else (CU_KALPHA2_A if abs(ka1 - CU_KALPHA1_A) < 1e-3 else None),
        kalpha2_ratio=CU_KALPHA2_RATIO if (ka2 or abs(ka1 - CU_KALPHA1_A) < 1e-3) else None,
        counting_time_s=counting_time,
        file_timestamp_raw=stamp,
        meta=meta,
    )
    if np.any(np.diff(p.two_theta) <= 0):
        order = np.argsort(p.two_theta, kind="stable")
        p.two_theta, p.counts = p.two_theta[order], p.counts[order]
        p.warn("2θ가 오름차순이 아니어서 정렬했습니다.")
    for w in warnings:
        p.warn(w)
    return p
