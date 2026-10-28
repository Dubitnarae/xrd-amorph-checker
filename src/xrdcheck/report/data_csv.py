"""처리 데이터 CSV(utf-8-sig — Excel에서 한글이 깨지지 않게)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from xrdcheck.model import AnalysisResult


def write_processed_csv(r: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    p = r.pattern
    n = p.n_points
    nan = np.full(n, np.nan)
    comps = r.halo.components if r.halo else {}
    cols = {
        "2θ(°)": p.two_theta,
        "강도(counts)": p.counts,
        "모델": r.halo.mu if r.halo else nan,
        "배경": comps.get("배경", nan),
        "주 halo": comps.get("주 halo", nan),
        "제2 halo": comps.get("제2 halo", nan),
        "잔차": p.counts - r.halo.mu if r.halo else nan,
        "z": r.z if r.z is not None else nan,
        "검출한계(counts)": r.dl_curve if r.dl_curve is not None else nan,
        "피팅 사용": r.fit_mask.astype(int) if r.fit_mask is not None else nan,
    }
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"# {p.sample_name} | {r.verdict.value} | xrdcheck v{r.version}"])
        w.writerow(cols.keys())
        for i in range(n):
            w.writerow(["" if np.isnan(v[i]) else f"{v[i]:.6g}" for v in cols.values()])
    return path
