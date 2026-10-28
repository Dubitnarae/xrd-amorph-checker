"""Phase 1: 파일 읽기."""

import datetime as dt
import shutil

import numpy as np
import pytest

from xrdcheck.io import UnsupportedFileError, load_pattern
from xrdcheck.io.base import date_from_filename, date_from_folder
from xrdcheck.io.generic_xy import GenericXyError
from xrdcheck.io.rtf_meta import read_rtf_meta
from xrdcheck.io.xrdml import XrdmlError

# ---------------------------------------------------------------- 실측 샘플


def test_xrdml_matches_expected_io(sample_file, expected):
    io = expected["io"]
    p = load_pattern(sample_file(".xrdml"))
    assert p.file_format == "xrdml"
    assert p.n_points == io["n_points"]
    assert p.two_theta[0] == pytest.approx(io["two_theta_start"], abs=1e-6)
    assert p.two_theta[-1] == pytest.approx(io["two_theta_end"], abs=1e-6)
    assert p.step_deg == pytest.approx(io["step_deg"], abs=1e-6)
    assert p.kalpha1_A == io["kalpha1_A"]
    assert p.kalpha2_A == io["kalpha2_A"]
    assert p.kalpha2_ratio == io["kalpha2_ratio"]
    assert p.counting_time_s == io["counting_time_s"]
    assert p.max_counts == io["max_counts"]
    assert p.file_timestamp_raw == io["file_timestamp_raw"]
    assert np.all(np.diff(p.two_theta) > 0)


def test_csv_is_same_data_as_xrdml(sample_file, expected):
    tol = expected["io"]["xrdml_vs_csv"]["angle_abs_tol"]
    a = load_pattern(sample_file(".xrdml"))
    b = load_pattern(sample_file(".csv"))
    assert b.file_format == "xpert_csv"
    assert b.n_points == a.n_points
    assert np.max(np.abs(a.two_theta - b.two_theta)) < tol
    assert np.array_equal(a.counts, b.counts)
    assert (b.kalpha1_A, b.kalpha2_A, b.kalpha2_ratio) == (a.kalpha1_A, a.kalpha2_A, a.kalpha2_ratio)
    assert b.counting_time_s == a.counting_time_s


@pytest.mark.parametrize("suffix", [".xrdml", ".csv"])
def test_sample_date_not_from_internal_timestamp(sample_file, expected, suffix):
    p = load_pattern(sample_file(suffix))
    assert p.measurement_date is not None and p.measurement_date.year == 2026
    assert p.date_source == "파일명"
    assert any("2003" in w and "비정상" in w for w in p.warnings) == expected["io"]["expect_date_warning"]


def test_rtf_meta(sample_file, sample_stem):
    meta = read_rtf_meta(sample_file(".RTF"))
    assert meta["original_path"].startswith("C:\\X'Pert Data\\2026\\")
    assert meta["original_path"].endswith("\\" + sample_stem + ".xrdml")
    assert meta["dataset_name"] == sample_stem


def test_rtf_original_path_gives_folder_date(sample_file, sample_stem):
    p = load_pattern(sample_file(".xrdml"))
    assert p.meta["original_path"].endswith(sample_stem + ".xrdml")
    assert p.meta["date_candidates"]["폴더 경로"] == "2026-09-11"


def test_rtf_itself_is_rejected(sample_file):
    with pytest.raises(UnsupportedFileError):
        load_pattern(sample_file(".RTF"))


# ---------------------------------------------------------------- 측정일 결정


@pytest.mark.parametrize(
    "name, expected_date",
    [
        ("SMP-01a-260910-001.xrdml", dt.date(2026, 9, 10)),
        ("S1_20260911_a.xrdml", dt.date(2026, 9, 11)),
        ("SMP-01a-001.xrdml", None),
        ("SMP-999999-1.xrdml", None),  # 달력에 없는 날짜
        ("run-1234567.xrdml", None),  # 7자리는 날짜로 보지 않음
    ],
)
def test_date_from_filename(name, expected_date):
    assert date_from_filename(name) == expected_date


