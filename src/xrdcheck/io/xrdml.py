"""PANalytical XRDML 파서."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from xrdcheck.model import CU_KALPHA1_A, Pattern


class XrdmlError(ValueError):
    pass


def _float(node) -> float | None:
    if node is None or node.text is None or not node.text.strip():
        return None
    return float(node.text)


def read_xrdml(path: str | Path) -> Pattern:
    path = Path(path)
    root = ET.parse(path).getroot()
    if not root.tag.startswith("{"):
        raise XrdmlError(f"XRDML 네임스페이스가 없습니다: {path.name}")
    # 스키마 버전(1.x, 2.x)과 상관없이 루트의 네임스페이스를 그대로 쓴다
    ns = {"x": root.tag[1:].split("}")[0]}
    warnings: list[str] = []

    scans = root.findall(".//x:scan", ns)
    if not scans:
        raise XrdmlError(f"<scan>이 없습니다: {path.name}")
    if len(scans) > 1:
        warnings.append(f"scan이 {len(scans)}개 있습니다 — 첫 번째 scan만 사용합니다.")
    dp = scans[0].find("x:dataPoints", ns)
    if dp is None:
        raise XrdmlError(f"<dataPoints>가 없습니다: {path.name}")

    node = dp.find("x:intensities", ns)
    if node is None:  # 일부 버전은 <counts>
        node = dp.find("x:counts", ns)
    if node is None or not (node.text or "").strip():
        raise XrdmlError(f"강도 데이터(<intensities>/<counts>)가 없습니다: {path.name}")
    y = np.array(node.text.split(), dtype=float)
    unit = (node.get("unit") or "counts").strip()

    counting_time = _float(dp.find("x:commonCountingTime", ns))
    if "per second" in unit.lower() or unit.lower() == "cps":
        if counting_time:
            y = y * counting_time
            warnings.append(f"강도 단위가 cps라서 계수시간 {counting_time:g} s를 곱해 counts로 환산했습니다.")
        else:
            warnings.append("강도 단위가 cps인데 계수시간이 없어 counts로 환산하지 못했습니다 — 통계 가중치가 부정확합니다.")

    pos = next((p for p in dp.findall("x:positions", ns) if p.get("axis") == "2Theta"), None)
    if pos is None:
        raise XrdmlError(f"2Theta 위치 정보가 없습니다: {path.name}")
    lp = pos.find("x:listPositions", ns)
    if lp is not None and (lp.text or "").strip():
        x = np.array(lp.text.split(), dtype=float)
        if len(x) != len(y):
            raise XrdmlError(f"위치 개수({len(x)})와 강도 개수({len(y)})가 다릅니다: {path.name}")
    else:
        x0 = _float(pos.find("x:startPosition", ns))
        x1 = _float(pos.find("x:endPosition", ns))
        if x0 is None or x1 is None:
            raise XrdmlError(f"2Theta 시작/끝 위치가 없습니다: {path.name}")
        x = np.linspace(x0, x1, len(y))  # 등간격으로 펼침

    wl = root.find(".//x:usedWavelength", ns)
    ka1 = _float(wl.find("x:kAlpha1", ns)) if wl is not None else None
    ka2 = _float(wl.find("x:kAlpha2", ns)) if wl is not None else None
    ratio = _float(wl.find("x:ratioKAlpha2KAlpha1", ns)) if wl is not None else None
    if ka1 is None:
        ka1 = CU_KALPHA1_A
        warnings.append("파장 정보가 없어 Cu Kα1(1.540598 Å)로 가정했습니다.")

    sample_name = (root.findtext(".//x:sample/x:name", default="", namespaces=ns) or "").strip()
    scan = scans[0]
    meta = {
        "namespace": ns["x"],
        "n_scans": len(scans),
        "intensity_unit": unit,
        "sample_id": (root.findtext(".//x:sample/x:id", default="", namespaces=ns) or "").strip(),
        "scan_mode": scan.get("mode", ""),
        "scan_axis": scan.get("scanAxis", ""),
        "start_timestamp": scan.findtext(".//x:startTimeStamp", default="", namespaces=ns),
        "end_timestamp": scan.findtext(".//x:endTimeStamp", default="", namespaces=ns),
        "tube_kV": _float(root.find(".//x:xRayTube/x:tension", ns)),
        "tube_mA": _float(root.find(".//x:xRayTube/x:current", ns)),
        "anode": root.findtext(".//x:xRayTube/x:anodeMaterial", default="", namespaces=ns),
        "detector": (root.find(".//x:detector", ns).get("name", "") if root.find(".//x:detector", ns) is not None else ""),
        "comments": [e.text for e in root.findall("./x:comment/x:entry", ns) if e.text],
    }

    p = Pattern(
        two_theta=x,
        counts=y,
        source_path=path,
        file_format="xrdml",
        sample_name=sample_name or path.stem,
        kalpha1_A=ka1,
        kalpha2_A=ka2,
        kalpha2_ratio=ratio,
        counting_time_s=counting_time,
        file_timestamp_raw=meta["start_timestamp"],
        meta=meta,
    )
    for w in warnings:
        p.warn(w)
    return p
