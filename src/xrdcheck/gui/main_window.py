"""메인 창: 왼쪽 목록 | 가운데 그래프 | 오른쪽 결과 패널."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QLabel, QMainWindow, QMessageBox, QProgressBar, QSplitter,
                               QToolBar)

from xrdcheck import __version__
from xrdcheck.cli import collect_files
from xrdcheck.gui.storage import UserStore
from xrdcheck.gui.widgets.detail_panel import DetailPanel
from xrdcheck.gui.widgets.plot_view import PlotView
from xrdcheck.gui.widgets.result_table import ResultTable, result_key
from xrdcheck.gui.widgets.settings_dialog import SettingsDialog
from xrdcheck.gui.widgets.worker import AnalysisWorker
from xrdcheck.io import SUPPORTED_SUFFIXES
from xrdcheck.model import AnalysisResult
from xrdcheck.report.data_csv import write_processed_csv
from xrdcheck.report.excel import write_excel
from xrdcheck.report.figure import make_compare_figure, make_figure, save_figure

APP_TITLE = "XRD 비정질 판정 도우미"
MAX_RECENT = 5
FILE_FILTER = "XRD 파일 (" + " ".join(f"*{s}" for s in SUPPORTED_SUFFIXES) + ");;모든 파일 (*.*)"


class MainWindow(QMainWindow):
    def __init__(self, config_dir: str | Path | None = None, show_dialogs: bool = True):
        super().__init__()
        self.show_dialogs = show_dialogs  # 테스트에서는 끈다(모달 창 방지)
        self.store = UserStore(config_dir)
        self.qs = QSettings(str(self.store.gui_ini), QSettings.IniFormat)
        self.settings = self.store.load_settings()
        self.library = self.store.load_library()
        self.results: dict[str, AnalysisResult] = {}
        self.pending: list[Path] = []
        self.worker: AnalysisWorker | None = None
        self.errors: list[tuple[str, str]] = []
        self._select_after: str | None = None

        self.setWindowTitle(f"{APP_TITLE} v{__version__}")
        self.setAcceptDrops(True)
        self.resize(1500, 860)

        self.table = ResultTable()
        self.plot = PlotView()
        self.detail = DetailPanel()
        self.splitter = QSplitter(Qt.Horizontal)
        for w in (self.table, self.plot, self.detail):
            self.splitter.addWidget(w)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([470, 760, 370])
        self.setCentralWidget(self.splitter)

        self.status = QLabel("파일을 끌어다 놓거나 [파일 열기]를 누르세요.")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_actions()
        self.table.itemSelectionChanged.connect(self.refresh_view)
        self.plot.options_changed.connect(self.refresh_view)
        self._restore_state()

    # ------------------------------------------------------------ 메뉴·도구
    def _act(self, text, slot, shortcut=None, checkable=False, tip=None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        self.act_open = self._act("파일 열기", self.open_files_dialog, "Ctrl+O")
        self.act_open_dir = self._act("폴더 열기", self.open_folder_dialog, "Ctrl+Shift+O")
        self.act_excel = self._act("Excel 내보내기", lambda: self.export_excel(), "Ctrl+E",
                                   tip="목록의 모든 시료를 Excel 보고서로 저장")
        self.act_png = self._act("그래프 PNG", lambda: self.export_png(), "Ctrl+P",
                                 tip="지금 보이는 그래프를 300 dpi PNG로 저장")
        self.act_csv = self._act("처리 데이터 CSV", lambda: self.export_csv(),
                                 tip="선택한 시료의 2θ·강도·모델·z·검출한계를 CSV로 저장")
        self.act_compare = self._act("비교 모드", self.toggle_compare, "Ctrl+M", checkable=True,
                                     tip="선택한 여러 시료를 한 그래프에서 비교")
        self.act_remove = self._act("선택 삭제", self.remove_selected, "Delete")
        self.act_clear = self._act("모두 지우기", self.clear_all)
        self.act_reanalyze = self._act("다시 분석", self.reanalyze_all, "F5")
        self.act_settings = self._act("설정", self.open_settings, "Ctrl+,")
        self.act_about = self._act("정보", self.show_about)

        tb = QToolBar("주 도구")
        tb.setMovable(False)
        self.addToolBar(tb)
        for a in (self.act_open, self.act_open_dir, None, self.act_excel, self.act_png, self.act_csv, None,
                  self.act_compare, self.act_reanalyze, self.act_settings):
            tb.addSeparator() if a is None else tb.addAction(a)

        m = self.menuBar().addMenu("파일")
        m.addAction(self.act_open)
        m.addAction(self.act_open_dir)
        self.recent_menu = m.addMenu("최근 폴더")
        m.addSeparator()
        for a in (self.act_excel, self.act_png, self.act_csv):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self._act("끝내기", self.close, "Ctrl+Q"))
        m = self.menuBar().addMenu("보기")
        for a in (self.act_compare, self.act_remove, self.act_clear, self.act_reanalyze):
            m.addAction(a)
        m = self.menuBar().addMenu("도구")
        m.addAction(self.act_settings)
        m = self.menuBar().addMenu("도움말")
        m.addAction(self.act_about)
        self._update_recent_menu()

    # ------------------------------------------------------------ 최근 폴더·창 상태
    def recent_dirs(self) -> list[str]:
        v = self.qs.value("recent_dirs", [])
        if isinstance(v, str):
            v = [v]
        return [d for d in (v or []) if d]

    def _remember_dir(self, d: Path) -> None:
        d = str(d)
        dirs = [d] + [x for x in self.recent_dirs() if x != d]
        self.qs.setValue("recent_dirs", dirs[:MAX_RECENT])
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        self.recent_menu.clear()
        dirs = self.recent_dirs()
        for d in dirs:
            a = self.recent_menu.addAction(d)
            a.triggered.connect(lambda _=False, d=d: self.open_paths([d]))
        self.recent_menu.setEnabled(bool(dirs))

    def _last_dir(self) -> str:
        dirs = self.recent_dirs()
        return dirs[0] if dirs else str(Path.home())

    def _restore_state(self) -> None:
        if geo := self.qs.value("geometry"):
            self.restoreGeometry(geo)
        if st := self.qs.value("splitter"):
            self.splitter.restoreState(st)
        idx = self.qs.value("yscale_index")
        if idx is not None:
            self.plot.yscale.setCurrentIndex(int(idx))

    def closeEvent(self, event) -> None:
        self.qs.setValue("geometry", self.saveGeometry())
        self.qs.setValue("splitter", self.splitter.saveState())
        self.qs.setValue("yscale_index", self.plot.yscale.currentIndex())
        self.qs.sync()
        if self.worker is not None:
            self.pending.clear()
            self.worker.requestInterruption()
            self.worker.wait(10000)
        super().closeEvent(event)

    # ------------------------------------------------------------ 파일 열기
    def open_files_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "XRD 파일 열기", self._last_dir(), FILE_FILTER)
        if files:
            self.open_paths(files)

    def open_folder_dialog(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "폴더 열기", self._last_dir())
        if d:
            self.open_paths([d])

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.open_paths(paths)
            event.acceptProposedAction()

    def open_paths(self, paths: list[str | Path]) -> int:
        files, notes = collect_files([str(p) for p in paths])
        first = Path(paths[0])
        self._remember_dir(first if first.is_dir() else first.parent)
        if notes:
            self.status.setText(" / ".join(notes[:3]) + (" …" if len(notes) > 3 else ""))
        if not files:
            if not notes:
                self.status.setText("분석할 XRD 파일이 없습니다.")
            return 0
        self._enqueue(files)
        return len(files)

    # ------------------------------------------------------------ 분석(백그라운드)
    def is_busy(self) -> bool:
        return self.worker is not None or bool(self.pending)

    def _enqueue(self, files: list[Path]) -> None:
        self.pending += files
        if self.worker is None:
            self._start_worker()

    def _start_worker(self) -> None:
        files, self.pending = self.pending, []
        self.errors.clear()
        self.worker = AnalysisWorker(files, self.settings, self.library, self)
        self.worker.result_ready.connect(self._on_result)
        self.worker.failed.connect(self._on_failed)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status.setText(f"분석 중… (0/{len(files)})")
        self.worker.start()

    def _on_result(self, r: AnalysisResult) -> None:
        key = result_key(r)
        self.results[key] = r
        self.table.upsert(r)
        if not self.table.selected_keys():
            self.table.select_key(key)
        elif key in self.table.selected_keys():
            self.refresh_view()

    def _on_failed(self, path: str, msg: str) -> None:
        self.errors.append((path, msg))

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.status.setText(f"분석 중… ({done}/{total})")

    def _on_finished(self) -> None:
        self.worker.deleteLater()
        self.worker = None
        if self.pending:
            self._start_worker()
            return
        self.progress.setVisible(False)
        msg = f"분석 완료 — 목록 {len(self.results)}개"
        if self.errors:
            msg += f", 실패 {len(self.errors)}개"
            if self.show_dialogs:
                QMessageBox.warning(self, "읽기 실패",
                                    "\n".join(f"{Path(p).name}: {m}" for p, m in self.errors[:15]))
        self.status.setText(msg)

    def reanalyze_all(self) -> None:
        files = [self.results[k].pattern.source_path for k in self.table.keys_in_order()]
        if files:
            self._enqueue(files)

    # ------------------------------------------------------------ 보기
    def selected_results(self) -> list[AnalysisResult]:
        return [self.results[k] for k in self.table.selected_keys() if k in self.results]

    def current_result(self) -> AnalysisResult | None:
        sel = self.selected_results()
        return sel[0] if sel else None

    def refresh_view(self) -> None:
        sel = self.selected_results()
        compare = self.act_compare.isChecked()
        self.plot.set_compare_controls(compare)
        if not sel:
            self.plot.clear()
            self.detail.clear_result()
            return
        if compare:
            self.plot.show_compare(sel)
            self.detail.set_compare(sel) if len(sel) > 1 else self.detail.set_result(sel[0])
        else:
            self.plot.show_result(sel[0])
            self.detail.set_result(sel[0])

    def toggle_compare(self) -> None:
        if self.act_compare.isChecked() and len(self.table.selected_keys()) < 2:
            self.status.setText("비교 모드: 목록에서 Ctrl/Shift로 여러 시료를 고르세요.")
        self.refresh_view()

    def remove_selected(self) -> None:
        keys = self.table.selected_keys()
        self.table.remove_keys(keys)
        for k in keys:
            self.results.pop(k, None)
        self.refresh_view()

    def clear_all(self) -> None:
        self.table.setRowCount(0)
        self.results.clear()
        self.refresh_view()

    # ------------------------------------------------------------ 내보내기
    def _save_path(self, title: str, default_name: str, filt: str, path) -> Path | None:
        if path:
            return Path(path)
        p, _ = QFileDialog.getSaveFileName(self, title, str(Path(self._last_dir()) / default_name), filt)
        return Path(p) if p else None

    def _report_error(self, title: str, err: Exception) -> None:
        self.status.setText(f"{title}: {err}")
        if self.show_dialogs:
            QMessageBox.warning(self, title, str(err))

    def export_excel(self, path=None) -> Path | None:
        results = [self.results[k] for k in self.table.keys_in_order()]
        if not results:
            self.status.setText("내보낼 결과가 없습니다.")
            return None
        path = self._save_path("Excel 내보내기", "XRD_판정결과.xlsx", "Excel (*.xlsx)", path)
        if not path:
            return None
        try:
            write_excel(results, path)
        except PermissionError:
            self._report_error("저장 실패", PermissionError(f"{path.name}이(가) Excel에서 열려 있으면 닫고 다시 시도하세요."))
            return None
        self.status.setText(f"Excel 저장: {path}")
        return path

    def export_png(self, path=None) -> Path | None:
        sel = self.selected_results()
        if not sel:
            self.status.setText("그래프로 저장할 시료를 고르세요.")
            return None
        compare = self.act_compare.isChecked()
        name = "비교.png" if compare else f"{sel[0].pattern.source_path.stem}.png"
        path = self._save_path("그래프 PNG 저장", name, "PNG 그림 (*.png)", path)
        if not path:
            return None
        if compare:
            fig = make_compare_figure(sel, mode=self.plot.compare_mode.currentData(),
                                      normalize=self.plot.normalize.isChecked(), yscale=self.plot.yscale_key)
        else:
            fig = make_figure(sel[0], yscale=self.plot.yscale_key, show_phases=self.plot.phases.isChecked())
        try:
            save_figure(fig, path)
        except OSError as e:
            self._report_error("저장 실패", e)
            return None
        self.status.setText(f"그래프 저장: {path}")
        return path

    def export_csv(self, path=None) -> Path | None:
        r = self.current_result()
        if r is None:
            self.status.setText("CSV로 저장할 시료를 고르세요.")
            return None
        path = self._save_path("처리 데이터 CSV", f"{r.pattern.source_path.stem}_processed.csv", "CSV (*.csv)", path)
        if not path:
            return None
        try:
            write_processed_csv(r, path)
        except OSError as e:
            self._report_error("저장 실패", e)
            return None
        self.status.setText(f"CSV 저장: {path}")
        return path

    # ------------------------------------------------------------ 설정·정보
    def make_settings_dialog(self) -> SettingsDialog:
        return SettingsDialog(self.settings, self.store.library_text(), self)

    def apply_settings(self, dlg: SettingsDialog) -> None:
        self.store.save_settings(dlg.overrides())
        self.store.save_library_text(dlg.library_text())
        self.settings = self.store.load_settings()
        self.library = self.store.load_library()
        self.reanalyze_all()

    def open_settings(self) -> None:
        dlg = self.make_settings_dialog()
        if dlg.exec():
            self.apply_settings(dlg)

    def show_about(self) -> None:
        QMessageBox.about(self, "정보",
                          f"<b>{APP_TITLE}</b> v{__version__}<br><br>"
                          "비정질 halo를 피팅하고 결정 피크를 통계적으로 찾아<br>"
                          "비정질 / 결정상 의심 / 결정상 검출 / 판정 불가로 판정합니다.<br><br>"
                          "판정은 보조 수단입니다. 근거(그래프·수치·검출한계)를 확인하고 최종 판단은 사람이 합니다."
                          f"<br><br>사용자 설정 폴더: {self.store.dir}")
