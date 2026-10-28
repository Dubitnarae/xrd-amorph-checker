"""Phase 2: 분석 엔진 — 골든 테스트와 단위 테스트."""

import time
from pathlib import Path

import numpy as np
import pytest
from conftest import SAMPLE_STEM, SAMPLES

from xrdcheck.analysis.peaks import flag_kalpha2, kalpha2_offset_deg
from xrdcheck.analysis.phases import load_library, phase_lines
from xrdcheck.analysis.pipeline import analyze, analyze_file
from xrdcheck.analysis.profiles import gaussian, pseudo_voigt, pseudo_voigt_area
from xrdcheck.analysis.verdict import decide
from xrdcheck.io import load_pattern
from xrdcheck.model import Pattern, Peak, Verdict
from xrdcheck.settings import load_settings


@pytest.fixture(scope="module")
def sample_result():
    path = SAMPLES / f"{SAMPLE_STEM}.xrdml"
    if not path.exists():
        pytest.skip("샘플 파일 없음")
    return analyze_file(path)


# ---------------------------------------------------------------- 골든 테스트


def test_golden_halo(sample_result, expected):
    a = expected["analysis"]
    h = sample_result.halo
    assert h.center == pytest.approx(a["halo_main_center_2theta"]["value"], abs=a["halo_main_center_2theta"]["tol"])
    assert h.fwhm == pytest.approx(a["halo_main_fwhm_deg"]["value"], abs=a["halo_main_fwhm_deg"]["tol"])
    assert h.second_center == pytest.approx(a["halo_second_center_2theta"]["value"],
                                            abs=a["halo_second_center_2theta"]["tol"])
    assert h.chi2_red <= a["reduced_chi2_max"]


def test_golden_verdict(sample_result, expected):
    a = expected["analysis"]
    r = sample_result
    assert len([p for p in r.counted_peaks if p.significant]) == a["significant_narrow_peaks"]
    assert r.z_max < a["z_max_below"]
    assert r.verdict.value == a["verdict"]
    dl = {d["label"]: d["counts"] for d in r.detection_limits}
    exp = a["detection_limit_counts_at_44.67"]
    assert dl["α-Fe(110)"] == pytest.approx(exp["value"], abs=exp["tol"])


def test_golden_traceability(sample_result):
    """판정 결과에 근거 문장·z최대·검출한계·버전·설정이 함께 남는다."""
    r = sample_result
    assert r.sentence.startswith("비정질 — 주 halo 2θ 44.76°")
    assert "z최대" in r.sentence and "검출한계" in r.sentence
    assert r.version and r.settings["z_detect"] == 5.0
    assert 0 < r.p_chance <= 1
    assert r.broad is not None and r.broad["delta_bic"] > 0  # 참고값만, 판정에는 쓰지 않음


def test_analysis_under_3_seconds(sample_file):
    t = time.perf_counter()
    analyze_file(sample_file(".xrdml"))
    assert time.perf_counter() - t < 3.0


def test_csv_gives_same_result(sample_file, sample_result):
    r = analyze_file(sample_file(".csv"))
    assert r.verdict == sample_result.verdict
    assert r.halo.center == pytest.approx(sample_result.halo.center, abs=1e-6)


def test_big_peak_on_halo_apex_is_masked(sample_file):
    """큰 결정 피크가 halo 정점에 있어도 재피팅으로 halo가 끌려가지 않는다."""
    p = load_pattern(sample_file(".xrdml"))
    p.counts = p.counts + gaussian(p.two_theta, 500, 44.67, 0.15)
    r = analyze(p)
    assert r.refit_rounds >= 1
    assert not r.fit_mask[np.abs(p.two_theta - 44.67) < 0.2].any()
    assert r.halo.center == pytest.approx(44.76, abs=0.3)
    assert 6.5 < r.halo.fwhm < 8.0  # 가리지 않으면 5.6°까지 좁아짐
    assert any("정점 부근" in w for w in r.warnings)


# ---------------------------------------------------------------- 합성 데이터


def _synthetic(seed=1, x0=20.0, x1=90.0, scale=1.0):
    x = np.linspace(x0, x1, 2666)
    mu = scale * (15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10))
    y = np.random.default_rng(seed).poisson(mu).astype(float)
    return Pattern(two_theta=x, counts=y, source_path=Path("syn.xrdml"), file_format="xrdml",
                   sample_name="합성", counting_time_s=78.54)


def test_synthetic_amorphous():
    r = analyze(_synthetic())
    assert r.verdict == Verdict.AMORPHOUS
    assert r.halo.center == pytest.approx(44.8, abs=0.3)


