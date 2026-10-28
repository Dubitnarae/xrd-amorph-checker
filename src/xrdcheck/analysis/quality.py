"""분석 전 품질 점검. 판정 불가 사유와 경고를 돌려준다."""

from __future__ import annotations

import numpy as np

from xrdcheck.model import Pattern


def check_quality(p: Pattern, settings: dict) -> tuple[list[str], list[str]]:
    """(판정 불가 사유 목록, 경고 목록)."""
    qs = settings["quality"]
    blockers, warnings = [], []
    lo, hi = qs["required_range_deg"]
    if p.n_points < 50:
        blockers.append(f"측정 점이 {p.n_points}개뿐입니다.")
        return blockers, warnings
    if p.two_theta[0] > lo or p.two_theta[-1] < hi:
        blockers.append(f"스캔 범위({p.two_theta[0]:.1f}–{p.two_theta[-1]:.1f}°)가 halo 영역 {lo:g}–{hi:g}°를 포함하지 않습니다.")
    if p.max_counts < qs["min_max_counts"]:
        blockers.append(f"최대 counts({p.max_counts:.0f})가 너무 낮습니다(기준 {qs['min_max_counts']}).")
    if np.any(p.counts < 0):
        warnings.append("음수 강도가 있습니다 — 배경을 뺀 데이터일 수 있어 통계 판정이 부정확할 수 있습니다.")
    steps = np.diff(p.two_theta)
    if steps.max() - steps.min() > 0.01 * np.median(steps):
        warnings.append("2θ 간격이 고르지 않습니다 — 정합 필터는 등간격을 가정하므로 결과를 그래프로 확인하세요.")
    return blockers, warnings
