"""v0.8.0: Rigaku .rasx 읽기, 격자상수·Si 함량, 2차 상 카드, 판정 검토(맞음/틀림)."""

import datetime as dt
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

from xrdcheck.analysis.lattice import estimate_lattice, si_from_a
from xrdcheck.analysis.phases import load_library, match_peaks, phase_lines
from xrdcheck.analysis.pipeline import analyze
from xrdcheck.analysis.profiles import gaussian, two_theta_from_d
from xrdcheck.io import load_pattern
from xrdcheck.io.base import date_from_folder
from xrdcheck.io.rasx import RasxError, read_rasx
from xrdcheck.model import Pattern, Peak, Verdict
from xrdcheck.review import ReviewStore, confusion, review_hints, status_text
from xrdcheck.settings import load_settings

LAM = 1.540598

# ---------------------------------------------------------------- .rasx

COND = """\ufeff<?xml version="1.0" encoding="utf-8"?>
<MeasurementConditions>
  <GeneralInformation><SampleName>1</SampleName><SystemName>SmartLab</SystemName><Comment /><Memo /></GeneralInformation>
  <HWConfigurations><XrayGenerator><TargetName>Cu</TargetName><Voltage>40</Voltage><Current>50</Current>
    <WavelengthKalpha1>1.540593</WavelengthKalpha1><WavelengthKalpha2>1.544414</WavelengthKalpha2></XrayGenerator>
  </HWConfigurations>
  <ScanInformation><AxisName>TwoThetaTheta</AxisName><Mode>CONTINUOUS</Mode><Start>20.0000</Start><Stop>90.0000</Stop>
    <Step>{step}</Step><Speed>5.0000</Speed><SpeedUnit>deg/min</SpeedUnit><IntensityUnit>{unit}</IntensityUnit>
    <StartTime>2026-02-25T05:34:18Z</StartTime></ScanInformation>
</MeasurementConditions>"""


def _write_rasx(path: Path, x, y, att=None, unit="counts", step=0.01, extra_data=False, cond=True):
    att = np.ones_like(x) if att is None else att
    prof = "\ufeff" + "\n".join(f"{a:.4f}\t{b:.6f}\t{c:g}" for a, b, c in zip(x, y, att))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Data0/Profile0.txt", prof.encode("utf-8"))
        if cond:
            z.writestr("Data0/MesurementConditions0.xml", COND.format(step=step, unit=unit).encode("utf-8"))
        if extra_data:
            z.writestr("Data1/Profile0.txt", prof.encode("utf-8"))
        z.writestr("root.xml", "<Root />")
    return path


def test_rasx_reads_profile_and_conditions(tmp_path):
    x = np.round(np.arange(20, 90.0001, 0.01), 4)
    y = 100 + 50 * np.exp(-((x - 44.5) / 3) ** 2)
    p = read_rasx(_write_rasx(tmp_path / "RX_1_01_20260225_000000_001.rasx", x, y))
    assert p.file_format == "rasx" and p.n_points == len(x)
    assert p.kalpha1_A == pytest.approx(1.540593) and p.kalpha2_A == pytest.approx(1.544414)
    assert p.counting_time_s == pytest.approx(0.12)  # 0.01° ÷ 5°/min × 60
    assert p.meta["sample_id"] == "1" and p.sample_name.startswith("RX_1_01")
    assert p.counts.max() == pytest.approx(150, abs=0.01)


def test_rasx_attenuator_factor_and_date(tmp_path):
    x = np.round(np.arange(20, 90.0001, 0.02), 4)
    y = np.full_like(x, 10.0)
    att = np.where(x > 44, 100.0, 1.0)
    p = load_pattern(_write_rasx(tmp_path / "S_20260225.rasx", x, y, att))
    assert p.counts[-1] == pytest.approx(1000) and p.counts[0] == pytest.approx(10)
    assert any("감쇠" in w for w in p.warnings)
    assert p.measurement_date == dt.date(2026, 2, 25) and p.date_source == "파일명"
    assert not any("비정상" in w for w in p.warnings)  # 내부 시각(2026)과 파일명 날짜가 같음


def test_rasx_cps_converted_and_multiple_data_warns(tmp_path):
    x = np.round(np.arange(20, 90.0001, 0.01), 4)
    p = read_rasx(_write_rasx(tmp_path / "a.rasx", x, np.full_like(x, 50.0), unit="cps", extra_data=True))
    assert p.counts[0] == pytest.approx(50 * 0.12)
    assert any("첫 번째" in w for w in p.warnings)


def test_rasx_bad_files(tmp_path):
    bad = tmp_path / "bad.rasx"
    bad.write_text("not a zip")
    with pytest.raises(RasxError):
        read_rasx(bad)
    x = np.round(np.arange(20, 90.0001, 0.01), 4)
    p = read_rasx(_write_rasx(tmp_path / "nocond.rasx", x, np.full_like(x, 5.0), cond=False))
    assert p.kalpha1_A == pytest.approx(LAM) and any("측정 조건" in w for w in p.warnings)