def test_synthetic_with_peaks_detected():
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 60, 44.672, 0.15) + gaussian(p.two_theta, 30, 65.02, 0.15)
    r = analyze(p)
    assert r.verdict == Verdict.DETECTED
    labels = {m for pk in r.peaks for m in pk.matches}
    assert {"α-Fe(110)", "α-Fe(200)"} <= labels
    big = max(r.peaks, key=lambda pk: pk.height)
    assert big.height == pytest.approx(60, rel=0.3)
    assert big.fwhm == pytest.approx(0.15, abs=0.08)


def test_kalpha2_doublet_counted_once():
    """강한 피크 + 그 Kα2(절반 세기)는 피크 하나로 센다."""
    p = _synthetic()
    tt = 82.331
    ka2 = tt + kalpha2_offset_deg(tt, p.kalpha1_A, p.kalpha2_A)
    p.counts = p.counts + gaussian(p.two_theta, 200, tt, 0.15) + gaussian(p.two_theta, 100, ka2, 0.15)
    r = analyze(p)
    near = [pk for pk in r.peaks if abs(pk.two_theta - tt) < 1]
    assert sum(pk.counted for pk in near) == 1
    main = next(pk for pk in near if pk.counted)
    assert main.two_theta == pytest.approx(tt, abs=0.02)
    assert main.height == pytest.approx(200, rel=0.15)  # Kα1 높이
    assert main.fwhm == pytest.approx(0.15, abs=0.04)


def test_scan_without_halo_region_is_undetermined():
    r = analyze(_synthetic(x0=55, x1=90))
    assert r.verdict == Verdict.UNDETERMINED
    assert "halo 영역" in r.reasons[0]
    assert r.sentence.startswith("판정 불가")


def test_low_counts_is_undetermined():
    r = analyze(_synthetic(scale=0.1))
    assert r.verdict == Verdict.UNDETERMINED
    assert "최대 counts" in r.reasons[0]


def test_short_scan_omits_second_halo():
    r = analyze(_synthetic(x0=25, x1=65))
    assert r.halo.second_center is None
    assert "제2 halo" not in r.halo.components


def test_chi2_warning_not_undetermined():
    """모델과 안 맞는 긴 스캔이어도 판정 불가가 아니라 경고."""
    p = _synthetic(scale=100)
    p.counts = p.counts * (1 + 0.05 * np.sin(p.two_theta / 2))  # 모델이 못 따라가는 완만한 굴곡
    r = analyze(p)
    assert r.verdict != Verdict.UNDETERMINED
    assert any("모델 적합도 낮음" in w for w in r.warnings)


def test_settings_override_changes_threshold():
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 25, 61.0, 0.15)
    strict = analyze(p, load_settings(overrides={"z_detect": 50.0, "z_suspect": 40.0}))
    assert strict.verdict == Verdict.AMORPHOUS


# ---------------------------------------------------------------- 단위


def test_kalpha2_offset_matches_plan():
    """PLAN 1.2: 45°에서 약 0.12°, 82°에서 약 0.25°."""
    assert kalpha2_offset_deg(45, 1.540598, 1.544426) == pytest.approx(0.12, abs=0.01)
    assert kalpha2_offset_deg(82, 1.540598, 1.544426) == pytest.approx(0.25, abs=0.015)


def test_phase_lines_from_library():
    lines = {ln["label"]: ln["two_theta"] for ln in phase_lines(load_library(), 1.540598, 20, 90)}
    assert lines["α-Fe(110)"] == pytest.approx(44.67, abs=0.01)
    assert lines["α-Fe(200)"] == pytest.approx(65.02, abs=0.01)
    assert lines["α-Fe(211)"] == pytest.approx(82.33, abs=0.01)
    assert lines["Fe3O4(311)"] == pytest.approx(35.43, abs=0.01)


def _pk(tt, z, matches=(), sat=None, conf=None):
    return Peak(two_theta=tt, z=z, height=30, fwhm=0.15, area=5, level="검출" if z >= 5 else "의심",
                matches=list(matches), satellite_of=sat,
                match_confidence=conf if conf is not None else ("높음" if matches else ""))


