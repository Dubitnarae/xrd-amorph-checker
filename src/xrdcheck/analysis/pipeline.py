"""분석 전체 흐름: 품질 점검 → halo 피팅 → 협폭 피크 검출(재피팅) → Kα2 → 상 매칭 → 판정 → 문장."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np

from xrdcheck import __version__
from xrdcheck.analysis.broad import broad_indicator
from xrdcheck.analysis.halo import HaloFitError, fit_halo
from xrdcheck.analysis.peaks import Doublet, NarrowDetector, detect_peaks, flag_kalpha2
from xrdcheck.analysis.phases import load_library, match_peaks, phase_lines
from xrdcheck.analysis.quality import check_quality
from xrdcheck.analysis.verdict import decide
from xrdcheck.io import load_pattern
from xrdcheck.model import AnalysisResult, Pattern, Verdict
from xrdcheck.report.text import build_sentence
from xrdcheck.settings import load_settings


def analyze_file(path: str | Path, settings: dict | None = None, library: list[dict] | None = None) -> AnalysisResult:
    settings = settings or load_settings()
    regex = settings.get("io", {}).get("filename_date_regex") or None
    return analyze(load_pattern(path, filename_regex=regex), settings, library)


def _detect(x, y, mu, doublet, settings):
    det = NarrowDetector(x, mu, settings)
    z, peaks = detect_peaks(x, y, mu, det, doublet, settings)
    return det, z, peaks


def analyze(pattern: Pattern, settings: dict | None = None, library: list[dict] | None = None) -> AnalysisResult:
    settings = settings or load_settings()
    library = library if library is not None else load_library()
    result = AnalysisResult(pattern=pattern, settings=settings, version=__version__,
                            analyzed_at=dt.datetime.now(), verdict=Verdict.UNDETERMINED,
                            warnings=list(pattern.warnings))
    blockers, warnings = check_quality(pattern, settings)
    result.warnings += warnings
    if blockers:
        result.reasons = blockers
        result.sentence = build_sentence(result)
        return result

    x, y, lam = pattern.two_theta, pattern.counts, pattern.kalpha1_A
    inst = settings["instrument_fwhm_deg"]
    k_mask = settings["refit"]["mask_fwhm_multiple"]
    doublet = Doublet(lam, pattern.kalpha2_A, pattern.kalpha2_ratio)
    mask = np.ones_like(x, dtype=bool)
    try:
        # 큰 결정 피크가 halo 피팅을 끌어당기지 않도록, 검출된 피크 주변을 가리고 다시 피팅(최대 N회)
        for rnd in range(settings["refit"]["max_rounds"] + 1):
            fit = fit_halo(x, y, lam, settings, mask)
            det, z, peaks = _detect(x, y, fit.mu, doublet, settings)
            new_mask = np.ones_like(mask)
            for p in peaks:
                if p.significant and p.counted:
                    half = k_mask * max(p.fwhm, inst)
                    tail = doublet.offset(p.two_theta)
                    new_mask &= (x < p.two_theta - half) | (x > p.two_theta + tail + half)  # Kα2 자리까지 가림
            if rnd == settings["refit"]["max_rounds"] or np.array_equal(new_mask, mask):
                break
            mask = new_mask
            result.refit_rounds = rnd + 1
    except HaloFitError as e:
        result.reasons = [str(e)]
        result.sentence = build_sentence(result)
        return result

    flag_kalpha2(peaks, lam, pattern.kalpha2_A, settings)
    lines = phase_lines(library, lam, float(x[0]), float(x[-1]))
    match_peaks(peaks, lines, settings, det.min_height)
    verdict, reasons = decide(peaks)

    result.halo, result.z, result.peaks, result.fit_mask = fit, z, peaks, mask
    result.verdict, result.reasons = verdict, reasons
    result.phase_lines = lines
    i_max = int(np.argmax(z))
    result.z_max, result.z_max_at = float(z[i_max]), float(x[i_max])
    result.p_chance = det.null_pvalue(result.z_max)
    result.dl_curve = det.limit_curve(settings["z_detect"])
    by_label = {ln["label"]: ln for ln in lines}
    for label in settings["detection_limit_lines"]:
        if label in by_label:
            tt = by_label[label]["two_theta"]
            h = det.min_height(tt, settings["z_detect"])
            if h is not None:
                result.detection_limits.append({"label": label, "two_theta": tt, "counts": h})

    broad_line = by_label.get(settings["broad_component"]["line"])
    if broad_line:
        result.broad = broad_indicator(x, y, fit, broad_line["two_theta"], lam, settings, mask)

    near_apex = np.abs(x - fit.center) <= fit.fwhm / 4
    if not mask[near_apex].all():
        result.warnings.append("결정 피크 때문에 halo 정점 부근을 빼고 피팅했습니다 — halo FWHM이 다소 크게 나올 수 있습니다.")
    if fit.chi2_red > settings["chi2_red_warn"]:
        result.warnings.append(f"모델 적합도 낮음(χ²red {fit.chi2_red:.2f}) — 그래프를 확인하세요.")
    if pattern.counting_time_s is None:
        result.warnings.append("계수시간 정보가 없습니다 — 강도를 counts로 가정했습니다.")
    result.sentence = build_sentence(result)
    return result