def test_year_folder_with_korean_suffix():
    assert date_from_folder(r"C:\XRD\2025년\0725-XRD\a.rasx") == dt.date(2025, 7, 25)


# ---------------------------------------------------------------- 격자상수 · Si

def test_si_calibration_matches_literature_points():
    table = load_settings()["lattice"]["si_calibration"]
    assert si_from_a(2.8665, table)[0] == pytest.approx(0, abs=0.01)
    assert si_from_a(2.8431, table)[0] == pytest.approx(16.25, abs=0.6)  # FINEMET 문헌 표 값
    assert si_from_a(2.8479, table)[0] == pytest.approx(14.6, abs=0.8)
    assert si_from_a(2.8400, table)[0] == pytest.approx(18, abs=0.01)
    assert si_from_a(2.880, table)[0] is None  # 순수 Fe보다 큼 → 범위 밖
    assert si_from_a(2.80, table)[0] is None


def _bcc_pattern(a: float, seed=3) -> Pattern:
    x = np.linspace(20, 90, 3500)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10)
    for n, h in ((2, 300), (4, 60), (6, 100)):
        tt = two_theta_from_d(a / math.sqrt(n), LAM)
        mu = mu + gaussian(x, h, tt, 0.35)
    y = np.random.default_rng(seed).poisson(mu).astype(float)
    return Pattern(two_theta=x, counts=y, source_path=Path("bcc.xrdml"), file_format="xrdml", sample_name="bcc",
                   counting_time_s=78.54, kalpha2_A=None, kalpha2_ratio=None)


def test_lattice_and_si_from_synthetic_bcc():
    r = analyze(_bcc_pattern(2.8431))
    lat = r.lattice
    assert lat is not None and len(lat["lines"]) == 3
    assert lat["a_A"] == pytest.approx(2.8431, abs=0.0015)
    assert lat["a_extrap_A"] == pytest.approx(2.8431, abs=0.003)
    assert lat["si_at"] == pytest.approx(16.4, abs=1.0)
    assert lat["si_err_at"] > 0


def test_no_lattice_for_amorphous():
    x = np.linspace(20, 90, 2666)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10)
    p = Pattern(two_theta=x, counts=np.random.default_rng(1).poisson(mu).astype(float), source_path=Path("a.xrdml"),
                file_format="xrdml", sample_name="a", counting_time_s=78.54)
    r = analyze(p)
    assert r.verdict == Verdict.AMORPHOUS and r.lattice is None and estimate_lattice(r, r.settings) is None


# ---------------------------------------------------------------- 2차 상 카드

def _match(positions_heights, dl=5.0):
    s = load_settings()
    lines = phase_lines(load_library(), LAM, 20, 90, "Fe")
    peaks = [Peak(two_theta=t, z=20, height=h, fwhm=0.2, area=1, level="검출") for t, h in positions_heights]
    match_peaks(peaks, lines, s, lambda tt, z: dl, LAM)
    return peaks


def test_library_has_secondary_phases_with_sources():
    lib = {ph["name"]: ph for ph in load_library()}
    for name in ("Fe2B", "(Fe,Nb)23B6", "Fe3B(t)", "Fe3C", "Fe5PB2", "Fe2P", "fcc(γ-Fe/Cu)", "Fe3O4"):
        assert lib[name]["role"] == "secondary" and lib[name]["source"]
    assert "COD" in lib["Fe2B"]["source"]


def test_alpha_fe_peak_not_taken_by_boride():
    """45° α-Fe(Si)(110) 피크는 Fe2B(211)에도 걸리지만 기본 상으로 설명되면 2차 상으로 다시 해석하지 않는다."""
    peaks = _match([(44.9, 400), (65.3, 60), (82.7, 110)])
    assert all(not any(m.startswith(("Fe2B", "Fe3C", "Fe3B")) for m in p.matches) for p in peaks)
    assert all(any(m.startswith("α-Fe") for m in p.matches) for p in peaks)


def test_boride_peaks_matched_when_alone():
    d = {ln["hkl"]: ln["d_A"] for ln in next(ph for ph in load_library() if ph["name"] == "Fe3B(t)")["lines"]}
    tts = [two_theta_from_d(d[h], LAM) for h in ("321", "411", "301")]
    peaks = _match([(tts[0], 100), (tts[1], 77), (tts[2], 34)])
    assert all(any(m.startswith("Fe3B(t)") for m in p.matches) and p.accepted_match for p in peaks)


def test_fcc_pair_from_lattice_range():
    a = 3.596  # 실측 43.57°/50.70° 쌍
    peaks = _match([(two_theta_from_d(a / math.sqrt(3), LAM), 70), (two_theta_from_d(a / 2, LAM), 33)], dl=40)
    assert all(any(m.startswith("fcc") for m in p.matches) for p in peaks)


