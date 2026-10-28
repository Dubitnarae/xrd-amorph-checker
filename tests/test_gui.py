"""Phase 3: GUI (화면 없이 offscreen으로 실행)."""

import json
import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from xrdcheck.cli import build_parser  # noqa: E402
from xrdcheck.gui.app import apply_matplotlib_rc  # noqa: E402
from xrdcheck.gui.main_window import MainWindow  # noqa: E402
from xrdcheck.gui.storage import UserStore, validate_library_text  # noqa: E402
from xrdcheck.gui.widgets.result_table import KEY_ROLE  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    apply_matplotlib_rc()
    w = MainWindow(config_dir=tmp_path / "cfg", show_dialogs=False)
    qtbot.addWidget(w)
    w.show()
    return w


def _wait(qtbot, w):
    qtbot.waitUntil(lambda: not w.is_busy(), timeout=60000)


@pytest.fixture
def two_samples(sample_file, tmp_path):
    """같은 데이터를 다른 이름으로 2개(.xrdml + .csv) — 같은 이름이면 .csv는 건너뛰므로 이름을 바꿈."""
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(sample_file(".xrdml"), d / "A-260910.xrdml")
    shutil.copy(sample_file(".csv"), d / "B-260910.csv")
    return d


def test_open_folder_shows_verdict(window, qtbot, sample_file):
    w = window
    assert w.open_paths([str(sample_file(".xrdml").parent)]) == 1  # .csv는 같은 이름의 .xrdml이 있어 건너뜀
    _wait(qtbot, w)
    assert w.table.rowCount() == 1
    assert w.table.item(0, 1).text() == "비정질"
    assert w.table.item(0, 2).text() == "44.76"
    assert w.table.selected_keys()  # 첫 결과가 자동 선택됨
    html = w.detail.toPlainText()
    assert "비정질" in html and "검출한계" in html and "α-Fe(110)" in html
    assert len(w.plot.figure.axes) == 2  # 패턴 + z
    assert "분석 완료" in w.status.text()


def test_exports(window, qtbot, sample_file, tmp_path):
    w = window
    w.open_paths([str(sample_file(".xrdml"))])
    _wait(qtbot, w)
    xlsx = w.export_excel(tmp_path / "out" / "r.xlsx")
    png = w.export_png(tmp_path / "out" / "g.png")
    csv = w.export_csv(tmp_path / "out" / "d.csv")
    assert xlsx.exists() and xlsx.stat().st_size > 0
    assert png.read_bytes()[:4] == b"\x89PNG"
    assert csv.read_bytes()[:3] == b"\xef\xbb\xbf"


def test_compare_mode(window, qtbot, two_samples, tmp_path):
    w = window
    assert w.open_paths([str(two_samples)]) == 2
    _wait(qtbot, w)
    w.table.selectAll()
    w.act_compare.setChecked(True)
    w.refresh_view()
    assert len(w.plot.figure.axes) == 1  # 겹치기
    assert "시료 비교 (2개)" in w.detail.toPlainText()
    w.plot.compare_mode.setCurrentIndex(1)  # 세로로 나눠 보기 → options_changed로 다시 그림
    assert len(w.plot.figure.axes) == 2
    assert w.export_png(tmp_path / "cmp.png").exists()


def test_remove_and_clear(window, qtbot, two_samples):
    w = window
    w.open_paths([str(two_samples)])
    _wait(qtbot, w)
    w.table.selectRow(0)
    w.remove_selected()
    assert w.table.rowCount() == 1 and len(w.results) == 1
    w.clear_all()
    assert w.table.rowCount() == 0 and not w.results
    assert w.export_excel("unused.xlsx") is None  # 결과가 없으면 저장하지 않음


def test_bad_file_is_reported_not_fatal(window, qtbot, tmp_path):
    bad = tmp_path / "bad.xy"
    bad.write_text("no data", encoding="utf-8")
    window.open_paths([str(bad)])
    _wait(qtbot, window)
    assert window.table.rowCount() == 0
    assert "실패 1개" in window.status.text()


def test_settings_change_reanalyzes_and_persists(window, qtbot, sample_file):
    w = window
    w.open_paths([str(sample_file(".xrdml"))])
    _wait(qtbot, w)
    dlg = w.make_settings_dialog()
    dlg.z_detect.setValue(3.0)  # 샘플 z최대 3.3 → 기준을 낮추면 결정상 쪽으로 바뀜
    dlg.z_suspect.setValue(2.5)
    assert dlg.validate() is None
    w.apply_settings(dlg)
    _wait(qtbot, w)
    assert w.settings["z_detect"] == 3.0
    assert w.table.item(0, 1).text() != "비정질"
    saved = json.loads(w.store.settings_path.read_text(encoding="utf-8"))
    assert saved == {"z_detect": 3.0, "z_suspect": 2.5}  # 기본값과 다른 값만 저장

    dlg = w.make_settings_dialog()
    dlg.reset_defaults()
    assert dlg.overrides() == {}
    w.apply_settings(dlg)
    _wait(qtbot, w)
    assert w.table.item(0, 1).text() == "비정질"
    assert not w.store.phases_path.exists()  # 상 라이브러리가 기본값이면 사용자 사본 없음


def test_settings_validation(window):
    dlg = window.make_settings_dialog()
    dlg.z_detect.setValue(4.0)
    dlg.z_suspect.setValue(4.5)
    assert "의심 기준" in dlg.validate()
    dlg.z_suspect.setValue(3.5)
    dlg.regex.setText("(?P<yy>")
    assert "정규식" in dlg.validate()
    dlg.regex.setText("")
    dlg.library.setPlainText('{"phases": [{"name": "X", "lines": [{"hkl": "110", "d_A": -1, "rel": 100}]}]}')
    assert "상 라이브러리" in dlg.validate()


def test_settings_regex_preview(window):
    dlg = window.make_settings_dialog()
    dlg.test_name.setText("S-0911-2026.xrdml")
    dlg.regex.setText(r"(?P<m>\d{2})(?P<d>\d{2})-(?P<y>\d{4})")
    assert dlg.test_result.text() == "2026-09-11"


def test_validate_library_text():
    from xrdcheck.gui.storage import default_library_text

    assert validate_library_text(default_library_text()) is None
    assert "JSON" in validate_library_text("{")
    assert "phases" in validate_library_text("{}")


def test_recent_dirs_persist(qtbot, tmp_path, sample_file):
    cfg = tmp_path / "cfg"
    w = MainWindow(config_dir=cfg, show_dialogs=False)
    qtbot.addWidget(w)
    w.open_paths([str(sample_file(".xrdml"))])
    _wait(qtbot, w)
    w.close()
    w2 = MainWindow(config_dir=cfg, show_dialogs=False)
    qtbot.addWidget(w2)
    assert w2.recent_dirs()[0] == str(sample_file(".xrdml").parent)
    assert w2.recent_menu.isEnabled()


def test_table_sorts_by_verdict(window, qtbot, two_samples):
    w = window
    w.open_paths([str(two_samples)])
    _wait(qtbot, w)
    w.table.sortItems(2)
    keys = [w.table.item(r, 0).data(KEY_ROLE) for r in range(w.table.rowCount())]
    assert len(keys) == 2 and all(keys)


def test_user_store_ignores_broken_settings(tmp_path):
    s = UserStore(tmp_path)
    s.settings_path.write_text("{broken", encoding="utf-8")
    assert s.load_settings()["z_detect"] == 5.0


def test_cli_gui_parser():
    args = build_parser().parse_args(["gui", "a.xrdml", "folder"])
    assert args.paths == ["a.xrdml", "folder"]
