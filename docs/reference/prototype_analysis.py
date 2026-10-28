"""
참고용 프로토타입 — 계획 수립 시 알고리즘과 기대값을 검증하려고 만든 단일 스크립트.

* 실제 구현은 PLAN.md의 폴더 구조(src/xrdcheck/...)로 나눠 다시 작성할 것.
* 이 파일의 출력값이 tests/expected/SMP-01a-260910-001.json 의 근거임.

사용법
    python prototype_analysis.py ../../samples/SMP-01a-260910-001.xrdml
    python prototype_analysis.py ../../samples/SMP-01a-260910-001.csv
    # 가상 결정 피크 주입 테스트 (위치:높이[counts], FWHM 0.15°)
    python prototype_analysis.py ../../samples/SMP-01a-260910-001.xrdml --inject 44.67:40,65.02:15

필요 패키지: numpy, scipy
"""
from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit

LN2_4 = 4 * math.log(2)


# ---------------------------------------------------------------- 파일 읽기
def read_xrdml(path):
    root = ET.parse(path).getroot()
    ns = {"x": root.tag.split("}")[0].strip("{")}  # 스키마 버전(1.x/2.x)에 상관없이 네임스페이스 추출
    scan = root.find(".//x:scan", ns)  # 첫 번째 scan만 사용 (여러 scan이면 경고 대상)
    dp = scan.find("x:dataPoints", ns)
    node = dp.find("x:intensities", ns)
    if node is None:  # 일부 버전은 <counts>
        node = dp.find("x:counts", ns)
    y = np.array(node.text.split(), float)
    ct_node = dp.find("x:commonCountingTime", ns)
    ct = float(ct_node.text) if ct_node is not None else None
    if "per second" in (node.get("unit") or "") and ct:
        y = y * ct  # 포아송 가중치를 위해 counts로 환산
    pos = next(p for p in dp.findall("x:positions", ns) if p.get("axis") == "2Theta")
    lp = pos.find("x:listPositions", ns)
    if lp is not None:
        x = np.array(lp.text.split(), float)
    else:
        x0 = float(pos.find("x:startPosition", ns).text)
        x1 = float(pos.find("x:endPosition", ns).text)
        x = np.linspace(x0, x1, len(y))
    wl = root.find(".//x:usedWavelength", ns)
    meta = {
        "ka1": float(wl.find("x:kAlpha1", ns).text),
        "ka2": float(wl.find("x:kAlpha2", ns).text),
        "counting_time_s": ct,
        "file_timestamp": (root.findtext(".//x:startTimeStamp", default="", namespaces=ns)),
        "n_scans": len(root.findall(".//x:scan", ns)),
    }
    return x, y, meta


def read_xpert_csv(path):
    lines = open(path, encoding="cp1252", errors="replace").read().splitlines()
    meta = {}
    k = None
    for i, line in enumerate(lines):
        if line.strip() == "Angle,Intensity":
            k = i
            break
        if "," in line:
            key, _, val = line.partition(",")
            meta[key.strip()] = val.strip().strip('"')
    data = np.array([[float(v) for v in l.split(",")[:2]] for l in lines[k + 1:] if l.strip()])
    meta = {
        "ka1": float(meta.get("K-Alpha1 wavelength", 1.540598)),
        "ka2": float(meta.get("K-Alpha2 wavelength", 1.544426)),
        "counting_time_s": float(meta["Time per step"]) if "Time per step" in meta else None,
        "file_timestamp": meta.get("File date and time", ""),
        "n_scans": 1,
    }
    return data[:, 0], data[:, 1], meta


def read_any(path):
    p = path.lower()
    if p.endswith(".xrdml"):
        return read_xrdml(path)
    if p.endswith(".csv"):
        return read_xpert_csv(path)
    raise ValueError("지원하지 않는 형식: " + path)


# ---------------------------------------------------------------- 모델
def pv(x, A, c, w, eta):
    g = np.exp(-LN2_4 * ((x - c) / w) ** 2)
    l = 1 / (1 + 4 * ((x - c) / w) ** 2)
    return A * (eta * l + (1 - eta) * g)


def spv(x, A, c, wl, wr, eta):  # 비대칭(split) pseudo-Voigt — 비정질 halo용
    w = np.where(x < c, wl, wr)
    return pv(x, A, c, w, eta)


def make_model(x_start, x_mid):
    def model(x, A1, c1, wl, wr, e1, A2, c2, w2, e2, b0, b1, B, t):
        bg = b0 + b1 * (x - x_mid) + B * np.exp(-(x - x_start) / t)
        return spv(x, A1, c1, wl, wr, e1) + pv(x, A2, c2, w2, e2) + bg
    return model


