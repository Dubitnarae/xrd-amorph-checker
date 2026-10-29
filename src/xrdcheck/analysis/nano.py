"""나노결정 판정과 Scherrer 결정립 크기, 결정 분율(참고).

기준(사용자 제공, 2026-10-28)
- 나노결정이려면 우선 **주 halo 위에 결정 피크가 있어야 한다**(필요조건).
  주 halo 범위 = 중심 − 비율·FWHM(좌) ~ 중심 + 비율·FWHM(우), 비율은 `nanocrystal.halo_window_fwhm_fraction`.
- Scherrer 식은 약 100 nm까지만 쓸 수 있다. 크기를 내기 **전에** 측정 폭이 100 nm에 해당하는 폭보다 좁은 피크는
  걸러 낸다(`nanocrystal.scherrer_max_nm`). 걸러진 피크는 "100 nm 초과"로만 표시하고 크기를 내지 않는다.
- 남은 주 halo 위 피크 중 가장 강한 피크로 **Scherrer 결정립 크기(nm)**를 내고, 크기가 10–90 nm
  (`nanocrystal.size_range_nm`)이면 판정을 "나노결정상 후보"로 바꾼다. 범위 밖이면 "결정상 검출" 그대로.
  D = K·λ / (β·cos θ), β = √(B² − b²) (B: 측정 FWHM(Kα1), b: 기기 FWHM — 2θ별 표에서 보간)
- 붕화물·인화물·fcc 등 2차 상(role = secondary)에만 매칭된 피크는 주 halo 위에 있어도 나노결정 판단에서 뺀다
  (`nanocrystal.exclude_secondary_peaks`, 2026-10-29 상 카드 추가와 함께).
- 결정 분율 Xc = Ac / (Ac + Aa) (Ac: 결정 피크 면적(Kα2 포함), Aa: halo 면적). 산란인자 차이를 보정하지 않은 참고값.
"""

from __future__ import annotations

import math

import numpy as np

from xrdcheck.model import AnalysisResult, Peak, Verdict

NANO = "나노결정상 후보"
NANO_SUSPECT = "나노결정 의심"
NOT_NANO = "나노결정 아님(주 halo에 피크 없음)"
OUT_SMALL = "나노결정 범위 밖(%g nm 미만)"
OUT_LARGE = "나노결정 범위 밖(%g nm 초과)"
OVER_SCHERRER = "Scherrer 적용 범위 밖(%g nm 초과)"
OVER_LIMIT = "적용 범위 초과"  # scherrer()의 limit 값
WIDTH_CAP = "폭 상한(이하)"
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


def fwhm_for_size(size_nm: float, two_theta: float, wavelength_A: float, settings: dict) -> float:
    """결정립 크기가 size_nm일 때 기대되는 측정 FWHM(°): B = √(β² + b²)."""
    k = settings["nanocrystal"]["scherrer_k"]
    beta = math.degrees(k * wavelength_A / (size_nm * 10 * math.cos(math.radians(two_theta / 2))))
    return math.hypot(beta, instrument_fwhm(two_theta, settings))


def over_scherrer_range(pk: Peak, wavelength_A: float, settings: dict) -> bool:
    """측정 폭이 Scherrer 적용 상한(기본 100 nm)에 해당하는 폭보다 좁으면 True — 크기를 내지 않는다."""
    d_max = settings["nanocrystal"]["scherrer_max_nm"]
    return pk.fwhm < fwhm_for_size(d_max, pk.two_theta, wavelength_A, settings)


def scherrer(pk: Peak, wavelength_A: float, settings: dict) -> dict:
    """한 피크의 Scherrer 크기. limit: "" | "적용 범위 초과" | "폭 상한(이하)" | "피팅 실패"."""
    ns = settings["nanocrystal"]
    k = ns["scherrer_k"]
    b = instrument_fwhm(pk.two_theta, settings)
    big = pk.fwhm
    out = {"two_theta": pk.two_theta, "fwhm_obs": big, "fwhm_inst": b, "label": "/".join(pk.matches) or "매칭 없음",
           "size_nm": None, "size_err_nm": None, "limit": "", "max_nm": ns["scherrer_max_nm"]}
    if not pk.refined:
        out["limit"] = "피팅 실패"
        return out
    if over_scherrer_range(pk, wavelength_A, settings):
        out["limit"] = OVER_LIMIT  # 폭이 기기 폭에 너무 가까움 → Scherrer로 크기를 정할 수 없음
        return out
    beta = math.sqrt(big**2 - b**2)
    d = _size_nm(pk.two_theta, beta, wavelength_A, k)
    out["size_nm"] = d
    if pk.fwhm_err is not None:
        out["size_err_nm"] = d * (big * pk.fwhm_err / beta) / beta  # σ_β = B·σ_B/β, σ_D = D·σ_β/β
    fw_hi = settings["peak_refine"]["fwhm_range_deg"][1]
    if big >= fw_hi * 0.999:
        out["limit"] = WIDTH_CAP
    return out


