"""나노결정 판정과 Scherrer 결정립 크기.

기준(사용자 제공, 2026-10-28)
- 나노결정이려면 우선 **주 halo 위에 결정 피크가 있어야 한다**(필요조건).
  주 halo 범위 = 중심 − 비율·FWHM(좌) ~ 중심 + 비율·FWHM(우), 비율은 `nanocrystal.halo_window_fwhm_fraction`.
- 나노결정으로 판단되면 **Scherrer 식으로 결정립 크기(nm)**를 낸다.
  D = K·λ / (β·cos θ), β = √(B² − b²) (B: 측정 FWHM(Kα1), b: 기기 FWHM — 2θ별 표에서 보간)
"""

from __future__ import annotations

import math

import numpy as np

from xrdcheck.model import AnalysisResult, Peak, Verdict

NANO = "나노결정 후보"
NANO_SUSPECT = "나노결정 의심"
NOT_NANO = "나노결정 아님(주 halo에 피크 없음)"
SIZE_PHASES = ("α-Fe(Si)", "α-Fe", "Fe3Si(DO3)")  # 크기를 함께 보여줄 상


def main_halo_window(r: AnalysisResult, settings: dict) -> tuple[float, float] | None:
    h = r.halo
    if h is None:
        return None
    f = settings["nanocrystal"]["halo_window_fwhm_fraction"]
    return h.center - f * h.fwhm_left, h.center + f * h.fwhm_right


def instrument_fwhm(two_theta: float, settings: dict) -> float:
    table = np.array(settings["nanocrystal"]["scherrer_instrument_fwhm_deg"], dtype=float)
    return float(np.interp(two_theta, table[:, 0], table[:, 1]))


def _size_nm(two_theta: float, beta_deg: float, wavelength_A: float, k: float) -> float:
    return k * wavelength_A / (math.radians(beta_deg) * math.cos(math.radians(two_theta / 2))) / 10


def scherrer(pk: Peak, wavelength_A: float, settings: dict) -> dict:
    """한 피크의 Scherrer 크기. limit: "" | "분해능 한계(이상)" | "폭 상한(이하)"."""
    ns = settings["nanocrystal"]
    k = ns["scherrer_k"]
    b = instrument_fwhm(pk.two_theta, settings)
    big = pk.fwhm
    out = {"two_theta": pk.two_theta, "fwhm_obs": big, "fwhm_inst": b, "label": "/".join(pk.matches) or "매칭 없음",
           "size_nm": None, "size_err_nm": None, "limit": ""}
    if not pk.refined:
        out["limit"] = "피팅 실패"
        return out
    if big < ns["scherrer_min_broadening_ratio"] * b:
        # 측정 폭이 기기 폭에 너무 가까움 → 크기는 이 값 이상으로만 말할 수 있음
        beta = math.sqrt((ns["scherrer_min_broadening_ratio"] * b) ** 2 - b**2)
        out.update(size_nm=_size_nm(pk.two_theta, beta, wavelength_A, k), limit="분해능 한계(이상)")
        return out
    beta = math.sqrt(big**2 - b**2)
    d = _size_nm(pk.two_theta, beta, wavelength_A, k)
    out["size_nm"] = d
    if pk.fwhm_err is not None:
        out["size_err_nm"] = d * (big * pk.fwhm_err / beta) / beta  # σ_β = B·σ_B/β, σ_D = D·σ_β/β
    fw_hi = settings["peak_refine"]["fwhm_range_deg"][1]
    if big >= fw_hi * 0.999:
        out["limit"] = "폭 상한(이하)"
    return out


def format_size(s: dict) -> str:
    if s["size_nm"] is None:
        return "산출 불가(" + s["limit"] + ")" if s["limit"] else "-"
    if s["limit"] == "분해능 한계(이상)":
        return f"> {s['size_nm']:.0f} nm"
    if s["limit"] == "폭 상한(이하)":
        return f"≤ {s['size_nm']:.1f} nm"
    err = f" ± {s['size_err_nm']:.1f}" if s["size_err_nm"] is not None else ""
    return f"{s['size_nm']:.1f}{err} nm"


def classify_nano(r: AnalysisResult, settings: dict) -> dict | None:
    """비정질·판정 불가면 None. 결정 피크가 있으면 주 halo 위 피크 여부로 나노결정 후보/의심/아님을 정하고,
    후보이면 주 halo 위 가장 강한 피크로 Scherrer 크기를 낸다(같은 계열 다른 선의 크기도 함께)."""
    if r.verdict in (Verdict.AMORPHOUS, Verdict.UNDETERMINED):
        return None
    win = main_halo_window(r, settings)
    if win is None:
        return None
    lo, hi = win
    on_halo = [p for p in r.counted_peaks if lo <= p.two_theta <= hi]
    sig = [p for p in on_halo if p.significant]
    if r.verdict == Verdict.DETECTED and sig:
        label = NANO
    elif on_halo:
        label = NANO_SUSPECT
    else:
        label = NOT_NANO
    out = {"label": label, "window": (lo, hi), "halo_peaks": [p.two_theta for p in on_halo],
           "size": None, "other_sizes": [],
           "note": "필요조건(주 halo 위 피크) 확인. 크기는 Scherrer(K = %g), 기기 폭은 %s"
                   % (settings["nanocrystal"]["scherrer_k"],
                      "표준시료 측정값" if settings["nanocrystal"]["scherrer_instrument_measured"]
                      else "실측 데이터 추정치(표준시료 미측정)")}
    if label == NANO:
        lam = r.pattern.kalpha1_A
        main = max(sig, key=lambda p: p.height)
        out["size"] = scherrer(main, lam, settings)
        others = [p for p in r.counted_peaks if p is not main and p.significant and p.refined
                  and any(m.startswith(SIZE_PHASES) for m in p.matches)]
        out["other_sizes"] = [scherrer(p, lam, settings) for p in sorted(others, key=lambda p: p.two_theta)]
    return out
