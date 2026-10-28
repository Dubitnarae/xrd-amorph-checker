"""GUI 실행: `python -m xrdcheck gui [파일|폴더 ...]`."""

from __future__ import annotations

import sys


def apply_matplotlib_rc() -> str | None:
    """화면에 그릴 때도 한글 글꼴·마이너스 설정이 적용되도록 전역으로 바꾼다. 글꼴이 없으면 경고 문구."""
    import matplotlib

    from xrdcheck.report.figure import _rc, font_family

    matplotlib.rcParams.update(_rc())
    return font_family()[1]


def run(paths: list[str] | None = None) -> int:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from xrdcheck.gui.main_window import APP_TITLE, MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setFont(QFont("Malgun Gothic", 9))
    font_warning = apply_matplotlib_rc()
    w = MainWindow()
    w.show()
    if font_warning:
        w.status.setText(font_warning)
    if paths:
        w.open_paths(paths)
    return app.exec()
