"""보정 검토 목록(Excel): 사용자가 실제 상태를 확인해야 할 시료를 유형별 시트로 나눈다.

    python tools/calib_review.py out/calibration
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

sys.path.insert(0, str(Path(__file__).parent))
from calib_report import fnum, heat_treated, load, series  # noqa: E402

COLS = ["시리즈", "열처리", "판정", "z최대", "z최대 위치(°)", "매칭", "halo 2θ", "halo FWHM", "최대 counts", "파일", "폴더",
        "실제 상태(입력)", "메모"]


def main(argv=None) -> int:
    root = Path((argv or sys.argv[1:])[0])
    seen, uniq = set(), []
    for r in load(root / "survey.csv"):
        if not r.get("error") and r["sha1"] not in seen:
            seen.add(r["sha1"])
            uniq.append(r)
    peaks = defaultdict(list)
    for p in load(root / "survey_peaks.csv"):
        peaks[p["sha1"]].append(p)

    def counted(r):
        return [p for p in peaks[r["sha1"]] if p["counted"] == "True"]

    groups = {
        "1_65도 단일 강한 피크": [r for r in uniq if r["verdict"] == "결정상 의심" and any(
            64.8 < fnum(p["two_theta"]) < 65.8 and fnum(p["z"]) >= 10 and p["confidence"] == "낮음" for p in counted(r))],
        "2_A·HA인데 결정상": [r for r in uniq if series(r["file"]) in ("A", "HA") and not heat_treated(r)
                          and r["verdict"] == "결정상 검출"],
        "3_X 열처리인데 비정질": [r for r in uniq if series(r["file"]) in ("X", "HX") and heat_treated(r)
                           and r["verdict"] == "비정질"],
        "4_석영 오염 감지": [r for r in uniq if (fnum(r["n_contam"]) or 0) > 0],
        "5_매칭 없는 피크로 판정": [r for r in uniq if r["verdict"] != "비정질" and counted(r)
                            and not any(p["confidence"] in ("높음", "보통") for p in counted(r))],
    }
    wb = Workbook()
    ws = wb.active
    ws.title = "설명"
    ws.append(["보정 검토 목록 — 시료마다 '실제 상태(입력)' 칸에 비정질 / 부분 결정 / 나노결정 / 산화 / 모름 중 하나를 적어 주세요."])
    ws.append([])
    for name, rows in groups.items():
        ws.append([name, f"{len(rows)}개"])
    ws.column_dimensions["A"].width = 40
    for name, rows in groups.items():
        sh = wb.create_sheet(name[:31])
        sh.append(COLS)
        for c in sh[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="ECEFF1")
        for r in sorted(rows, key=lambda r: fnum(r["z_max"]) or 0):
            sh.append([series(r["file"]), "예" if heat_treated(r) else "", r["verdict"], fnum(r["z_max"]),
                       fnum(r["z_max_at"]), r["matches"], fnum(r["halo_center"]), fnum(r["halo_fwhm"]),
                       fnum(r["max_counts"]), r["file"], r["folder"], "", ""])
        sh.freeze_panes = "A2"
        for col, w in zip("ABCDEFGHIJKLM", (7, 6, 11, 8, 10, 40, 8, 9, 10, 30, 50, 16, 20)):
            sh.column_dimensions[col].width = w
        sh.column_dimensions["L"].width = 16
        for c in sh["L"][1:]:
            c.fill = PatternFill("solid", fgColor="FFF9C4")
    out = root / "calib_review.xlsx"
    wb.save(out)
    for name, rows in groups.items():
        print(f"{name}: {len(rows)}개")
    print("저장:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
