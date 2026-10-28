"""보정 평가: tools/survey.py 결과로 (1) 오경보 점검(음의 z), (2) 시리즈 목표 대비 판정 교차표를 만든다.

    python tools/calib_report.py out/calibration

시리즈 규칙(파일명 앞글자 A·X·HA·HX의 뜻)은 비공개 CLAUDE.md의 '시료 명명 규칙'을 본다.
파일명 'Al-…'은 'A1-…'의 오타로 보고 A 시리즈로 센다.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HEAT = re.compile(r"열처리|H\d{3}\b|H\d{3}(?=\D|$)|H-\d{3}|\d{3}-\d+H|ANNEAL|AFTER|CYCLE|싸이클|-CY", re.I)


AL_ALLOY = re.compile(r"^(?:\d+-)*AL(?:YNICO|-?\d*Y|-STF)", re.I)  # 진짜 Al계(halo 약 38.6°)


def series(name: str) -> str:
    s = name.upper().replace(" ", "")
    if AL_ALLOY.match(s):
        return "Al계"
    s = re.sub(r"^AL(?=[-_\dA-Z])", "A1", s)  # Al → A1 오타
    for key in ("HA", "HX"):
        if s.startswith(key):
            return key
    if re.match(r"^A\d", s):
        return "A"
    if re.match(r"^X\d", s):
        return "X"
    return "기타"


def heat_treated(row: dict) -> bool:
    return bool(HEAT.search(row["file"])) or "after" in row["folder"].lower()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    root = Path((argv or sys.argv[1:])[0])
    rows = [r for r in load(root / "survey.csv") if not r.get("error")]
    seen, uniq = set(), []
    for r in rows:
        if r["sha1"] not in seen:
            seen.add(r["sha1"])
            uniq.append(r)
    peaks = defaultdict(list)
    for p in load(root / "survey_peaks.csv"):
        peaks[p["sha1"]].append(fnum(p["two_theta"]))
    out = []
    say = out.append
    say(f"고유 시료 {len(uniq)}개 (전체 {len(rows)}개, 내용이 같은 복사본 제외)")

    # (1) 오경보 점검: 피크에서 1.5° 이상 떨어진 음의 z
    clean = [r for r in uniq if fnum(r["z_min"]) is not None
             and all(abs(fnum(r["z_min_at"]) - t) > 1.5 for t in peaks[r["sha1"]])]
    zmins = sorted(fnum(r["z_min"]) for r in clean)
    n = len(zmins)
    say("\n[오경보 점검] 음의 z(피크에서 1.5° 이상 떨어진 곳) — 결정 피크와 무관하므로 잡음·모델 오차만 반영")
    say(f"  대상 스캔 {n}개")
    for thr in (-3.5, -4.0, -4.5, -5.0, -6.0):
        k = sum(z <= thr for z in zmins)
        say(f"  z_min ≤ {thr:4.1f}: {k:4d}개 ({100 * k / max(n, 1):5.2f}%)")
    say("  기대(포아송, 이 측정 조건): z ≤ −4.5 약 1% 이하, z ≤ −5 약 0.1% 이하 — 음의 꼬리는 포아송 비대칭 때문에 양의 꼬리보다 가벼움")
    worst = sorted(clean, key=lambda r: fnum(r["z_min"]))[:8]
    say("  음의 z가 가장 큰 스캔: " + "; ".join(f"{r['file']}({r['z_min']} @ {r['z_min_at']}°)" for r in worst))

    # (2) 시리즈 × 판정
    say("\n[시리즈 목표 대비 판정] (열처리 표시는 파일명·폴더명 기준)")
    tab = defaultdict(Counter)
    for r in uniq:
        tab[(series(r["file"]), "열처리" if heat_treated(r) else "")][r["verdict"]] += 1
    verdicts = ["비정질", "결정상 의심", "결정상 검출", "판정 불가"]
    say(f"  {'시리즈':8s}{'':6s}" + "".join(f"{v:>10s}" for v in verdicts) + f"{'합계':>8s}")
    for key in sorted(tab):
        c = tab[key]
        say(f"  {key[0]:8s}{key[1]:6s}" + "".join(f"{c[v]:>10d}" for v in verdicts) + f"{sum(c.values()):>8d}")

    # (3) 판정 변화를 볼 수 있게 시료 목록 저장
    with (root / "calib_samples.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["시리즈", "열처리", "판정", "z최대", "z최대 위치", "매칭", "halo 2θ", "halo FWHM", "최대 counts",
                    "파일", "폴더", "실제 상태(사용자 입력)", "메모"])
        for r in sorted(uniq, key=lambda r: (series(r["file"]), r["verdict"], -(fnum(r["z_max"]) or 0))):
            w.writerow([series(r["file"]), "예" if heat_treated(r) else "", r["verdict"], r["z_max"], r["z_max_at"],
                        r["matches"], r["halo_center"], r["halo_fwhm"], r["max_counts"], r["file"], r["folder"], "", ""])
    text = "\n".join(out)
    (root / "calib_report.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
