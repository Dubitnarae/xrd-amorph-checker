"""피크 모양 함수."""

from __future__ import annotations

import math

import numpy as np

LN2_4 = 4 * math.log(2)


def gaussian(x, height, center, fwhm):
    return height * np.exp(-LN2_4 * ((x - center) / fwhm) ** 2)


def pseudo_voigt(x, height, center, fwhm, eta):
    """eta = 로렌츠 비율(0 = 가우시안, 1 = 로렌츠)."""
    u = (x - center) / fwhm
    return height * (eta / (1 + 4 * u**2) + (1 - eta) * np.exp(-LN2_4 * u**2))


def split_pseudo_voigt(x, height, center, fwhm_left, fwhm_right, eta):
    """비대칭 pseudo-Voigt(좌/우 FWHM 따로) — 비정질 halo용."""
    return pseudo_voigt(x, height, center, np.where(x < center, fwhm_left, fwhm_right), eta)


def pseudo_voigt_area(height, fwhm, eta):
    return height * fwhm * (eta * math.pi / 2 + (1 - eta) * math.sqrt(math.pi / LN2_4))


def d_spacing(two_theta_deg, wavelength_A):
    return wavelength_A / (2 * math.sin(math.radians(two_theta_deg / 2)))


def two_theta_from_d(d_A, wavelength_A):
    s = wavelength_A / (2 * d_A)
    return 2 * math.degrees(math.asin(s)) if 0 < s < 1 else None