def test_secondary_peak_on_halo_not_nanocrystal():
    """주 halo 위 피크가 2차 상에만 매칭되면 나노결정상 후보로 보지 않는다."""
    x = np.linspace(20, 90, 3500)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10)
    a = 3.596
    for tt, h in ((two_theta_from_d(a / math.sqrt(3), LAM), 60), (two_theta_from_d(a / 2, LAM), 28)):
        mu = mu + gaussian(x, h, tt, 0.3)
    p = Pattern(two_theta=x, counts=np.random.default_rng(2).poisson(mu).astype(float), source_path=Path("f.xrdml"),
                file_format="xrdml", sample_name="f", counting_time_s=78.54, kalpha2_A=None, kalpha2_ratio=None)
    r = analyze(p)
    assert r.verdict == Verdict.DETECTED
    assert r.nano["secondary_peaks"] and not r.nano["in_range"]


# ---------------------------------------------------------------- 검토

class _R:
    """검토 저장 시험용 최소 결과."""

    def __init__(self, path: Path, verdict=Verdict.NANO):
        self.pattern = Pattern(two_theta=np.zeros(2), counts=np.zeros(2), source_path=path, file_format="xrdml",
                               sample_name=path.stem)
        self.verdict = verdict
        self.nano = {"label": "나노결정상 후보"}


def test_review_store_roundtrip_by_content(tmp_path):
    f = tmp_path / "a.xrdml"
    f.write_bytes(b"same content")
    st = ReviewStore(tmp_path)
    r = _R(f)
    e = st.set(r, "결정상 검출", memo="붕화물 같음")
    assert e["program_verdict"] == "나노결정상 후보" and e["user_verdict"] == "결정상 검출"
    moved = tmp_path / "sub" / "renamed.xrdml"  # 옮기고 이름을 바꿔도 내용이 같으면 이어진다
    moved.parent.mkdir()
    moved.write_bytes(b"same content")
    st2 = ReviewStore(tmp_path)
    assert st2.get(_R(moved))["memo"] == "붕화물 같음"
    assert status_text(r, st2.get(r), []) == "✗ → 결정상 검출"
    st2.set(r, "나노결정상 후보")
    assert status_text(r, st2.get(r), []) == "✓ 맞음" and st2.get(r)["memo"] == "붕화물 같음"
    st2.remove(r)
    assert ReviewStore(tmp_path).get(r) is None
    with pytest.raises(ValueError):
        st2.set(r, "없는 판정")


def test_broken_review_file_is_kept_aside(tmp_path):
    (tmp_path / "reviews.json").write_text("{깨짐", encoding="utf-8")
    st = ReviewStore(tmp_path)
    assert st.data == {} and (tmp_path / "reviews.broken.json").exists()


def test_confusion_matrix(tmp_path):
    st = ReviewStore(tmp_path)
    rs = []
    for i, (prog, user) in enumerate([(Verdict.NANO, "나노결정상 후보"), (Verdict.NANO, "결정상 검출"),
                                      (Verdict.AMORPHOUS, "비정질")]):
        f = tmp_path / f"{i}.xrdml"
        f.write_bytes(str(i).encode())
        r = _R(f, prog)
        st.set(r, user)
        rs.append(r)
    c = confusion(st, rs)
    assert c["n"] == 3 and c["correct"] == 2 and c["accuracy"] == pytest.approx(2 / 3)
    assert c["matrix"]["결정상 검출"]["나노결정상 후보"] == 1
    assert c["disagree"] == [("1.xrdml", "나노결정상 후보", "결정상 검출", "")]
    rs[1].verdict = Verdict.DETECTED  # 기준을 고쳐 지금 판정이 바뀌면 지금 기준 정확도가 오른다
    assert confusion(st, rs)["accuracy"] == 1.0
    assert confusion(st)["accuracy"] == pytest.approx(2 / 3)  # 저장된 '검토 당시' 기준은 그대로


def test_review_hints_for_borderline_and_single_65():
    x = np.linspace(20, 90, 2666)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10)
    mu = mu + gaussian(x, 60, 65.1, 0.15)
    p = Pattern(two_theta=x, counts=np.random.default_rng(1).poisson(mu).astype(float), source_path=Path("h.xrdml"),
                file_format="xrdml", sample_name="h", counting_time_s=78.54)
    r = analyze(p)
    assert any("65" in h and "홀더" in h for h in r.review_hints)
    assert review_hints(r) == r.review_hints


def test_review_hints_empty_for_clear_amorphous():
    x = np.linspace(20, 90, 2666)
    mu = 15 + 45 * np.exp(-(x - 20) / 8) + gaussian(x, 55, 44.8, 7.0) + gaussian(x, 10, 80, 10)
    p = Pattern(two_theta=x, counts=np.random.default_rng(1).poisson(mu).astype(float), source_path=Path("c.xrdml"),
                file_format="xrdml", sample_name="c", counting_time_s=78.54)
    assert analyze(p).review_hints == []


def test_default_library_json_is_valid():
    from xrdcheck.gui.storage import default_library_text, validate_library_text

    assert validate_library_text(default_library_text()) is None
    bad = json.loads(default_library_text())
    bad["phases"][-1]["d_scale_range"] = [0.5, 1.0]
    assert "d_scale_range" in validate_library_text(json.dumps(bad))
