"""상 라이브러리와 협폭 피크 매칭.

상 정의 두 가지:
- 고정 d값: "lines": [{"hkl", "d_A", "rel"}]
- 입방정 격자상수 범위: "cubic_a_range_A": [최소, 최대], "lines": [{"hkl", "rel"}]
  (예: α-Fe(Si)는 Si 함량에 따라 a가 바뀌어 피크 위치가 움직인다)
"role": "contaminant"인 상(석영 등)에 매칭된 피크는 판정에서 빼고 경고만 남긴다.
"""

from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path

from xrdcheck.analysis.profiles import d_spacing, two_theta_from_d
from xrdcheck.model import Peak


def load_library(path: str | Path | None = None) -> list[dict]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("xrdcheck").joinpath("data/phases.json").read_text(encoding="utf-8")
    return json.loads(text)["phases"]


def _hkl_n(hkl: str) -> int:
    """'110' → h²+k²+l² (한 자리 지수 기준)."""
    return sum(int(c) ** 2 for c in hkl)


def phase_lines(library: list[dict], wavelength_A: float, x_min: float, x_max: float) -> list[dict]:
    """라이브러리를 파일 파장으로 2θ로 바꾸고, 스캔 범위에 걸치는 선만 돌려준다.
    범위 상은 two_theta_min–two_theta_max 구간을 갖는다(고정 d값이면 같은 값)."""
    out = []
    for ph in library:
        a_range = ph.get("cubic_a_range_A")
        for ln in ph["lines"]:
            if a_range:
                n = _hkl_n(ln["hkl"])
                tts = [two_theta_from_d(a / math.sqrt(n), wavelength_A) for a in a_range]
                if None in tts:
                    continue
                lo, hi = min(tts), max(tts)
            else:
                n = None
                tt = two_theta_from_d(ln["d_A"], wavelength_A)
                if tt is None:
                    continue
                lo = hi = tt
            if hi < x_min or lo > x_max:
                continue
            out.append({"label": f"{ph['name']}({ln['hkl']})", "phase": ph["name"], "hkl": ln["hkl"],
                        "two_theta": (lo + hi) / 2, "two_theta_min": lo, "two_theta_max": hi,
                        "rel": ln["rel"], "hkl_n": n, "role": ph.get("role", "")})
    return out


def _predicted_two_theta(ln: dict, ref_peak: Peak, ref_line: dict, wavelength_A: float) -> float:
    """범위 상이면 매칭된 피크에서 격자상수를 역산해 다른 선의 위치를 예측한다."""
    if ln["hkl_n"] and ref_line["hkl_n"]:
        a = d_spacing(ref_peak.two_theta, wavelength_A) * math.sqrt(ref_line["hkl_n"])
        tt = two_theta_from_d(a / math.sqrt(ln["hkl_n"]), wavelength_A)
        if tt is not None:
            return tt
    return ln["two_theta"]


def match_peaks(peaks: list[Peak], lines: list[dict], settings: dict, min_height,
                wavelength_A: float = 1.540598) -> None:
    """허용오차 안의 선과 매칭하고 신뢰도를 매긴다.

    - 높음: 그 상의 다른 선이 모두 검출한계 아래로 예상되거나 실제로 보임
    - 보통: 더 약한 선 일부가 보여야 하는데 안 보임(매칭은 인정)
    - 낮음: 더 강한(또는 같은 세기의) 선이 보여야 하는데 안 보임 → 판정에서 매칭으로 인정하지 않음
    min_height(2θ, z기준) → 그 위치의 검출한계(counts) 또는 None.
    """
    tol = settings["phase_match"]["tolerance_deg"]
    counted = [p for p in peaks if p.counted]
    hit: dict[str, list[tuple[Peak, dict]]] = {}
    for p in counted:
        for ln in lines:
            if ln["two_theta_min"] - tol <= p.two_theta <= ln["two_theta_max"] + tol:
                p.matches.append(ln["label"])
                hit.setdefault(ln["phase"], []).append((p, ln))
    by_label = {ln["label"]: ln for ln in lines}
    for p in counted:  # 오염 상에만 매칭된 피크는 판정에서 뺀다
        if p.matches and all(by_label[m]["role"] == "contaminant" for m in p.matches):
            p.contaminant = True

    rank = {"": 0, "낮음": 1, "보통": 2, "높음": 3}
    for phase, pairs in hit.items():
        ref_peak, ref_line = max(pairs, key=lambda pl: pl[0].height)
        found = {ln["label"] for _, ln in pairs}
        missing, stronger_missing = [], False
        for ln in lines:
            if ln["phase"] != phase or ln["label"] in found:
                continue
            expected = ref_peak.height * ln["rel"] / ref_line["rel"]
            tt = _predicted_two_theta(ln, ref_peak, ref_line, wavelength_A)
            dl = min_height(tt, settings["z_detect"])
            if dl is not None and expected > dl:
                missing.append(f"{ln['label']} {tt:.2f}° 미검출(예상 약 {expected:.0f} counts > 검출한계 {dl:.0f})")
                stronger_missing |= ln["rel"] >= ref_line["rel"]
        conf = "낮음" if stronger_missing else ("보통" if missing else "높음")
        for p, _ in pairs:
            p.notes.extend(m for m in missing if m not in p.notes)
            if rank[conf] > rank[p.match_confidence]:  # 여러 상에 매칭되면 가장 높은 신뢰도
                p.match_confidence = conf
