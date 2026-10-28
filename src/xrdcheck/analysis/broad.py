"""넓은 성분 지표(참고용): α-Fe(Si)(110) 근처에 넓은 PV 성분을 더해 모델이 얼마나 좋아지는지 본다.

halo 모양 차이인지 미세 결정인지는 이것만으로 구분할 수 없으므로, 보정(Phase 4) 전에는 판정에 쓰지 않는다.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import curve_fit

from xrdcheck.analysis.halo import bic, halo_model_for
from xrdcheck.analysis.profiles import pseudo_voigt
from xrdcheck.model import HaloFit


def broad_indicator(x, y, fit: HaloFit, line_2theta: float, wavelength_A: float, settings: dict,
                    mask: np.ndarray | None = None) -> dict | None:
    bs = settings["broad_component"]
    mask = np.ones_like(x, dtype=bool) if mask is None else mask
    base = halo_model_for(fit, x)
    k = len(fit.params)

    def model(xx, *q):
        return base(xx, *q[:k]) + pseudo_voigt(xx, q[k], q[k + 1], q[k + 2], 0.5)

    win = bs["center_window_deg"]
    fw_lo, fw_hi = bs["fwhm_range_deg"]
    p0 = list(fit.params) + [5.0, line_2theta, min(max(1.0, fw_lo), fw_hi)]
    lb = [-np.inf] * k + [0, line_2theta - win, fw_lo]
    ub = [np.inf] * k + [500, line_2theta + win, fw_hi]
    sigma = np.sqrt(np.maximum(y, 1))
    try:
        q, _ = curve_fit(model, x[mask], y[mask], p0=p0, bounds=(lb, ub), sigma=sigma[mask], maxfev=40000)
    except (RuntimeError, ValueError):
        return None
    chi2 = float(np.sum(((y[mask] - model(x[mask], *q)) / sigma[mask]) ** 2))
    d_bic = fit.bic - bic(chi2, len(q), int(mask.sum()))
    center, fwhm = float(q[k + 1]), float(q[k + 2])
    size_nm = bs["scherrer_k"] * wavelength_A / (math.radians(fwhm) * math.cos(math.radians(center / 2))) / 10
    return {
        "delta_bic": d_bic,
        "center_2theta": center,
        "fwhm_deg": fwhm,
        "height_counts": float(q[k]),
        "scherrer_nm_uncorrected": size_nm,
        "note": "참고값 — 보정 전에는 판정에 쓰지 않음(기기 폭 보정 전 Scherrer)",
    }
