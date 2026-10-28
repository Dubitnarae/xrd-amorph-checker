"""상 라이브러리와 협폭 피크 매칭."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from xrdcheck.analysis.profiles import two_theta_from_d
from xrdcheck.model import Peak


def load_library(path: str | Path | None = None) -> list[dict]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("xrdcheck").joinpath("data/phases.json").read_text(encoding="utf-8")
    return json.loads(text)["phases"]


def phase_lines(library: list[dict], wavelength_A: float, x_min: float, x_max: float) -> list[dict]:
    """라이브러리의 d값을 파일 파장으로 2θ로 바꾸고, 스캔 범위 안의 선만 돌려준다."""
    out = []
    for ph in library:
        for ln in ph["lines"]:
            tt = two_theta_from_d(ln["d_A"], wavelength_A)
            if tt is not None and x_min <= tt <= x_max:
                out.append({"label": f"{ph['name']}({ln['hkl']})", "phase": ph["name"], "hkl": ln["hkl"],
                            "two_theta": tt, "rel": ln["rel"]})
    return out


def match_peaks(peaks: list[Peak], lines: list[dict], settings: dict, min_height) -> None:
    """±허용오차 안의 선과 매칭한다. 매칭된 상의 다른 선이 검출한계보다 커야 하는데 안 보이면 신뢰도를 낮춘다.

    min_height(2θ, z기준) → 그 위치의 검출한계(counts) 또는 None.
    """
    tol = settings["phase_match"]["tolerance_deg"]
    counted = [p for p in peaks if p.counted]
    hit: dict[str, list[tuple[Peak, dict]]] = {}
    for p in counted:
        for ln in lines:
            if abs(ln["two_theta"] - p.two_theta) <= tol:
                p.matches.append(ln["label"])
                hit.setdefault(ln["phase"], []).append((p, ln))

    for phase, pairs in hit.items():
        ref_peak, ref_line = max(pairs, key=lambda pl: pl[0].height)
        found = {ln["label"] for _, ln in pairs}
        missing = []
        for ln in lines:
            if ln["phase"] != phase or ln["label"] in found:
                continue
            expected = ref_peak.height * ln["rel"] / ref_line["rel"]
            dl = min_height(ln["two_theta"], settings["z_detect"])
            if dl is not None and expected > dl:
                missing.append(f"{ln['label']} 미검출(예상 약 {expected:.0f} counts > 검출한계 {dl:.0f})")
        for p, _ in pairs:
            if missing:
                p.notes.extend(m for m in missing if m not in p.notes)
            conf = "낮음" if missing else "높음"
            if p.match_confidence != "높음":  # 여러 상에 매칭되면 하나라도 높으면 높음
                p.match_confidence = conf