def format_size(s: dict) -> str:
    if s["limit"] == OVER_LIMIT:
        return f"> {s['max_nm']:g} nm"
    if s["size_nm"] is None:
        return "산출 불가(" + s["limit"] + ")" if s["limit"] else "-"
    if s["limit"] == WIDTH_CAP:
        return f"≤ {s['size_nm']:.1f} nm"
    err = f" ± {s['size_err_nm']:.1f}" if s["size_err_nm"] is not None else ""
    return f"{s['size_nm']:.1f}{err} nm"


def crystalline_fraction(r: AnalysisResult) -> float | None:
    """Xc = Ac / (Ac + Aa). Ac는 판정에 세는 검출 피크 면적(Kα2 포함), Aa는 주·제2 halo 면적(스캔 범위 안)."""
    if r.halo is None:
        return None
    x = r.pattern.two_theta
    aa = sum(float(np.trapezoid(r.halo.components[k], x)) for k in ("주 halo", "제2 halo") if k in r.halo.components)
    ac = sum(p.area for p in r.counted_peaks if p.significant and p.refined) * (1 + (r.pattern.kalpha2_ratio or 0))
    if aa <= 0 or ac <= 0:
        return None
    return ac / (ac + aa)


def classify_nano(r: AnalysisResult, settings: dict) -> dict | None:
    """비정질·판정 불가면 None. 결정 피크가 있으면 주 halo 위 피크 여부로 나노결정 여부를 정한다.

    결정상 검출이고 주 halo 위 검출 피크가 있으면: 100 nm 초과 피크를 먼저 거르고, 남은 피크 중 가장 강한 피크로
    Scherrer 크기를 낸다. 크기가 설정 범위(10–90 nm) 안이면 label = NANO, in_range = True.
    """
    if r.verdict in (Verdict.AMORPHOUS, Verdict.UNDETERMINED):
        return None
    win = main_halo_window(r, settings)
    if win is None:
        return None
    ns = settings["nanocrystal"]
    lo, hi = win
    lam = r.pattern.kalpha1_A
    d_lo, d_hi = ns["size_range_nm"]
    on_halo = [p for p in r.counted_peaks if lo <= p.two_theta <= hi]
    secondary = []
    if ns.get("exclude_secondary_peaks", True):  # 붕화물 등 2차 상에만 매칭된 피크는 α-Fe(Si) 나노결정이 아니다
        from xrdcheck.analysis.phases import secondary_only

        secondary = [p for p in on_halo if secondary_only(p, r.phase_lines)]
        on_halo = [p for p in on_halo if p not in secondary]
    sig = [p for p in on_halo if p.significant]
    out = {"label": NOT_NANO, "in_range": False, "window": (lo, hi), "halo_peaks": [p.two_theta for p in on_halo],
           "size": None, "other_sizes": [], "over_peaks": [], "xc": None,
           "secondary_peaks": [(p.two_theta, "/".join(p.matches)) for p in secondary],
           "note": "필요조건(주 halo 위 피크) 확인. 크기는 Scherrer(K = %g, %g nm 이하만), 나노결정 범위 %g–%g nm, 기기 폭은 %s"
                   % (ns["scherrer_k"], ns["scherrer_max_nm"], d_lo, d_hi,
                      "표준시료 측정값" if ns["scherrer_instrument_measured"] else "실측 데이터 추정치(표준시료 미측정)")}
    if not (r.verdict == Verdict.DETECTED and sig):
        out["label"] = NANO_SUSPECT if on_halo else NOT_NANO
        return out

    # Scherrer 적용 전에 100 nm 초과(폭이 기기 폭에 너무 가까운) 피크를 거른다
    over = [p for p in sig if p.refined and over_scherrer_range(p, lam, settings)]
    usable = [p for p in sig if p.refined and p not in over]
    out["over_peaks"] = [p.two_theta for p in over]
    if not usable:
        out["label"] = OVER_SCHERRER % ns["scherrer_max_nm"]
        out["size"] = scherrer(max(sig, key=lambda p: p.height), lam, settings)
        return out
    main = max(usable, key=lambda p: p.height)
    s = scherrer(main, lam, settings)
    out["size"] = s
    others = [p for p in r.counted_peaks if p is not main and p.significant and p.refined
              and any(m.startswith(SIZE_PHASES) for m in p.matches)]
    out["other_sizes"] = [scherrer(p, lam, settings) for p in sorted(others, key=lambda p: p.two_theta)]
    d = s["size_nm"]
    if s["limit"] == WIDTH_CAP or d < d_lo:
        out["label"] = OUT_SMALL % d_lo
    elif d > d_hi:
        out["label"] = OUT_LARGE % d_hi
    else:
        out["label"], out["in_range"] = NANO, True
        out["xc"] = crystalline_fraction(r)
    return out


def size_short(r: AnalysisResult) -> str:
    """목록용 짧은 표기: 'X nm' / '> 100 nm' / '≤ X nm' / 의심 / 아님 / 빈칸."""
    n = r.nano
    if not n:
        return ""
    s = n.get("size")
    if s:
        if s["limit"] == OVER_LIMIT:
            return f"> {s['max_nm']:g} nm"
        if s["size_nm"] is not None:
            return f"{'≤ ' if s['limit'] == WIDTH_CAP else ''}{s['size_nm']:.0f} nm"
    return "의심" if n["label"] == NANO_SUSPECT else "아님"
