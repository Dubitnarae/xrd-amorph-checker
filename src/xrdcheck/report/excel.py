"""Excel 보고서: 요약(시료당 1행) · 피크 · 설정·버전."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from xrdcheck import __version__
from xrdcheck.model import AnalysisResult
from xrdcheck.report.text import format_p
from xrdcheck.settings import flatten

VERDICT_FILL = {"비정질": "C8E6C9", "결정상 의심": "FFE0B2", "결정상 검출": "FFCDD2", "나노결정상 후보": "E1BEE7",
                "판정 불가": "E0E0E0"}
HEADER_FILL = PatternFill("solid", fgColor="ECEFF1")


def _r(v, n):
    return None if v is None else round(float(v), n)


def _dl(r: AnalysisResult, label: str):
    for d in r.detection_limits:
        if d["label"] == label:
            return _r(d["counts"], 1)
    return None


def _size_cols(r: AnalysisResult) -> dict:
    """나노결정 후보의 Scherrer 결정립 크기(nm)."""
    from xrdcheck.analysis.nano import format_size

    s = (r.nano or {}).get("size")
    others = (r.nano or {}).get("other_sizes", [])
    return {
        "결정립 크기 D(nm)": _r(s["size_nm"], 1) if s and s["size_nm"] is not None and not s["limit"] else None,
        "D 오차(nm)": _r(s["size_err_nm"], 1) if s and s["size_err_nm"] is not None and not s["limit"] else None,
        "D 표기": format_size(s) if s else "",
        "D 근거 피크": f"{s['label']} {s['two_theta']:.2f}° (FWHM {s['fwhm_obs']:.3f}°, 기기 {s['fwhm_inst']:.3f}°)" if s else "",
        "다른 선 D": "; ".join(f"{o['label']} {format_size(o)}" for o in others),
        "결정 분율 Xc(%, 참고)": _r((r.nano or {})["xc"] * 100, 1) if (r.nano or {}).get("xc") is not None else None,
    }


def _lattice_cols(r: AnalysisResult) -> dict:
    lat = r.lattice or {}
    return {
        "격자상수 a(Å, 참고)": _r(lat.get("a_A"), 4),
        "a 오차(Å)": _r(lat.get("a_err_A"), 4),
        "a 외삽(Å)": _r(lat.get("a_extrap_A"), 4),
        "Si 함량(at%, 참고)": _r(lat.get("si_at"), 1),
        "Si 오차(at%)": _r(lat.get("si_err_at"), 1),
        "격자상수 근거 피크": "; ".join(f"{u['label']} {u['two_theta']:.2f}°" for u in lat.get("lines", [])),
    }


def summary_row(r: AnalysisResult, dl_labels: list[str], reviews=None) -> dict:
    p, h, b = r.pattern, r.halo, r.broad or {}
    counted = r.counted_peaks
    row = {
        "파일": p.source_path.name,
        "시료명": p.sample_name,
        "측정일": p.measurement_date.isoformat() if p.measurement_date else "",
        "측정일 근거": p.date_source,
        "합금계": r.alloy_system,
        "판정": r.verdict.value,
        "나노결정": (r.nano or {}).get("label", ""),
        **_size_cols(r),
        **_lattice_cols(r),
        "결과 문장": r.sentence,
        "주 halo 2θ(°)": _r(h.center, 3) if h else None,
        "FWHM(°)": _r(h.fwhm, 2) if h else None,
        "FWHM 좌(°)": _r(h.fwhm_left, 2) if h else None,
        "FWHM 우(°)": _r(h.fwhm_right, 2) if h else None,
        "d(Å)": _r(h.d_A, 4) if h else None,
        "q(1/Å)": _r(h.q_invA, 3) if h else None,
        "r1(Å)": _r(h.r1_A, 3) if h else None,
        "제2 halo 2θ(°)": _r(h.second_center, 2) if h else None,
        "제2 halo FWHM(°)": _r(h.second_fwhm, 2) if h else None,
        "χ²red": _r(h.chi2_red, 3) if h else None,
        "z최대": _r(r.z_max, 2),
        "z최대 위치(°)": _r(r.z_max_at, 2),
        "우연확률": format_p(r.p_chance) if r.p_chance is not None else "",
        "검출 피크 수": sum(pk.significant for pk in counted),
        "의심 피크 수": sum(not pk.significant for pk in counted),
        "매칭 상": ", ".join(sorted({m for pk in counted for m in pk.matches})),
    }
    for label in dl_labels:
        row[f"검출한계 {label}(counts)"] = _dl(r, label)
    row.update({
        "넓은 성분 ΔBIC(참고)": _r(b.get("delta_bic"), 1),
        "넓은 성분 FWHM(°)(참고)": _r(b.get("fwhm_deg"), 2),
        "넓은 성분 Scherrer(nm, 보정 전)": _r(b.get("scherrer_nm_uncorrected"), 1),
        "최대 counts": _r(p.max_counts, 0),
        "점 개수": p.n_points,
        "재피팅 횟수": r.refit_rounds,
        "판정 근거": " / ".join(r.reasons),
        "검토 추천 이유": " / ".join(r.review_hints),
        "경고": " / ".join(r.warnings),
        "원본 경로": str(p.source_path),
    })
    if reviews is not None:
        rv = reviews.get(r) or {}
        row["내 판정"] = rv.get("user_verdict", "")
        row["판정 일치"] = ("O" if rv["user_verdict"] == r.verdict.value else "X") if rv else ""
        row["검토 메모"] = rv.get("memo", "")
    return row


PEAK_COLUMNS = ["파일", "시료명", "2θ(°)", "z", "단계", "높이(counts)", "FWHM(°)", "면적", "d(Å)",
                "매칭", "매칭 신뢰도", "판정 제외 사유", "국소 피팅", "비고"]


def _write_table(ws, columns: list[str], rows: list[list]) -> None:
    ws.append(columns)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    for i, col in enumerate(columns, 1):
        width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows if r[i - 1] is not None][:200])
        ws.column_dimensions[get_column_letter(i)].width = min(max(8, width * 1.3), 60)


def write_excel(results: list[AnalysisResult], path: str | Path, reviews=None) -> Path:
    from xrdcheck.analysis.profiles import d_spacing

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    settings = results[0].settings if results else {}
    dl_labels = settings.get("detection_limit_lines", [])

    ws = wb.active
    ws.title = "요약"
    rows = [summary_row(r, dl_labels, reviews) for r in results]
    columns = list(rows[0].keys()) if rows else ["파일"]
    _write_table(ws, columns, [list(r.values()) for r in rows])
    vcol = columns.index("판정") + 1 if "판정" in columns else None
    if vcol:
        for i, r in enumerate(results, 2):
            ws.cell(i, vcol).fill = PatternFill("solid", fgColor=VERDICT_FILL.get(r.verdict.value, "FFFFFF"))
    if "결과 문장" in columns:
        ws.column_dimensions[get_column_letter(columns.index("결과 문장") + 1)].width = 80

    wp = wb.create_sheet("피크")
    peak_rows = []
    for r in results:
        for pk in r.peaks:
            peak_rows.append([
                r.pattern.source_path.name, r.pattern.sample_name, _r(pk.two_theta, 3), _r(pk.z, 2), pk.level,
                _r(pk.height, 1), _r(pk.fwhm, 3), _r(pk.area, 2), _r(d_spacing(pk.two_theta, r.pattern.kalpha1_A), 4),
                ", ".join(pk.matches), pk.match_confidence, (f"{pk.satellite_of:.2f}° 피크에 딸림" if pk.satellite_of else "오염·홀더 상(판정 제외)" if pk.contaminant else ""),
                "성공" if pk.refined else "실패", " / ".join(pk.notes),
            ])
    _write_table(wp, PEAK_COLUMNS, peak_rows)

    wsv = wb.create_sheet("설정·버전")
    info = [("프로그램", "XRD 비정질 판정 도우미 (xrdcheck)"), ("버전", __version__),
            ("보고서 작성", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), ("시료 수", len(results))]
    _write_table(wsv, ["항목", "값"], [list(i) for i in info] + [[k, str(v)] for k, v in flatten(settings)])
    wb.save(path)
    return path


def write_review_excel(store, results: list[AnalysisResult], path: str | Path) -> Path:
    """검토 기록(저장된 전체)과 혼동표(목록의 지금 판정 기준)를 Excel로 저장한다."""
    from xrdcheck.review import VERDICTS, confusion

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "검토 기록"
    now = {}
    for r in results:
        if (e := store.get(r)) is not None:
            now[id(e)] = r.verdict.value
    cols = ["파일", "내 판정", "검토 당시 판정", "검토 당시 버전", "목록의 지금 판정", "메모", "검토 일시", "파일 해시", "경로"]
    rows = [[e["file"], e["user_verdict"], e["program_verdict"], e["program_version"], now.get(id(e), ""),
             e.get("memo", ""), e["reviewed_at"], k, e["path"]] for k, e in sorted(store.data.items(), key=lambda kv: kv[1]["file"])]
    _write_table(ws, cols, rows)
    wc = wb.create_sheet("혼동표")
    c = confusion(store, results)
    wc.append(["내 판정(행) × 프로그램 판정(열)"] + VERDICTS)
    for u in VERDICTS:
        wc.append([u] + [c["matrix"][u][p] or None for p in VERDICTS])
    for i in range(len(VERDICTS)):
        cell = wc.cell(i + 2, i + 2)
        cell.fill = PatternFill("solid", fgColor="C8E6C9")
    wc.append([])
    wc.append(["검토 수", c["n"]])
    wc.append(["정확도", None if c["accuracy"] is None else round(c["accuracy"] * 100, 1)])
    wc.column_dimensions["A"].width = 28
    wb.save(path)
    return path
