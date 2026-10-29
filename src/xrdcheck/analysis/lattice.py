"""α-Fe(Si) 격자상수와 Si 함량 환산(참고값).

- 격자상수: α-Fe(Si)·α-Fe·Fe3Si(DO3)에 매칭된 검출 피크마다 a = d·√(h²+k²+l²) (DO3는 a/2로 bcc 환산).
  여러 선이면 피크 높이로 가중 평균하고, 선이 3개 이상이면 시료 높이 오차를 줄이는 외삽값(cos²θ/sinθ → 0)도 함께 낸다.
- Si 함량: `lattice.si_calibration`의 (a, at.% Si) 점을 직선으로 이어 보간한다. 기본 표는 문헌값
  (순수 Fe 2.8665 Å / 저Si 기울기 −0.00069 Å/at% / FINEMET 나노결정 a = 2.840 Å ≈ 18 at% / Fe3Si 5.655 Å ÷ 2 = 25 at%).
- 한계: Fe–Si 2원계 기준이라 Co·Ni·Al·P 등 다른 원소가 고용되면 맞지 않는다. 2θ 0.02° 오차가 약 0.5 at%에 해당.
"""

from __future__ import annotations

import math

import numpy as np

from xrdcheck.analysis.profiles import d_spacing
from xrdcheck.model import AnalysisResult


def _hkl_n(hkl: str) -> int:
    return sum(int(c) ** 2 for c in hkl)


def si_from_a(a: float, table: list[list[float]]) -> tuple[float | None, str]:
    """보정표로 Si 함량(at.%)을 낸다. 표 범위 밖이면 (None, 사유)."""
    pts = sorted(table, key=lambda t: t[0])  # a 오름차순
    a_lo, a_hi = pts[0][0], pts[-1][0]
    if a > a_hi + 0.001:
        return None, f"격자상수가 순수 Fe({a_hi:.4f} Å)보다 큼 — 다른 원소 고용 또는 2θ 영점 오차"
    if a < a_lo - 0.001:
        return None, f"격자상수가 보정표 하한({a_lo:.4f} Å, {pts[0][1]:g} at%)보다 작음"
    x = float(np.interp(a, [p[0] for p in pts], [p[1] for p in pts]))
    return max(x, 0.0), ""


def estimate_lattice(r: AnalysisResult, settings: dict) -> dict | None:
    ls = settings.get("lattice")
    if not ls or not r.peaks:
        return None
    lam = r.pattern.kalpha1_A
    roles = {ln["label"]: ln for ln in r.phase_lines}
    dtt = math.radians(ls["two_theta_uncertainty_deg"]) / 2  # Δθ
    used = []
    for p in r.counted_peaks:
        if not (p.significant and p.refined):
            continue
        for m in p.matches:
            ln = roles.get(m)
            if ln is None or ln["phase"] not in ls["phases"]:
                continue
            a = d_spacing(p.two_theta, lam) * math.sqrt(_hkl_n(ln["hkl"]))
            if ln["phase"] == "Fe3Si(DO3)":
                a /= 2  # DO3 단위포는 bcc의 2배
            theta = math.radians(p.two_theta / 2)
            used.append({"label": m, "two_theta": p.two_theta, "a_A": a, "height": p.height,
                         "err_A": a * dtt / math.tan(theta), "f": math.cos(theta) ** 2 / math.sin(theta)})
            break
    if not used:
        return None
    w = np.array([u["height"] for u in used])
    a_vals = np.array([u["a_A"] for u in used])
    a_mean = float(np.average(a_vals, weights=w))
    err_pos = float(np.average([u["err_A"] for u in used], weights=w))
    spread = float(np.sqrt(np.average((a_vals - a_mean) ** 2, weights=w))) if len(used) > 1 else 0.0
    a_err = math.hypot(err_pos, spread)
    out = {"a_A": a_mean, "a_err_A": a_err, "lines": used, "a_extrap_A": None,
           "si_at": None, "si_err_at": None, "si_note": "", "table": ls["si_calibration"]}
    if len({u["label"] for u in used}) >= 3:  # 시료 높이 오차는 cos²θ/sinθ에 비례 → 0으로 외삽
        fit = np.polyfit([u["f"] for u in used], a_vals, 1, w=np.sqrt(w))
        out["a_extrap_A"] = float(fit[1])
    x, why = si_from_a(a_mean, ls["si_calibration"])
    out["si_at"], out["si_note"] = x, why
    if x is not None:
        lo, _ = si_from_a(a_mean + a_err, ls["si_calibration"])
        hi, _ = si_from_a(a_mean - a_err, ls["si_calibration"])
        if lo is not None and hi is not None:
            out["si_err_at"] = (hi - lo) / 2
    return out


def format_si(lat: dict | None) -> str:
    if not lat:
        return ""
    if lat["si_at"] is None:
        return "범위 밖"
    err = f" ± {lat['si_err_at']:.1f}" if lat.get("si_err_at") is not None else ""
    return f"{lat['si_at']:.1f}{err} at%"