@pytest.mark.parametrize(
    "peaks, verdict",
    [
        ([], Verdict.AMORPHOUS),
        ([_pk(44.67, 6, ["α-Fe(110)"])], Verdict.DETECTED),
        ([_pk(50, 6), _pk(61, 7)], Verdict.DETECTED),
        ([_pk(61, 19)], Verdict.SUSPECT),
        ([_pk(44.67, 4.7, ["α-Fe(110)"])], Verdict.SUSPECT),
        ([_pk(61, 7), _pk(61.2, 6, sat=61)], Verdict.SUSPECT),  # Kα2는 세지 않음
        ([_pk(65.5, 30, ["α-Fe(Si)(200)"], conf="낮음")], Verdict.SUSPECT),  # 최강선 없는 매칭은 불인정
        ([_pk(65.5, 30, ["α-Fe(Si)(200)"], conf="보통")], Verdict.DETECTED),
    ],
)
def test_verdict_rules(peaks, verdict):
    assert decide(peaks)[0] == verdict


def test_flag_kalpha2_ratio_check():
    s = load_settings()
    off = kalpha2_offset_deg(65, 1.540598, 1.544426)
    a = Peak(65, 9, 40, 0.15, 6, "검출")
    b = Peak(65 + off, 5, 20, 0.15, 3, "검출")
    flag_kalpha2([a, b], 1.540598, 1.544426, s)
    assert b.satellite_of == 65 and a.satellite_of is None
    c = Peak(65, 9, 40, 0.15, 6, "검출")
    d = Peak(65 + off, 5, 39, 0.15, 3, "검출")  # 세기 비가 안 맞으면 별개 피크
    flag_kalpha2([c, d], 1.540598, 1.544426, s)
    assert d.satellite_of is None


def test_pseudo_voigt_area():
    x = np.linspace(-200, 200, 400001)  # 로렌츠 꼬리까지 포함
    for eta in (0, 0.5, 1):
        num = np.trapezoid(pseudo_voigt(x, 3, 0, 0.2, eta), x)
        assert pseudo_voigt_area(3, 0.2, eta) == pytest.approx(num, rel=0.01)


# ---------------------------------------------------------------- Phase 4: 라이브러리 확장


def _bcc_tt(a, n, lam=1.540598):
    from xrdcheck.analysis.profiles import two_theta_from_d

    return two_theta_from_d(a / np.sqrt(n), lam)


def test_alpha_fe_si_range_match():
    """Si 고용 α-Fe(a = 2.840 Å)는 순수 α-Fe 허용오차 밖이지만 α-Fe(Si) 범위로 매칭된다."""
    p = _synthetic()
    for n, h in ((2, 80), (4, 25), (6, 30)):
        p.counts = p.counts + gaussian(p.two_theta, h, _bcc_tt(2.840, n), 0.15)
    r = analyze(p)
    assert r.verdict == Verdict.DETECTED
    labels = {m for pk in r.counted_peaks for m in pk.matches}
    assert {"α-Fe(Si)(110)", "α-Fe(Si)(200)", "α-Fe(Si)(211)"} <= labels
    assert "α-Fe(110)" not in labels  # 45.1°는 순수 α-Fe(44.67 ± 0.25°) 밖


def test_quartz_is_contaminant_not_crystallization():
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 40, 26.64, 0.15)
    r = analyze(p)
    assert r.verdict == Verdict.AMORPHOUS
    q = [pk for pk in r.peaks if pk.contaminant]
    assert q and "석영 SiO2(101)" in q[0].matches
    assert any("오염" in w for w in r.warnings)


def test_single_peak_without_strongest_line_is_suspect():
    """65.5°의 강한 단일 피크: α-Fe(Si)(200) 자리지만 (110)이 안 보이므로 매칭 불인정 → 의심."""
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 150, 65.5, 0.2)
    r = analyze(p)
    assert r.verdict == Verdict.SUSPECT
    pk = r.counted_peaks[0]
    assert pk.match_confidence == "낮음" and any("(110)" in n for n in pk.notes)


def test_library_validation_accepts_range_phase():
    from xrdcheck.gui.storage import default_library_text, validate_library_text

    assert validate_library_text(default_library_text()) is None
    bad = '{"phases": [{"name": "X", "cubic_a_range_A": [3, 2], "lines": [{"hkl": "110", "rel": 100}]}]}'
    assert "cubic_a_range_A" in validate_library_text(bad)


# ---------------------------------------------------------------- 나노결정 기준: 주 halo 위 피크(필요조건)


def test_nano_candidate_needs_peak_on_main_halo():
    p = _synthetic()
    for n, h in ((2, 60), (4, 15), (6, 20)):
        p.counts = p.counts + gaussian(p.two_theta, h, _bcc_tt(2.840, n), 0.3)
    r = analyze(p)
    assert r.verdict == Verdict.DETECTED
    assert r.nano["label"] == "나노결정 후보"
    lo, hi = r.nano["window"]
    assert lo < 45.1 < hi and any(abs(t - 45.1) < 0.2 for t in r.nano["halo_peaks"])
    assert "나노결정 후보" in r.sentence


