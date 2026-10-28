"""결과 문장 자동 생성."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xrdcheck.model import AnalysisResult


def format_p(p: float | None) -> str:
    if p is None:
        return "-"
    if p < 0.001:
        return "<0.1%"
    return f"{p * 100:.1f}%" if p < 0.1 else f"{p * 100:.0f}%"


def _peak_text(p) -> str:
    match = "/".join(p.matches) if p.matches else "매칭 없음"
    return f"{p.two_theta:.2f}° {match} z {p.z:.1f}"


def build_sentence(r: AnalysisResult) -> str:
    v = r.verdict.value
    if r.halo is None:
        return f"{v} — " + " ".join(r.reasons)
    halo = f"주 halo 2θ {r.halo.center:.2f}°(FWHM {r.halo.fwhm:.1f}°)."
    dl = ""
    if r.detection_limits:
        d0 = r.detection_limits[0]
        dl = f" 검출한계: {d0['label']} 위치 약 {d0['counts']:.0f} counts."
    counted = r.counted_peaks
    if r.verdict.name == "AMORPHOUS":
        return (f"{v} — {halo} 협폭 결정 피크 미검출(z최대 {r.z_max:.1f}, 우연확률 {format_p(r.p_chance)}).{dl}")
    peaks = ", ".join(_peak_text(p) for p in counted)
    nano = _nano_text(r)
    if r.verdict.name == "DETECTED":
        low = any(p.match_confidence == "낮음" for p in counted)
        tail = " 상 매칭 신뢰도 낮음(다른 강한 선 미검출) — 그래프 확인." if low else ""
        return f"{v} — 협폭 피크 {len(counted)}개: {peaks}. {halo}{nano}{tail}"
    return f"{v} — 협폭 피크 후보 {len(counted)}개: {peaks}. 그래프로 확인 필요. {halo}{nano}{dl}"


def _nano_text(r: AnalysisResult) -> str:
    n = r.nano
    if not n:
        return ""
    lo, hi = n["window"]
    if n["halo_peaks"]:
        where = ", ".join(f"{t:.2f}°" for t in n["halo_peaks"])
        size = ""
        if n.get("size"):
            from xrdcheck.analysis.nano import format_size

            s = n["size"]
            size = f" 결정립 크기 D ≈ {format_size(s)}(Scherrer, {s['label']} {s['two_theta']:.2f}°)."
        return f" {n['label']}(주 halo {lo:.1f}–{hi:.1f}° 위 피크 {where}).{size}"
    return f" {n['label']}(주 halo {lo:.1f}–{hi:.1f}°)."
