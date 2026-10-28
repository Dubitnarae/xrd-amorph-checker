"""배경 + 비정질 halo 피팅(가중 최소제곱, σ = √max(I, 1))."""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit

from xrdcheck.analysis.background import PARAM_NAMES as BG_NAMES
from xrdcheck.analysis.background import background
from xrdcheck.analysis.profiles import d_spacing, pseudo_voigt, split_pseudo_voigt
from xrdcheck.model import HaloFit

MAIN_NAMES = ["A1", "c1", "w1L", "w1R", "eta1"]
SECOND_NAMES = ["A2", "c2", "w2", "eta2"]


class HaloFitError(RuntimeError):
    pass


class HaloModel:
    """주 halo(비대칭 PV) + 제2 halo(PV, 선택) + 배경."""

    def __init__(self, x_start: float, x_mid: float, with_second: bool):
        self.x_start, self.x_mid, self.with_second = x_start, x_mid, with_second
        self.names = MAIN_NAMES + (SECOND_NAMES if with_second else []) + BG_NAMES

    def _split(self, p):
        main = p[:5]
        second = p[5:9] if self.with_second else None
        bg = p[9:] if self.with_second else p[5:]
        return main, second, bg

    def __call__(self, x, *p):
        return sum(self.components(x, p).values())

    def components(self, x, p) -> dict[str, np.ndarray]:
        main, second, bg = self._split(p)
        out = {"배경": background(x, *bg, self.x_start, self.x_mid), "주 halo": split_pseudo_voigt(x, *main)}
        if second is not None:
            out["제2 halo"] = pseudo_voigt(x, *second)
        return out


def bic(chi2: float, n_params: int, n_points: int) -> float:
    return chi2 + n_params * math.log(n_points)


def fit_halo(x: np.ndarray, y: np.ndarray, wavelength_A: float, settings: dict,
             mask: np.ndarray | None = None) -> HaloFit:
    """mask가 False인 점(결정 피크 주변)은 피팅에서 뺀다."""
    hs = settings["halo"]
    mask = np.ones_like(x, dtype=bool) if mask is None else mask
    step = float(np.median(np.diff(x)))
    ys = gaussian_filter1d(y, hs["smooth_fwhm_deg"] / step)

    lo, hi = hs["search_range_deg"]
    win = (x > lo) & (x < hi)
    if not win.any():
        raise HaloFitError("주 halo 탐색 구간에 데이터가 없습니다.")
    c1 = float(x[win][np.argmax(ys[win])])
    blo, bhi = hs["baseline_range_deg"]
    base_win = (x > blo) & (x < bhi)
    base = float(np.percentile(ys[base_win] if base_win.sum() >= 20 else ys, 20))
    base = max(base, 0.0)
    A1 = max(float(ys[win].max()) - base, 1.0)
    head = max(float(y[:20].mean()) - base, 1.0)

    with_second = x[-1] >= hs["second_min_scan_end_deg"]
    model = HaloModel(float(x[0]), float((x[0] + x[-1]) / 2), with_second)
    cb = hs["center_bound_deg"]
    p0 = [A1, c1, 6.0, 6.0, 0.5]
    lb = [0, c1 - cb, 1, 1, 0]
    ub = [10 * A1 + 10, c1 + cb, 15, 15, 1]
    if with_second:
        s_lo, s_hi = hs["second_range_deg"]
        p0 += [A1 * 0.15, (s_lo + s_hi) / 2, 10.0, 0.5]
        lb += [0, s_lo, 3, 0]
        ub += [5 * A1 + 10, s_hi, 25, 1]
    p0 += [base, 0.0, head, 8.0]
    lb += [0, -5, 0, 0.5]
    ub += [10 * base + 10, 5, 50 * A1 + 100, 40]
    p0 = np.clip(p0, np.array(lb) + 1e-9, np.array(ub) - 1e-9)

    sigma = np.sqrt(np.maximum(y, 1))
    try:
        p, _ = curve_fit(model, x[mask], y[mask], p0=p0, bounds=(lb, ub), sigma=sigma[mask], maxfev=40000)
    except (RuntimeError, ValueError) as e:
        raise HaloFitError(f"halo 피팅이 수렴하지 않았습니다: {e}") from e

    mu = np.maximum(model(x, *p), 1e-6)
    chi2 = float(np.sum(((y[mask] - mu[mask]) / sigma[mask]) ** 2))
    n = int(mask.sum())
    comps = model.components(x, p)
    get = dict(zip(model.names, p))
    center = float(get["c1"])
    d = d_spacing(center, wavelength_A)
    return HaloFit(
        params=np.asarray(p),
        param_names=model.names,
        mu=mu,
        components=comps,
        chi2_red=chi2 / (n - len(p)),
        bic=bic(chi2, len(p), n),
        n_used=n,
        center=center,
        fwhm_left=float(get["w1L"]),
        fwhm_right=float(get["w1R"]),
        d_A=d,
        q_invA=2 * math.pi / d,
        r1_A=1.23 * d,  # Ehrenfest 근사: 최근접 원자간 거리
        second_center=float(get["c2"]) if with_second else None,
        second_fwhm=float(get["w2"]) if with_second else None,
    )


def halo_model_for(fit: HaloFit, x: np.ndarray) -> HaloModel:
    return HaloModel(float(x[0]), float((x[0] + x[-1]) / 2), fit.second_center is not None)
