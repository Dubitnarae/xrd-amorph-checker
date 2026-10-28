"""halo 모양 오차로 인한 가짜 검출 모의실험.

PV(최대 로렌츠)보다 뾰족한 halo(Pearson VII, m < 1)를 결정 피크 없이 만들고 포아송 잡음을 넣어
분석했을 때, 정점 근처에서 '의심/검출'이 얼마나 나오는지 센다.

    python tools/apex_sim.py --n 200
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np


def pearson7(x, h, c, w, m):
    return h * (1 + (2 ** (1 / m) - 1) * (2 * (x - c) / w) ** 2) ** (-m)


def one(args):
    from xrdcheck.analysis.pipeline import analyze
    from xrdcheck.model import Pattern

    m, scale, seed = args
    x = np.linspace(20, 90, 2666)
    rng = np.random.default_rng(seed)
    fwhm = rng.uniform(4.5, 7.0)
    mu = scale * (15 + 45 * np.exp(-(x - 20) / 8) + pearson7(x, 55, 44.8, fwhm, m) + pearson7(x, 10, 80, 10, 1.5))
    y = rng.poisson(mu).astype(float)
    p = Pattern(two_theta=x, counts=y, source_path=Path("sim.xrdml"), file_format="xrdml", sample_name="sim",
                counting_time_s=78.54)
    r = analyze(p)
    near = [pk for pk in r.counted_peaks if abs(pk.two_theta - 44.8) < 1.0]
    return m, scale, r.verdict.value, bool(near), r.halo.param("eta1") if r.halo else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    jobs = [(m, s, 1000 * i + int(m * 100) + int(s)) for m in (2.0, 1.0, 0.8, 0.6) for s in (1, 3) for i in range(a.n)]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, jobs, chunksize=8))
    print("m(1=로렌츠, 작을수록 뾰족)  계수배율  판정 분포  정점±1° 피크 비율  η=1 비율")
    for m in (2.0, 1.0, 0.8, 0.6):
        for s in (1, 3):
            g = [r for r in res if r[0] == m and r[1] == s]
            c = Counter(r[2] for r in g)
            print(f"  m={m:<4} ×{s}  {dict(c)}  {sum(r[3] for r in g) / len(g):.1%}  "
                  f"{sum((r[4] or 0) > 0.99 for r in g) / len(g):.0%}")


if __name__ == "__main__":
    main()
