"""Phase 2: 보고서(Excel·PNG·CSV)와 CLI."""

import csv

import pytest
from openpyxl import load_workbook

from xrdcheck.cli import collect_files, main


def test_cli_end_to_end(sample_file, sample_stem, tmp_path, capsys):
    src = sample_file(".xrdml")
    out = tmp_path / "result.xlsx"
    code = main(["analyze", str(src.parent), "--out", str(out), "--png", str(tmp_path / "figs"),
                 "--csv", str(tmp_path / "data")])
    assert code == 0
    text = capsys.readouterr().out
    assert f"[비정질] {sample_stem}.xrdml" in text
    assert f"건너뜀(같은 이름의 .xrdml 사용): {sample_stem}.csv" in text

    wb = load_workbook(out)
    assert wb.sheetnames == ["요약", "피크", "설정·버전"]
    head = [c.value for c in wb["요약"][1]]
    row = dict(zip(head, [c.value for c in wb["요약"][2]]))
    assert row["판정"] == "비정질"
    assert row["주 halo 2θ(°)"] == pytest.approx(44.76, abs=0.01)
    assert row["검출한계 α-Fe(110)(counts)"] == pytest.approx(23.4, abs=0.5)
    info = {r[0]: r[1] for r in wb["설정·버전"].iter_rows(min_row=2, values_only=True)}
    assert info["z_detect"] == "5.0" and info["버전"]

    png = tmp_path / "figs" / f"{sample_stem}.png"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    data = tmp_path / "data" / f"{sample_stem}_processed.csv"
    assert data.read_bytes()[:3] == b"\xef\xbb\xbf"  # utf-8-sig
    with data.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[1][0] == "2θ(°)" and len(rows) == 2 + 2666


def test_cli_bad_file_continues(tmp_path, capsys):
    bad = tmp_path / "bad.xy"
    bad.write_text("not data", encoding="utf-8")
    assert main(["analyze", str(bad)]) == 1
    assert "[오류] bad.xy" in capsys.readouterr().out


def test_collect_files_skips_duplicate_csv(tmp_path):
    for name in ("a.xrdml", "a.csv", "b.csv", "readme.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    files, notes = collect_files([str(tmp_path)])
    assert [f.name for f in files] == ["a.xrdml", "b.csv"]
    assert any("a.csv" in n for n in notes)