@pytest.mark.parametrize(
    "path, expected_date",
    [
        (r"C:\X'Pert Data\2026\DATA\0911-xrd\a.xrdml", dt.date(2026, 9, 11)),
        (r"\\nas\xrd\20260105\a.xrdml", dt.date(2026, 1, 5)),
        (r"D:\data\XRD\a.xrdml", None),
        (r"D:\2026\XRD\a.xrdml", None),  # 연도만 있으면 날짜로 쓰지 않음
    ],
)
def test_date_from_folder(path, expected_date):
    assert date_from_folder(path) == expected_date


# ---------------------------------------------------------------- 합성 XRDML

XRDML_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<xrdMeasurements xmlns="http://www.xrdml.com/XRDMeasurement/{ver}">
  <sample><name>{name}</name></sample>
  <xrdMeasurement>
    <usedWavelength>
      <kAlpha1 unit="Angstrom">1.5405980</kAlpha1>
      <kAlpha2 unit="Angstrom">1.5444260</kAlpha2>
      <ratioKAlpha2KAlpha1>0.5000</ratioKAlpha2KAlpha1>
    </usedWavelength>
    {scans}
  </xrdMeasurement>
</xrdMeasurements>"""

SCAN_TMPL = """<scan mode="Continuous" scanAxis="Gonio">
      <header><startTimeStamp>{ts}</startTimeStamp></header>
      <dataPoints>
        <positions axis="2Theta" unit="deg">{pos}</positions>
        {ct}
        <{tag} unit="{unit}">{values}</{tag}>
      </dataPoints>
    </scan>"""


def _write_xrdml(tmp_path, filename="syn-261001.xrdml", ver="2.0", name="", n_scans=1, tag="intensities",
                 unit="counts", ct=10.0, list_positions=None, values=(5, 6, 7, 8), ts="2026-10-01T10:00:00+09:00"):
    if list_positions is not None:
        pos = "<listPositions>" + " ".join(map(str, list_positions)) + "</listPositions>"
    else:
        pos = "<startPosition>20.0</startPosition><endPosition>23.0</endPosition>"
    ct_xml = f'<commonCountingTime unit="seconds">{ct}</commonCountingTime>' if ct else ""
    scan = SCAN_TMPL.format(ts=ts, pos=pos, ct=ct_xml, tag=tag, unit=unit, values=" ".join(map(str, values)))
    path = tmp_path / filename
    path.write_text(XRDML_TMPL.format(ver=ver, name=name, scans=scan * n_scans), encoding="utf-8")
    return path


def test_xrdml_start_end_positions_are_evenly_spaced(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path))
    np.testing.assert_allclose(p.two_theta, [20.0, 21.0, 22.0, 23.0])
    assert p.sample_name == "syn-261001"  # 시료명이 비어 있으면 파일명
    assert p.warnings == []  # 정상 연도이므로 날짜 경고 없음
    assert p.measurement_date == dt.date(2026, 10, 1)


def test_xrdml_list_positions_and_namespace_version(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, ver="1.5", list_positions=[20.0, 20.5, 21.5, 23.0], name="S-1"))
    np.testing.assert_allclose(p.two_theta, [20.0, 20.5, 21.5, 23.0])
    assert p.sample_name == "S-1"


def test_xrdml_counts_tag(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, tag="counts"))
    np.testing.assert_array_equal(p.counts, [5, 6, 7, 8])


def test_xrdml_cps_converted_to_counts(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, unit="counts per second", ct=2.5, values=(1.0, 2.0, 4.0, 0.4)))
    np.testing.assert_allclose(p.counts, [2.5, 5.0, 10.0, 1.0])
    assert any("cps" in w for w in p.warnings)


def test_xrdml_cps_without_counting_time_warns(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, unit="counts per second", ct=None))
    np.testing.assert_array_equal(p.counts, [5, 6, 7, 8])
    assert any("환산하지 못했습니다" in w for w in p.warnings)


def test_xrdml_multiple_scans_uses_first_and_warns(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, n_scans=3))
    assert p.n_points == 4
    assert p.meta["n_scans"] == 3
    assert any("scan이 3개" in w for w in p.warnings)


def test_xrdml_position_count_mismatch_raises(tmp_path):
    with pytest.raises(XrdmlError):
        load_pattern(_write_xrdml(tmp_path, list_positions=[20, 21, 22]))


def test_no_date_anywhere_warns_and_user_date_used(tmp_path):
    path = _write_xrdml(tmp_path, filename="nodate.xrdml", ts="")
    p = load_pattern(path)
    assert p.measurement_date is None
    assert any("측정일을 정하지 못했습니다" in w for w in p.warnings)

    p = load_pattern(path, user_date=dt.date(2026, 3, 4))
    assert (p.measurement_date, p.date_source) == (dt.date(2026, 3, 4), "사용자 입력")


def test_internal_year_differs_from_filename_warns(tmp_path):
    p = load_pattern(_write_xrdml(tmp_path, ts="2024-10-01T10:00:00+09:00"))
    assert any("2024" in w and "비정상" in w for w in p.warnings)


# ---------------------------------------------------------------- 2열 텍스트


def test_generic_xy_with_header_and_mixed_separators(tmp_path):
    lines = ["# 다른 기관 데이터", "2theta intensity"]
    lines += [f"{20 + 0.1 * i:.2f}\t{50 + i}" for i in range(6)]
    lines += [f"{20.6 + 0.1 * i:.2f}, {56 + i}" for i in range(6)]
    path = tmp_path / "other_lab.xy"
    path.write_text("\n".join(lines), encoding="utf-8")
    p = load_pattern(path)
    assert p.file_format == "generic_xy"
    assert p.n_points == 12
    assert p.counts[0] == 50 and p.counts[-1] == 61
    assert any("Cu Kα" in w for w in p.warnings)


def test_generic_xy_unsorted_is_sorted(tmp_path):
    path = tmp_path / "rev.txt"
    path.write_text("\n".join(f"{30 - i} {i}" for i in range(12)), encoding="utf-8")
    p = load_pattern(path)
    assert np.all(np.diff(p.two_theta) > 0)
    assert any("정렬" in w for w in p.warnings)


def test_plain_csv_falls_back_to_generic(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("angle,intensity\n" + "\n".join(f"{20 + i},{i * 1.5}" for i in range(12)), encoding="utf-8")
    p = load_pattern(path)
    assert p.file_format == "generic_xy"
    assert any("소수" in w for w in p.warnings)


def test_generic_xy_too_few_points(tmp_path):
    path = tmp_path / "short.xy"
    path.write_text("20 1\n21 2\n", encoding="utf-8")
    with pytest.raises(GenericXyError):
        load_pattern(path)


def test_unsupported_suffix(tmp_path):
    path = tmp_path / "a.raw"
    path.write_bytes(b"\x00\x01")
    with pytest.raises(UnsupportedFileError):
        load_pattern(path)


def test_sample_files_are_not_modified(sample_file, tmp_path):
    """읽기만 하고 원본을 바꾸지 않는지 확인(복사본과 비교)."""
    src = sample_file(".xrdml")
    copy = tmp_path / src.name
    shutil.copy2(src, copy)
    load_pattern(src)
    assert src.read_bytes() == copy.read_bytes()


@pytest.mark.parametrize(
    "name, regex, expected_date",
    [
        ("SMP-0911-2026.xrdml", r"(?P<m>\d{2})(?P<d>\d{2})-(?P<y>\d{4})", dt.date(2026, 9, 11)),
        ("SMP-01a-260910-001.xrdml", r"-(?P<yy>\d{2})(?P<m>\d{2})(?P<d>\d{2})-", dt.date(2026, 9, 10)),
        ("SMP-01a-260910-001.xrdml", r"(?P<y>\d{4})-(?P<m>\d{2})", dt.date(2026, 9, 10)),  # 그룹 부족 → 기본 규칙
    ],
)
def test_date_from_filename_user_regex(name, regex, expected_date):
    assert date_from_filename(name, regex) == expected_date
