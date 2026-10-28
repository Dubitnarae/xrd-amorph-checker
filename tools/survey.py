"""보정용 전수 조사: 폴더 아래의 모든 XRD 파일을 분석해 시료당 1행 CSV와 피크 CSV로 저장한다.

    python tools/survey.py <데이터 폴더> --out out/calibration [--workers 8]

원본 파일은 읽기만 한다. 같은 내용의 파일(폴더 간 복사본)은 내용 해시로 표시해 중복을 걸러낼 수 있게 한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

SUMMARY_COLS = [
    "path", "folder", "file", "sha1", "format", "verdict", "halo_center", "halo_fwhm", "halo_fwhm_l", "halo_fwhm_r",
    "eta1", "second_center", "chi2_red", "z_max", "z_max_at", "z_min", "z_min_at", "p_chance", "n_contam", "n_detect", "n_suspect", "matches",
    "dl_110", "broad_dbic", "broad_fwhm", "max_counts", "x0", "x1", "step", "n_points", "counting_time",
    "refit_rounds", "reasons", "warnings", "error",
]
PEAK_COLS = ["sha1", "file", "two_theta", "z", "level", "height", "fwhm", "counted", "contaminant", "matches",
             "confidence", "halo_center"]


def _analyze(path: str) -> tuple[dict, list[dict]]:
    from xrdcheck.analysis.pipeline import analyze_file

    p = Path(path)
    row = {"path": path, "folder": str(p.parent), "file": p.name,
           "sha1": hashlib.sha1(p.read_bytes()).hexdigest()[:16]}
    try:
        r = analyze_file(p)
    except Exception as e:  # noqa: BLE001 — 조사용: 실패도 기록
        row["error"] = f"{type(e).__name__}: {e}"
        return row, []
    pt, h = r.pattern, r.halo
    row.update({
        "format": pt.file_format, "verdict": r.verdict.value, "max_counts": pt.max_counts,
        "x0": round(float(pt.two_theta[0]), 3), "x1": round(float(pt.two_theta[-1]), 3),
        "step": round(pt.step_deg, 5), "n_points": pt.n_points, "counting_time": pt.counting_time_s,
        "refit_rounds": r.refit_rounds, "reasons": " / ".join(r.reasons), "warnings": " / ".join(r.warnings),
    })
    if h is not None:
        row.update({
            "halo_center": round(h.center, 3), "halo_fwhm": round(h.fwhm, 3), "halo_fwhm_l": round(h.fwhm_left, 3),
            "halo_fwhm_r": round(h.fwhm_right, 3), "eta1": round(h.param("eta1"), 3),
            "second_center": round(h.second_center, 2) if h.second_center else "",
            "chi2_red": round(h.chi2_red, 3), "z_max": round(r.z_max, 2), "z_max_at": round(r.z_max_at, 2),
            "p_chance": round(r.p_chance, 4),
            "z_min": round(float(r.z.min()), 2),  # 음의 쪽: 결정 피크와 무관 → 잡음·모델 오차만 반영
            "z_min_at": round(float(pt.two_theta[int(r.z.argmin())]), 2),
            "n_contam": sum(pk.contaminant for pk in r.peaks),
            "n_detect": sum(pk.significant for pk in r.counted_peaks),
            "n_suspect": sum(not pk.significant for pk in r.counted_peaks),
            "matches": ";".join(sorted({m for pk in r.counted_peaks for m in pk.matches})),
            "dl_110": next((round(d["counts"], 1) for d in r.detection_limits if d["label"] == "α-Fe(110)"), ""),
            "broad_dbic": round(r.broad["delta_bic"], 1) if r.broad else "",
            "broad_fwhm": round(r.broad["fwhm_deg"], 2) if r.broad else "",
        })
    peaks = [{"sha1": row["sha1"], "file": p.name, "two_theta": round(pk.two_theta, 3), "z": round(pk.z, 2),
              "level": pk.level, "height": round(pk.height, 1), "fwhm": round(pk.fwhm, 3), "counted": pk.counted,
              "contaminant": pk.contaminant, "matches": ";".join(pk.matches), "confidence": pk.match_confidence, "halo_center": row.get("halo_center", "")} for pk in r.peaks]
    return row, peaks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default="out/calibration")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--pattern", default="*.xrdml")
    a = ap.parse_args(argv)
    files = sorted(str(f) for f in Path(a.root).rglob(a.pattern) if f.is_file())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"파일 {len(files)}개 분석 시작 (작업자 {a.workers})", flush=True)
    t0 = time.time()
    rows, peaks = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(_analyze, f) for f in files]
        for k, fut in enumerate(as_completed(futs), 1):
            row, pk = fut.result()
            rows.append(row)
            peaks += pk
            if k % 100 == 0:
                print(f"  {k}/{len(files)} ({time.time() - t0:.0f} s)", flush=True)
    rows.sort(key=lambda r: r["path"])
    with (out / "survey.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, SUMMARY_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with (out / "survey_peaks.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, PEAK_COLS)
        w.writeheader()
        w.writerows(peaks)
    print(f"완료: {len(rows)}개, 오류 {sum(bool(r.get('error')) for r in rows)}개, {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
