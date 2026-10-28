"""가운데 그래프: 보고서와 같은 matplotlib 그림 + 확대·이동 도구 + 표시 옵션."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from xrdcheck.model import AnalysisResult
from xrdcheck.report.figure import make_compare_figure, make_figure

YSCALES = [("√ 축", "sqrt"), ("선형", "linear"), ("로그", "log")]
COMPARE_MODES = [("겹치기", "overlay"), ("세로로 나눠 보기", "stack")]


class PlotView(QWidget):
    options_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(10, 6.5), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        self.yscale = QComboBox()
        for text, key in YSCALES:
            self.yscale.addItem(text, key)
        self.phases = QCheckBox("상 기준선")
        self.phases.setChecked(True)
        self.compare_mode = QComboBox()
        for text, key in COMPARE_MODES:
            self.compare_mode.addItem(text, key)
        self.normalize = QCheckBox("halo 높이로 정규화")
        self.normalize.setChecked(True)
        self.compare_label = QLabel("비교:")
        for w in (self.yscale, self.compare_mode):
            w.currentIndexChanged.connect(self.options_changed)
        for w in (self.phases, self.normalize):
            w.toggled.connect(self.options_changed)

        opts = QHBoxLayout()
        opts.addWidget(self.toolbar)
        opts.addStretch(1)
        opts.addWidget(QLabel("y축:"))
        opts.addWidget(self.yscale)
        opts.addWidget(self.phases)
        opts.addWidget(self.compare_label)
        opts.addWidget(self.compare_mode)
        opts.addWidget(self.normalize)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(opts)
        lay.addWidget(self.canvas, 1)
        self.set_compare_controls(False)
        self.clear()

    def set_compare_controls(self, on: bool) -> None:
        for w in (self.compare_label, self.compare_mode, self.normalize):
            w.setVisible(on)
        self.phases.setVisible(not on)

    @property
    def yscale_key(self) -> str:
        return self.yscale.currentData()

    def _done(self) -> None:
        self.canvas.draw_idle()
        self.toolbar.update()  # 확대·이동 기록 초기화

    def clear(self) -> None:
        self.figure.clear()
        self.figure.text(0.5, 0.5, "XRD 파일(.xrdml / .csv / .xy)을 끌어다 놓거나 [파일 열기]를 누르세요.",
                         ha="center", va="center", fontsize=11, color="#78909c")
        self._done()

    def show_result(self, r: AnalysisResult) -> None:
        make_figure(r, yscale=self.yscale_key, show_phases=self.phases.isChecked(), fig=self.figure)
        self._done()

    def show_compare(self, results: list[AnalysisResult]) -> None:
        make_compare_figure(results, mode=self.compare_mode.currentData(), normalize=self.normalize.isChecked(),
                            yscale=self.yscale_key, fig=self.figure)
        self._done()
