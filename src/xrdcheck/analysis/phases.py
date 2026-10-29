"""상 라이브러리와 협폭 피크 매칭.

상 정의 두 가지:
- 고정 d값: "lines": [{"hkl", "d_A", "rel"}]
- 입방정 격자상수 범위: "cubic_a_range_A": [최소, 최대], "lines": [{"hkl", "rel"}]
  (예: α-Fe(Si)는 Si 함량에 따라 a가 바뀌어 피크 위치가 움직인다)
- 고정 d값 + "d_scale_range": [최소, 최대] — 모든 d에 같은 배율(등방 수축·팽창)을 허용(예: 원소 고용된 Fe3B)
"role": "contaminant"인 상(석영 등)에 매칭된 피크는 판정에서 빼고 경고만 남긴다.
"role": "secondary"인 상(붕화물·인화물·fcc 등 α-Fe(Si) 계열이 아닌 2차 상)은 결정상 판정에는 쓰지만,
그 상에만 매칭된 피크는 나노결정(α-Fe(Si)) 판단에서 뺀다. 2차 상은 기본 상으로 설명되지 않은 피크로만 판단한다.
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


def detect_system(halo_center: float, settings: dict) -> str | None:
    """halo 중심으로 합금계 키("Fe", "Al" …)를 고른다. 어느 범위에도 없으면 None."""
    for key, sys_ in settings.get("alloy_systems", {}).items():
        if key.startswith("_"):
            continue
        lo, hi = sys_["halo_center_range_deg"]
        if lo <= halo_center < hi:
            return key
    return None


def phase_lines(library: list[dict], wavelength_A: float, x_min: float, x_max: float,
                system: str | None = None) -> list[dict]:
    """라이브러리를 파일 파장으로 2θ로 바꾸고, 스캔 범위에 걸치는 선만 돌려준다.
    범위 상은 two_theta_min–two_theta_max 구간을 갖는다(고정 d값이면 같은 값).
    system이 주어지면 그 합금계에 해당하는 상만(상에 systems가 없으면 모든 합금계에 해당)."""
    out = []
    for ph in library:
        if system and system not in ph.get("systems", [system]):
            continue
        a_range = ph.get("cubic_a_range_A")
        s_range = ph.get("d_scale_range") or [1.0, 1.0]  # 고정 d값 상의 격자 크기 허용 범위(고용에 따른 수축·팽창)
        for ln in ph["lines"]:
            if a_range:
                n = _hkl_n(ln["hkl"])
                tts = [two_theta_from_d(a / math.sqrt(n), wavelength_A) for a in a_range]
                if None in tts:
                    continue
                lo, hi = min(tts), max(tts)
            else:
                n = None
                tts = [two_theta_from_d(ln["d_A"] * s, wavelength_A) for s in s_range]
                if None in tts:
                    continue
                lo, hi = min(tts), max(tts)
            if hi < x_min or lo > x_max:
                continue
            out.append({"label": f"{ph['name']}({ln['hkl']})", "phase": ph["name"], "hkl": ln["hkl"],
                        "two_theta": (lo + hi) / 2, "two_theta_min": lo, "two_theta_max": hi,
                        "rel": ln["rel"], "hkl_n": n, "role": ph.get("role", ""),
                        "d_A": ln.get("d_A"), "d_scale_range": s_range if ph.get("d_scale_range") else None})
    return out


def _predicted_two_theta(ln: dict, ref_peak: Peak, ref_line: dict, wavelength_A: float) -> float:
    """범위 상이면 매칭된 피크에서 격자상수(또는 d 배율)를 역산해 다른 선의 위치를 예측한다."""
    if ln.get("d_scale_range") and ref_line.get("d_A"):
        lo, hi = ln["d_scale_range"]
        s = min(max(d_spacing(ref_peak.two_theta, wavelength_A) / ref_line["d_A"], lo), hi)
        tt = two_theta_from_d(ln["d_A"] * s, wavelength_A)
        if tt is not None:
            return tt
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
    sig_peaks = [p for p in counted if p.significant]
    role_of = {ln["phase"]: ln["role"] for ln in lines}

    def judge(phase: str, pairs: list[tuple[Peak, dict]]) -> tuple[str, list[str]]:
        ref_peak, ref_line = max(pairs, key=lambda pl: pl[0].height)
        found = {ln["label"] for _, ln in pairs}
        missing, stronger_missing = [], False
        for ln in lines:
            if ln["phase"] != phase or ln["label"] in found:
                continue
            expected = ref_peak.height * ln["rel"] / ref_line["rel"]
            tt = _predicted_two_theta(ln, ref_peak, ref_line, wavelength_A)
            if any(abs(q.two_theta - tt) <= tol and q.height >= 0.5 * expected for q in sig_peaks):
                continue  # 다른 상의 더 큰 피크 밑에 겹쳐 있어 따로 보일 수 없음 → 미검출로 세지 않는다
            dl = min_height(tt, settings["z_detect"])
            if dl is not None and expected > dl:
                missing.append(f"{ln['label']} {tt:.2f}° 미검출(예상 약 {expected:.0f} counts > 검출한계 {dl:.0f})")
                stronger_missing |= ln["rel"] >= ref_line["rel"]
        conf = "낮음" if stronger_missing else ("보통" if missing else "높음")
        if conf == "높음" and role_of[phase] == "secondary":
            # 찾은 선의 세기 비가 계산값과 크게 다르면(3배 초과) 다른 상일 수 있다 → '보통'으로(배향을 생각해 '낮음'까지는 안 내림)
            for pk, ln in pairs:
                expected = ref_peak.height * ln["rel"] / ref_line["rel"]
                if pk is not ref_peak and pk.height > 3 * expected:
                    missing.append(f"{ln['label']} 세기 비가 계산값과 다름(관측 {pk.height:.0f} > 예상 {expected:.0f}의 3배)")
                    conf = "보통"
                    break
        return conf, missing

    # 1단계: 기본 상(α-Fe(Si)·Fe3Si 등). 2단계: 2차 상(붕화물·fcc 등)은 기본 상으로 설명되지 않은 피크만으로 판단한다
    # (45° α-Fe(Si)(110) 피크를 Fe2B(211)로 다시 해석하지 않도록)
    verdicts: dict[str, tuple[str, list[str]]] = {}
    for phase, pairs in hit.items():
        if role_of[phase] != "secondary":
            verdicts[phase] = judge(phase, pairs)
    explained = {id(pk) for phase, pairs in hit.items() if phase in verdicts and rank[verdicts[phase][0]] >= 2
                 for pk, _ in pairs}
    for phase, pairs in hit.items():
        if role_of[phase] == "secondary":
            rest = [(pk, ln) for pk, ln in pairs if id(pk) not in explained]
            if rest:
                verdicts[phase] = judge(phase, rest)

    # 한 피크가 여러 상에 걸리면 신뢰도가 가장 높은 상만 남긴다
    for p in counted:
        phases_hit = [ph for ph in dict.fromkeys(by_label[m]["phase"] for m in p.matches) if ph in verdicts]
        if not phases_hit:
            p.matches = []
            continue
        if id(p) in explained:
            phases_hit = [ph for ph in phases_hit if role_of[ph] != "secondary"]
        best = max(rank[verdicts[ph][0]] for ph in phases_hit)
        keep = [ph for ph in phases_hit if rank[verdicts[ph][0]] == best]
        p.matches = [m for m in p.matches if by_label[m]["phase"] in keep]
        p.match_confidence = verdicts[keep[0]][0]
        for ph in keep:
            p.notes.extend(m for m in verdicts[ph][1] if m not in p.notes)


def secondary_only(p: Peak, lines: list[dict]) -> bool:
    """매칭된 상이 모두 2차 상(붕화물·인화물·fcc 등, role = secondary)인지."""
    roles = {ln["label"]: ln["role"] for ln in lines}
    return bool(p.matches) and all(roles.get(m) == "secondary" for m in p.matches)