def fit_halo(x, y):
    step = x[1] - x[0]
    ys = gaussian_filter1d(y, 0.5 / step)
    win = (x > 38) & (x < 52)
    c1 = x[win][np.argmax(ys[win])]
    base = np.percentile(ys[(x > 55) & (x < 75)], 20)
    A1 = max(ys[win].max() - base, 1)
    model = make_model(x[0], (x[0] + x[-1]) / 2)
    p0 = [A1, c1, 6, 6, 0.5, A1 * 0.15, 80, 10, 0.5, base, 0, max(y[:20].mean() - base, 1), 8]
    lb = [0, c1 - 3, 1, 1, 0, 0, 72, 3, 0, 0, -5, 0, 0.5]
    ub = [10 * A1 + 10, c1 + 3, 15, 15, 1, 5 * A1 + 10, 88, 25, 1, 10 * base + 10, 5, 50 * A1 + 100, 40]
    sig = np.sqrt(np.maximum(y, 1))
    p, cov = curve_fit(model, x, y, p0=p0, bounds=(lb, ub), sigma=sig, maxfev=40000)
    mu = np.maximum(model(x, *p), 1e-6)
    r = (y - mu) / sig
    chi2 = float(np.sum(r ** 2))
    return model, p, mu, chi2 / (len(x) - len(p)), chi2 + len(p) * math.log(len(x))