def test_crystal_peaks_off_halo_are_not_nano():
    """주 halo 밖(65°대·82°대)에만 결정 피크가 있으면 결정상이어도 나노결정 아님."""
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 40, 65.02, 0.15) + gaussian(p.two_theta, 45, 82.33, 0.15)
    r = analyze(p)
    assert r.verdict == Verdict.DETECTED
    assert r.nano["label"].startswith("나노결정 아님")


def test_amorphous_has_no_nano_label(sample_result):
    assert sample_result.nano is None


# ---------------------------------------------------------------- Scherrer 결정립 크기


def _nano_pattern(size_nm, height=80, a=2.840, k=0.9):
    """크기를 아는 α-Fe(Si) 나노결정(Kα1+Kα2 쌍, 가우시안)을 합성 halo에 넣는다."""
    from xrdcheck.analysis.nano import instrument_fwhm

    p = _synthetic()
    s = load_settings()
    lam = p.kalpha1_A
    for n, rel in ((2, 1.0), (4, 0.2), (6, 0.3)):
        tt = _bcc_tt(a, n)
        beta = np.degrees(k * lam / (size_nm * 10 * np.cos(np.radians(tt / 2))))
        fw = float(np.hypot(beta, instrument_fwhm(tt, s)))
        dtt = kalpha2_offset_deg(tt, lam, p.kalpha2_A)
        p.counts = p.counts + gaussian(p.two_theta, height * rel, tt, fw) + gaussian(p.two_theta, 0.5 * height * rel, tt + dtt, fw)
    return p


@pytest.mark.parametrize("size_nm, height", [(8.0, 160), (10.0, 80), (15.0, 80), (30.0, 80)])
def test_scherrer_recovers_known_size(size_nm, height):
    """알려진 크기를 되찾는다. 8 nm(FWHM ≈ 1.1°)는 피크가 강할 때만 halo와 구분된다 — 6 nm 이하는 이 방법의 한계."""
    r = analyze(_nano_pattern(size_nm, height=height))
    assert r.nano["label"] == "나노결정 후보"
    s = r.nano["size"]
    assert s["limit"] == ""
    assert s["size_nm"] == pytest.approx(size_nm, rel=0.15)
    assert s["size_err_nm"] is not None and s["size_err_nm"] < 0.5 * size_nm
    assert "결정립 크기 D ≈" in r.sentence and "nm" in r.sentence


def test_scherrer_resolution_limit():
    """측정 폭이 기기 폭에 가까우면 '> ○ nm'로만 표시."""
    from xrdcheck.analysis.nano import format_size, scherrer

    s = load_settings()
    pk = Peak(45.1, 20, 100, 0.105, 10, "검출", matches=["α-Fe(Si)(110)"])
    out = scherrer(pk, 1.540598, s)
    assert out["limit"] == "분해능 한계(이상)" and format_size(out).startswith("> ")


def test_scherrer_value_by_hand():
    """D = Kλ/(β cosθ): 2θ = 45°, B = 0.6°, b = 0.10° → β = √(0.36 − 0.01)."""
    import math

    from xrdcheck.analysis.nano import scherrer

    s = load_settings()
    s["nanocrystal"]["scherrer_instrument_fwhm_deg"] = [[20, 0.10], [90, 0.10]]
    out = scherrer(Peak(45.0, 20, 100, 0.6, 10, "검출"), 1.540598, s)
    beta = math.radians(math.sqrt(0.6**2 - 0.1**2))
    assert out["size_nm"] == pytest.approx(0.9 * 1.540598 / (beta * math.cos(math.radians(22.5))) / 10, rel=1e-9)


def test_alloy_system_limits_phases():
    """Fe계 시료(halo 44.8°)에서는 38.5° 피크를 Al(111)로 매칭하지 않는다."""
    p = _synthetic()
    p.counts = p.counts + gaussian(p.two_theta, 40, 38.47, 0.15)
    r = analyze(p)
    assert r.alloy_system == "Fe계"
    assert not any(m.startswith("Al(") for pk in r.peaks for m in pk.matches)


def test_al_system_detected_and_warned():
    x = np.linspace(20, 90, 2666)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 38.5, 6.0) + gaussian(x, 10, 70, 10)
    y = np.random.default_rng(3).poisson(mu).astype(float)
    r = analyze(Pattern(two_theta=x, counts=y, source_path=Path("al.xrdml"), file_format="xrdml",
                        sample_name="Al", counting_time_s=78.54))
    assert r.alloy_system == "Al계"
    assert any("Al계" in w and "준비되지 않아" in w for w in r.warnings)
