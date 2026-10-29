"""오른쪽 결과 패널: 판정 문장, 수치, 검출한계, 피크, 넓은 성분(참고), 경고, 파일 정보."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QTextBrowser

from xrdcheck.model import AnalysisResult
from xrdcheck.report.figure import VERDICT_COLORS
from xrdcheck.report.text import format_p

CSS = """
<style>
body { font-family: 'Malgun Gothic'; font-size: 9pt; }
h2 { margin: 2px 0 6px 0; }
h3 { margin: 10px 0 3px 0; font-size: 9.5pt; color: #37474f; }
table { border-collapse: collapse; }
td, th { padding: 1px 6px; }
th { text-align: left; color: #546e7a; font-weight: normal; }
.num { text-align: right; }
.warn { color: #e65100; }
.muted { color: #78909c; }
</style>
"""


def _row(label: str, value) -> str:
    return f"<tr><th>{escape(label)}</th><td class='num'>{escape(str(value))}</td></tr>"


def _f(v, n, unit=""):
    return "-" if v is None else f"{v:.{n}f}{unit}"


def review_html(r: AnalysisResult, review: dict | None) -> str:
    out = []
    if review:
        ok = review["user_verdict"] == r.verdict.value
        color = "#2e7d32" if ok else "#c62828"
        out.append(f"<p style='color:{color}'><b>내 판정: {escape(review['user_verdict'])}</b> "
                   f"({'프로그램 판정과 같음' if ok else '프로그램 판정과 다름'}) "
                   f"<span class='muted'>검토 {escape(review['reviewed_at'][:10])}, 당시 v{escape(review['program_version'])}"
                   f" 판정 {escape(review['program_verdict'])}</span></p>")
        if review.get("memo"):
            out.append(f"<p class='muted'>메모: {escape(review['memo'])}</p>")
    if r.review_hints:
        out.append("<p><span style='color:#1565c0'><b>검토 추천</b></span> <span class='muted'>— 확인 후 아래 "
                   "[판정 맞음]/[판정 틀림]을 눌러 주세요</span></p><ul>"
                   + "".join(f"<li>{escape(h)}</li>" for h in r.review_hints) + "</ul>")
    return "".join(out)


def result_html(r: AnalysisResult, review: dict | None = None) -> str:
    p, h = r.pattern, r.halo
    v = r.verdict.value
    out = [CSS, f"<h2 style='color:{VERDICT_COLORS.get(v, '#000')}'>{escape(v)}</h2>",
           f"<p>{escape(r.sentence)}</p>"]
    if r.reasons:
        out.append("<p class='muted'>근거: " + escape(" / ".join(r.reasons)) + "</p>")
    out.append(review_html(r, review))
    if r.nano:
        lo, hi = r.nano["window"]
        out.append(f"<p><b>{escape(r.nano['label'])}</b> <span class='muted'>— 주 halo 범위 {lo:.1f}–{hi:.1f}°"
                   f"{', 피크 ' + ', '.join(f'{t:.2f}°' for t in r.nano['halo_peaks']) if r.nano['halo_peaks'] else ''}"
                   f" · {escape(r.nano['note'])}</span></p>")
        if r.nano.get("size"):
            from xrdcheck.analysis.nano import format_size

            s = r.nano["size"]
            out.append("<h3>결정립 크기 (Scherrer)</h3><table>")
            out.append(_row(f"D — {s['label']} {s['two_theta']:.2f}°", format_size(s)))
            out.append(_row("측정 FWHM / 기기 FWHM", f"{s['fwhm_obs']:.3f}° / {s['fwhm_inst']:.3f}°"))
            out += [_row(f"D — {o['label']} {o['two_theta']:.2f}°", format_size(o)) for o in r.nano["other_sizes"]]
            if r.nano.get("over_peaks"):
                out.append(_row("Scherrer 적용 범위 밖(크기 안 냄)", ", ".join(f"{t:.2f}°" for t in r.nano["over_peaks"])))
            if r.nano.get("xc") is not None:
                out.append(_row("결정 분율 Xc(참고)", f"{r.nano['xc'] * 100:.1f}%"))
            out.append("</table>")
        if r.nano.get("secondary_peaks"):
            out.append("<p class='muted'>2차 상 피크(붕화물·fcc 등, 나노결정 판단에서 제외): "
                       + escape(", ".join(f"{t:.2f}° {m}" for t, m in r.nano["secondary_peaks"])) + "</p>")

    if r.lattice:
        from xrdcheck.analysis.lattice import format_si

        lat = r.lattice
        out.append("<h3>격자상수 · Si 함량 (참고)</h3><table>")
        out.append(_row("a (bcc, 가중 평균)", f"{lat['a_A']:.4f} ± {lat['a_err_A']:.4f} Å"))
        out += [_row(f"  {u['label']} {u['two_theta']:.2f}°", f"{u['a_A']:.4f} Å") for u in lat["lines"]]
        if lat["a_extrap_A"] is not None:
            out.append(_row("a (높이 오차 외삽)", f"{lat['a_extrap_A']:.4f} Å"))
        out.append(_row("Si 함량 (Fe–Si 2원계 환산)", format_si(lat)))
        out.append("</table>")
        if lat["si_note"]:
            out.append(f"<p class='muted'>{escape(lat['si_note'])}</p>")
        out.append("<p class='muted'>2θ 영점·시료 높이 오차 0.02°가 약 0.5 at%에 해당합니다. Co·Ni·Al·P 등이 고용되면 맞지 않습니다.</p>")

    if h is not None:
        out.append("<h3>halo</h3><table>")
        out += [
            _row("주 halo 2θ", _f(h.center, 3, "°")),
            _row("FWHM (좌 / 우)", f"{h.fwhm:.2f}° ({h.fwhm_left:.2f} / {h.fwhm_right:.2f})"),
            _row("d / q", f"{h.d_A:.4f} Å / {h.q_invA:.3f} Å⁻¹"),
            _row("r₁ (1.23·d)", _f(h.r1_A, 3, " Å")),
            _row("제2 halo 2θ / FWHM",
                 f"{h.second_center:.2f}° / {h.second_fwhm:.2f}°" if h.second_center else "-"),
            _row("χ²red", _f(h.chi2_red, 3)),
        ]
        out.append("</table>")
        out.append("<h3>협폭 피크 통계</h3><table>")
        out += [_row("z최대 (위치)", f"{r.z_max:.2f} ({r.z_max_at:.2f}°)"),
                _row("우연확률", format_p(r.p_chance)),
                _row("재피팅 횟수", r.refit_rounds)]
        out.append("</table>")

    if r.detection_limits:
        out.append("<h3>검출한계 (z = %g)</h3><table>" % r.settings["z_detect"])
        out += [_row(f"{d['label']} {d['two_theta']:.2f}°", f"{d['counts']:.1f} counts") for d in r.detection_limits]
        out.append("</table>")

    if r.peaks:
        out.append("<h3>협폭 피크</h3><table><tr><th>2θ</th><th>z</th><th>높이</th><th>FWHM</th><th>매칭</th></tr>")
        for pk in r.peaks:
            style = "" if pk.counted else " class='muted'"
            match = ", ".join(pk.matches) or ("딸린 피크" if pk.satellite_of else "없음")
            if pk.contaminant:
                match += " — 오염·홀더(판정 제외)"
            if pk.match_confidence:
                match += f" ({pk.match_confidence})"
            out.append(f"<tr{style}><td class='num'>{pk.two_theta:.2f}</td><td class='num'>{pk.z:.1f}</td>"
                       f"<td class='num'>{pk.height:.0f}</td><td class='num'>{pk.fwhm:.3f}</td>"
                       f"<td>{escape(match)}</td></tr>")
            for note in pk.notes:
                out.append(f"<tr><td></td><td colspan='4' class='muted'>{escape(note)}</td></tr>")
        out.append("</table>")

    if r.broad:
        b = r.broad
        out.append("<h3>넓은 성분 지표 (참고 — 판정에 쓰지 않음)</h3><table>")
        out += [_row("ΔBIC", f"{b['delta_bic']:.1f}"), _row("중심 / FWHM", f"{b['center_2theta']:.2f}° / {b['fwhm_deg']:.2f}°"),
                _row("Scherrer (보정 전)", f"{b['scherrer_nm_uncorrected']:.1f} nm")]
        out.append("</table>")

    if r.warnings:
        out.append("<h3>경고</h3><ul>" + "".join(f"<li class='warn'>{escape(w)}</li>" for w in r.warnings) + "</ul>")

    out.append("<h3>파일</h3><table>")
    out += [
        _row("파일", p.source_path.name),
        _row("형식", p.file_format),
        _row("합금계(자동 판별)", r.alloy_system or "-"),
        _row("측정일", f"{p.measurement_date.isoformat()} ({p.date_source})" if p.measurement_date else "미정"),
        _row("점 / 간격", f"{p.n_points} / {p.step_deg:.4f}°"),
        _row("최대 counts", f"{p.max_counts:.0f}"),
        _row("계수시간", _f(p.counting_time_s, 2, " s")),
        _row("Kα1", f"{p.kalpha1_A:.6f} Å"),
        _row("프로그램", f"xrdcheck v{r.version}"),
    ]
    out.append("</table>")
    return "".join(out)


class DetailPanel(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.clear_result()

    def clear_result(self) -> None:
        self.setHtml(CSS + "<p class='muted'>목록에서 시료를 고르면 판정 근거가 여기에 나옵니다.</p>")

    def set_result(self, r: AnalysisResult, review: dict | None = None) -> None:
        self.setHtml(result_html(r, review))

    def set_compare(self, results: list[AnalysisResult]) -> None:
        rows = "".join(
            f"<tr><td>{escape(r.pattern.sample_name)}</td>"
            f"<td style='color:{VERDICT_COLORS.get(r.verdict.value, '#000')}'>{escape(r.verdict.value)}</td>"
            f"<td class='num'>{_f(r.halo.center if r.halo else None, 2)}</td>"
            f"<td class='num'>{_f(r.halo.fwhm if r.halo else None, 2)}</td>"
            f"<td class='num'>{_f(r.z_max, 1)}</td></tr>" for r in results)
        self.setHtml(CSS + f"<h2>시료 비교 ({len(results)}개)</h2><table><tr><th>시료</th><th>판정</th>"
                     f"<th>halo 2θ</th><th>FWHM</th><th>z최대</th></tr>{rows}</table>")