# ---------------------------------------------------------------- 협폭 피크 검출 (정합 필터)
class NarrowDetector:
    """영면적 DoG 커널 = 기기 분해능 폭의 좁은 피크에만 반응, 넓은 halo/배경 오차는 상쇄."""

    def __init__(self, x, mu, inst_fwhm=0.15, edge_deg=0.6):
        self.step = x[1] - x[0]
        self.edge = (x > x[0] + edge_deg) & (x < x[-1] - edge_deg)  # 필터 가장자리 왜곡 구간 제외
        self.s1 = inst_fwhm / 2.3548 / self.step
        self.s2 = 4 * self.s1
        imp = np.zeros(int(12 * self.s2) | 1)
        imp[len(imp) // 2] = 1
        k = self.dog(imp)
        self.var = np.convolve(mu, k ** 2, mode="same")  # 포아송 분산 전파
        self.x, self.mu, self.fw = x, mu, inst_fwhm

    def dog(self, v):
        return gaussian_filter1d(v, self.s1) - gaussian_filter1d(v, self.s2)

    def z(self, y):
        z = self.dog(y - self.mu) / np.sqrt(self.var)
        return np.where(self.edge, z, 0.0)

    def null_pvalue(self, z_obs, n=2000, seed=0):
        """비정질(모델만) 가정에서 스캔 전체 max-z가 z_obs 이상 나올 확률 (우연일 확률)."""
        rng = np.random.default_rng(seed)
        mx = np.array([self.z(rng.poisson(self.mu)).max() for _ in range(n)])
        return float((np.sum(mx >= z_obs) + 1) / (n + 1))

    def min_height(self, c, z_thr):
        """해당 위치에서 z_thr에 도달하는 좁은 피크의 최소 높이(counts) = 검출한계."""
        unit = np.exp(-LN2_4 * ((self.x - c) / self.fw) ** 2)
        zu = self.dog(unit) / np.sqrt(self.var)
        return float(z_thr / zu[np.argmin(abs(self.x - c))])


# ---------------------------------------------------------------- 상 라이브러리 (시드: 입방정만, 격자상수로 계산)
def cubic_lines(a, hkls, ka1):
    out = []
    for hkl, rel in hkls:
        d = a / math.sqrt(sum(i * i for i in hkl))
        out.append(("".join(map(str, hkl)), round(2 * math.degrees(math.asin(ka1 / (2 * d))), 3), rel))
    return out


def phase_library(ka1):
    return {
        # α-Fe a=2.8665 Å (bcc). 상대강도는 대략값 — 카드값으로 교체할 것
        "α-Fe": cubic_lines(2.8665, [((1, 1, 0), 100), ((2, 0, 0), 20), ((2, 1, 1), 30)], ka1),
        # Fe3O4 a=8.396 Å (spinel). 상대강도 대략값
        "Fe3O4": cubic_lines(8.396, [((2, 2, 0), 30), ((3, 1, 1), 100), ((4, 0, 0), 20),
                                     ((5, 1, 1), 30), ((4, 4, 0), 40)], ka1),
    }


# ---------------------------------------------------------------- 실행
Z_DETECT = 5.0  # 이 시료 조건에서 비정질 가정 시 스캔당 오경보 ≈ 0.1% (MC 3000회로 확인)
Z_SUSPECT = 4.5  # ≈ 1%


def analyze(path, inject=None, inst_fwhm=0.15):
    x, y, meta = read_any(path)
    if inject:  # 결정론적 주입(노이즈 없이 기대값만 더함) — 테스트 재현성
        for c, h in inject:
            y = y + h * np.exp(-LN2_4 * ((x - c) / inst_fwhm) ** 2)
    model, p, mu, chi2r, bic0 = fit_halo(x, y)
    det = NarrowDetector(x, mu, inst_fwhm)
    z = det.z(y)
    z_thr = Z_DETECT

    # 후보 피크: z 상위부터 0.3° 이상 떨어진 극대값
    cands = []
    for i in np.argsort(z)[::-1]:
        if z[i] < Z_SUSPECT:
            break
        if all(abs(x[i] - x[j]) > 0.3 for j in cands):
            cands.append(i)
    lib = phase_library(meta["ka1"])
    peaks = []
    for i in cands:
        match = [f"{ph}({hkl})" for ph, lines in lib.items() for hkl, tt, _ in lines if abs(tt - x[i]) <= 0.25]
        peaks.append({"two_theta": round(float(x[i]), 3), "z": round(float(z[i]), 2),
                      "significant": bool(z[i] >= z_thr), "match": match})
    sig = [pk for pk in peaks if pk["significant"]]
    if sig and (any(pk["match"] for pk in sig) or len(sig) >= 2):
        verdict = "결정상 검출"
    elif peaks:
        verdict = "결정상 의심"
    else:
        verdict = "비정질"

    # 정보 지표: α-Fe(110) 위치의 넓은 성분(나노결정/정점 형상) — 보정 전에는 판정에 쓰지 않음
    def m1(xx, *q):
        return model(xx, *q[:13]) + pv(xx, q[13], q[14], q[15], 0.5)
    c110 = lib["α-Fe"][0][1]
    lb = [-np.inf] * 13 + [0, c110 - 0.4, 0.3]
    ub = [np.inf] * 13 + [500, c110 + 0.4, 2.5]
    try:
        q, _ = curve_fit(m1, x, y, p0=list(p) + [5, c110, 1.0], bounds=(lb, ub),
                         sigma=np.sqrt(np.maximum(y, 1)), maxfev=40000)
        chi2_1 = np.sum(((y - m1(x, *q)) / np.sqrt(np.maximum(y, 1))) ** 2)
        dbic = bic0 - (chi2_1 + 16 * math.log(len(x)))
        theta = math.radians(q[14] / 2)
        scherrer_nm = 0.9 * meta["ka1"] / (math.radians(q[15]) * math.cos(theta)) / 10
        broad = {"dBIC": round(float(dbic), 1), "fwhm_deg": round(float(q[15]), 2),
                 "scherrer_nm_uncorrected": round(scherrer_nm, 1)}
    except RuntimeError:
        broad = None

    lam = meta["ka1"]
    th = math.radians(p[1] / 2)
    return {
        "file": path,
        "n_points": len(x), "two_theta_range": [round(float(x[0]), 4), round(float(x[-1]), 4)],
        "step_deg": round(float(x[1] - x[0]), 6), "max_counts": float(y.max()),
        "file_timestamp": meta["file_timestamp"], "n_scans": meta["n_scans"],
        "halo_main": {"center_2theta": round(float(p[1]), 3), "fwhm_deg": round(float(p[2] + p[3]) / 2, 2),
                      "fwhm_left": round(float(p[2]), 2), "fwhm_right": round(float(p[3]), 2),
                      "d_A": round(lam / (2 * math.sin(th)), 4),
                      "q_invA": round(4 * math.pi * math.sin(th) / lam, 3),
                      "r1_ehrenfest_A": round(1.23 * lam / (2 * math.sin(th)), 3)},
        "halo_second": {"center_2theta": round(float(p[6]), 2), "fwhm_deg": round(float(p[7]), 2)},
        "reduced_chi2": round(chi2r, 3),
        "z_threshold": z_thr, "z_suspect": Z_SUSPECT, "z_max": round(float(z.max()), 2),
        "p_chance_of_z_max": round(det.null_pvalue(float(z.max())), 4),
        "z_max_at": round(float(x[np.argmax(z)]), 2),
        "peaks": peaks, "verdict": verdict,
        "detection_limit_counts": {str(c): round(det.min_height(c, z_thr), 1) for c in (44.67, 65.02, 82.33)},
        "broad_component_info": broad,
    }


if __name__ == "__main__":
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--inject", default="", help="예: 44.67:40,65.02:15")
    ap.add_argument("--inst-fwhm", type=float, default=0.15)
    a = ap.parse_args()
    inj = [tuple(map(float, s.split(":"))) for s in a.inject.split(",") if s] or None
    print(json.dumps(analyze(a.path, inj, a.inst_fwhm), ensure_ascii=False, indent=2))
