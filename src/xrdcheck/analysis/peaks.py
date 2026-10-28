"""협폭(결정) 피크 검출: 잔차에 영면적 DoG 정합 필터를 적용하고 포아송 분산으로 z를 계산한다."""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit

from xrdcheck.analysis.profiles import gaussian, pseudo_voigt, pseudo_voigt_area
from xrdcheck.model import Peak

FWHM_TO_SIGMA = 1 / (2 * math.sqrt(2 * math.log(2)))


class NarrowDetector:
    """DoG 커널(σ₁ = 기기 FWHM/2.355, σ₂ = 비율·σ₁)은 면적이 0이라 넓은 halo의 모양 오차는 상쇄되고
    기기 분해능 폭의 좁은 피크에만 반응한다."""

    def __init__(self, x: np.ndarray, mu: np.ndarray, settings: dict):
        ds = settings["detector"]
        self.x, self.mu = x, mu
        self.fwhm = settings["instrument_fwhm_deg"]
        self.step = float(np.median(np.diff(x)))
        self.s1 = self.fwhm * FWHM_TO_SIGMA / self.step
        self.s2 = ds["dog_sigma_ratio"] * self.s1
        edge = ds["edge_exclude_deg"]
        self.valid = (x > x[0] + edge) & (x < x[-1] - edge)  # 필터 가장자리 왜곡 구간 제외
        impulse = np.zeros(int(12 * self.s2) | 1)
        impulse[len(impulse) // 2] = 1
        k = self.dog(impulse)
        self.sd = np.sqrt(np.convolve(mu, k**2, mode="same"))  # 포아송 분산 전파
        self.n_sim = ds["null_simulations"]
        self.seed = ds["null_seed"]

    def dog(self, v: np.ndarray, axis: int = -1) -> np.ndarray:
        return gaussian_filter1d(v, self.s1, axis=axis) - gaussian_filter1d(v, self.s2, axis=axis)

    def z(self, y: np.ndarray) -> np.ndarray:
        return np.where(self.valid, self.dog(y - self.mu) / self.sd, 0.0)

    def null_pvalue(self, z_obs: float, chunk: int = 500) -> float:
        """비정질(모델만) 가정에서 스캔 전체 z최대가 z_obs 이상 나올 확률 = 우연일 확률."""
        rng = np.random.default_rng(self.seed)
        hits, done = 0, 0
        while done < self.n_sim:
            m = min(chunk, self.n_sim - done)
            sims = rng.poisson(self.mu, size=(m, len(self.mu))) - self.mu
            z = np.where(self.valid, self.dog(sims, axis=1) / self.sd, 0.0)
            hits += int(np.sum(z.max(axis=1) >= z_obs))
            done += m
        return (hits + 1) / (self.n_sim + 1)

    def min_height(self, center: float, z_thr: float) -> float | None:
        """그 위치에서 z가 z_thr에 도달하는 좁은 피크의 최소 높이(counts) = 검출한계."""
        i = int(np.argmin(np.abs(self.x - center)))
        if not self.valid[i]:
            return None
        zu = self.dog(gaussian(self.x, 1.0, center, self.fwhm)) / self.sd
        return float(z_thr / zu[i]) if zu[i] > 0 else None

    def limit_curve(self, z_thr: float) -> np.ndarray:
        """2θ별 검출한계 곡선. 필터 응답이 위치와 무관하다는 점을 이용한 근사(가장자리 제외 구간에서 min_height와 같음)."""
        mid = len(self.x) // 2
        r0 = self.dog(gaussian(self.x, 1.0, self.x[mid], self.fwhm))[mid]
        return np.where(self.valid, z_thr * self.sd / r0, np.nan)


def find_candidates(x: np.ndarray, z: np.ndarray, z_min: float, min_sep: float) -> list[int]:
    """z가 큰 순서로, 이미 고른 점과 min_sep 이상 떨어진 점을 후보로 고른다."""
    picked: list[int] = []
    for i in np.argsort(z)[::-1]:
        if z[i] < z_min:
            break
        if all(abs(x[i] - x[j]) > min_sep for j in picked):
            picked.append(int(i))
    return picked


class Doublet:
    """Kα1 + Kα2 쌍 모양. 파장 정보가 없으면 Kα1만."""

    def __init__(self, ka1_A: float, ka2_A: float | None, ratio: float | None):
        self.ka1, self.ka2 = ka1_A, ka2_A
        self.ratio = ratio if (ka2_A and ratio) else 0.0

    def offset(self, two_theta: float) -> float:
        return kalpha2_offset_deg(two_theta, self.ka1, self.ka2) if self.ratio else 0.0

    def __call__(self, x, h, c, fw, eta):
        out = pseudo_voigt(x, h, c, fw, eta)
        if self.ratio:
            out = out + self.ratio * pseudo_voigt(x, h, c + self.offset(c), fw, eta)
        return out

    def of(self, x, pk: Peak):
        return self(x, pk.height, pk.two_theta, pk.fwhm, pk.eta)


def refine_peak(x, resid, y, mu, i: int, z_i: float, det: NarrowDetector, doublet: Doublet,
                settings: dict) -> Peak:
    """잔차에 국소 Kα1+Kα2 pseudo-Voigt 쌍 + 상수를 피팅해 Kα1의 위치·높이·FWHM·면적을 구한다."""
    rs = settings["peak_refine"]
    level = "검출" if z_i >= settings["z_detect"] else "의심"
    dc = rs["center_shift_max_deg"]
    fw_lo, fw_hi = rs["fwhm_range_deg"]
    off = 10 * float(np.sqrt(mu[i])) + 10

    def f(xx, h, c, fw, eta, o):
        return doublet(xx, h, c, fw, eta) + o

    try:
        # 넓은(나노결정) 피크는 꼬리가 잘리지 않도록 구간을 피크 폭의 ±4배까지 넓혀 한 번 더 피팅
        half = max(rs["window_deg"], 5 * det.fwhm)
        p0 = None
        for _ in range(2):
            w = (x > x[i] - half) & (x < x[i] + doublet.offset(x[i]) + half)
            xr, r, sig = x[w], resid[w], np.sqrt(np.maximum(y[w], 1))
            if p0 is None:
                near = np.abs(xr - x[i]) <= det.fwhm
                h0 = max(float(r[near].max()), 1.0)
                p0 = [h0, x[i], min(max(det.fwhm, fw_lo), fw_hi), 0.5, 0.0]
            lb = [0, x[i] - dc, fw_lo, 0, -off]
            ub = [max(10 * h0, 10), x[i] + dc, fw_hi, 1, off]
            p, cov = curve_fit(f, xr, r, p0=np.clip(p0, np.add(lb, 1e-9), np.subtract(ub, 1e-9)),
                               bounds=(lb, ub), sigma=sig, maxfev=5000)
            need = 4 * float(p[2])
            if need <= half * 1.05:
                break
            half, p0 = min(need, 6.0), list(p)
        h, c, fw, eta, _ = map(float, p)
        fw_err = float(np.sqrt(cov[2, 2])) if np.isfinite(cov[2, 2]) and cov[2, 2] >= 0 else None
        pk = Peak(two_theta=c, z=z_i, height=h, fwhm=fw, area=pseudo_voigt_area(h, fw, eta), level=level,
                  eta=eta, fwhm_err=fw_err)
        if fw >= fw_hi * 0.999:
            pk.notes.append(f"FWHM이 피팅 상한({fw_hi:g}°)에 닿음 — 실제 폭은 더 넓을 수 있음")
        return pk
    except (RuntimeError, ValueError):
        # 피팅이 안 되면 필터 응답으로 높이를 추정(가우시안, 기기 FWHM 가정)
        h = det.min_height(float(x[i]), z_i) or h0
        return Peak(two_theta=float(x[i]), z=z_i, height=h, fwhm=det.fwhm,
                    area=pseudo_voigt_area(h, det.fwhm, 0.0), level=level, refined=False, eta=0.0,
                    notes=["국소 피팅 실패 — 높이는 z로 추정"])


def detect_peaks(x, y, mu, det: NarrowDetector, doublet: Doublet, settings: dict) -> tuple[np.ndarray, list[Peak]]:
    """z가 큰 후보부터 처리한다. 앞서 확정한 피크(Kα1+Kα2 쌍)를 빼고 z를 다시 계산했을 때
    의심 기준 아래로 떨어지는 후보는 그 피크에 딸린 것(Kα2 어깨나 꼬리)으로 보고 세지 않는다."""
    z = det.z(y)
    idx = find_candidates(x, z, settings["z_suspect"], settings["detector"]["candidate_min_separation_deg"])
    explained = np.zeros_like(y, dtype=float)
    peaks: list[Peak] = []
    for i in idx:
        level = "검출" if z[i] >= settings["z_detect"] else "의심"
        counted = [p for p in peaks if p.counted]
        if counted and det.z(y - explained)[i] < settings["z_suspect"]:
            parent = min(counted, key=lambda p: abs(p.two_theta + doublet.offset(p.two_theta) - x[i]))
            what = "Kα2" if doublet.ratio and abs(parent.two_theta + doublet.offset(parent.two_theta) - x[i]) \
                <= max(det.fwhm, 0.1) else "꼬리"
            peaks.append(Peak(two_theta=float(x[i]), z=float(z[i]), height=float((y - mu)[i]), fwhm=det.fwhm,
                              area=0.0, level=level, refined=False, satellite_of=parent.two_theta,
                              notes=[f"{parent.two_theta:.2f}° 피크의 {what}로 설명됨(빼고 나면 z < 의심 기준)"]))
            continue
        pk = refine_peak(x, y - mu - explained, y, mu, i, float(z[i]), det, doublet, settings)
        peaks.append(pk)
        explained = explained + doublet.of(x, pk)
    return z, peaks


def kalpha2_offset_deg(two_theta_deg: float, ka1_A: float, ka2_A: float) -> float:
    """Kα2 피크가 Kα1 뒤로 떨어지는 거리: Δ2θ = 2·tanθ·Δλ/λ (도)."""
    theta = math.radians(two_theta_deg / 2)
    return math.degrees(2 * math.tan(theta) * (ka2_A - ka1_A) / ka1_A)


def flag_kalpha2(peaks: list[Peak], ka1_A: float, ka2_A: float | None, settings: dict) -> None:
    """더 강한 피크의 Kα2 위치에 세기 비가 맞는 피크가 있으면 Kα2로 표시(별도 피크로 세지 않음)."""
    if not ka2_A:
        return
    ks = settings["kalpha2"]
    tol = ks["position_tolerance_deg"]
    r_lo, r_hi = ks["intensity_ratio_range"]
    for strong in sorted(peaks, key=lambda p: p.height, reverse=True):
        if strong.satellite_of is not None:
            continue
        target = strong.two_theta + kalpha2_offset_deg(strong.two_theta, ka1_A, ka2_A)
        for weak in peaks:
            if weak is strong or weak.satellite_of is not None or weak.height >= strong.height:
                continue
            if abs(weak.two_theta - target) <= tol and r_lo <= weak.height / strong.height <= r_hi:
                weak.satellite_of = strong.two_theta
                weak.notes.append(f"{strong.two_theta:.2f}° 피크의 Kα2로 판단(위치·세기 비)")
