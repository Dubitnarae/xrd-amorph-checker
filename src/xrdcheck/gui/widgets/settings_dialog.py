"""설정: 판정 기준 · 파일명 날짜 규칙 · 상 라이브러리."""

from __future__ import annotations

import re

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from xrdcheck.gui.storage import default_library_text, validate_library_text
from xrdcheck.io.base import date_from_filename
from xrdcheck.settings import default_settings


def _dspin(lo, hi, step, decimals) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(decimals)
    return w


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, library_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.resize(620, 520)
        tabs = QTabWidget()

        # 판정 기준
        crit = QWidget()
        form = QFormLayout(crit)
        self.inst_fwhm = _dspin(0.01, 2.0, 0.01, 3)
        self.z_detect = _dspin(1.0, 50.0, 0.1, 2)
        self.z_suspect = _dspin(1.0, 50.0, 0.1, 2)
        self.match_tol = _dspin(0.01, 2.0, 0.01, 3)
        self.min_counts = QSpinBox()
        self.min_counts.setRange(0, 100000)
        form.addRow("기기 FWHM (°)", self.inst_fwhm)
        form.addRow("검출 기준 z", self.z_detect)
        form.addRow("의심 기준 z", self.z_suspect)
        form.addRow("상 매칭 허용오차 (±°)", self.match_tol)
        form.addRow("판정 불가: 최대 counts 미만", self.min_counts)
        note = QLabel("기준값을 바꾸면 열린 시료를 모두 다시 분석합니다.\n"
                      "바꾼 값은 보고서의 '설정·버전' 시트에 함께 남습니다.")
        note.setStyleSheet("color:#546e7a")
        form.addRow(note)
        tabs.addTab(crit, "판정 기준")

        # 파일명 규칙
        fn = QWidget()
        f2 = QFormLayout(fn)
        self.regex = QLineEdit()
        self.regex.setPlaceholderText(r"비우면 기본 규칙(YYYYMMDD 또는 6자리 YYMMDD)")
        self.test_name = QLineEdit("SMP-01a-260910-001.xrdml")
        self.test_result = QLabel()
        f2.addRow("날짜 정규식", self.regex)
        f2.addRow("시험할 파일명", self.test_name)
        f2.addRow("찾은 측정일", self.test_result)
        help_ = QLabel("이름 붙은 그룹 y(4자리) 또는 yy(2자리), m, d를 씁니다.\n"
                       "예: -(?P<yy>\\d{2})(?P<m>\\d{2})(?P<d>\\d{2})-\n"
                       "측정일은 파일명 → 폴더 경로 순으로 정합니다(파일 내부 날짜는 쓰지 않음).")
        help_.setStyleSheet("color:#546e7a")
        f2.addRow(help_)
        self.regex.textChanged.connect(self._test_regex)
        self.test_name.textChanged.connect(self._test_regex)
        tabs.addTab(fn, "파일명 규칙")

        # 상 라이브러리
        lib = QWidget()
        v = QVBoxLayout(lib)
        v.addWidget(QLabel("d값(Å)·상대강도(최강선 100)·출처를 JSON으로 적습니다. 파일의 파장으로 2θ를 계산합니다."))
        self.library = QPlainTextEdit()
        self.library.setFont(QFont("Consolas", 9))
        v.addWidget(self.library, 1)
        self.library_status = QLabel()
        v.addWidget(self.library_status)
        tabs.addTab(lib, "상 라이브러리")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("확인")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        reset = QPushButton("기본값으로")
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset.clicked.connect(self.reset_defaults)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)
        self.tabs = tabs

        self._load(settings, library_text)

    def _load(self, s: dict, library_text: str) -> None:
        self.inst_fwhm.setValue(s["instrument_fwhm_deg"])
        self.z_detect.setValue(s["z_detect"])
        self.z_suspect.setValue(s["z_suspect"])
        self.match_tol.setValue(s["phase_match"]["tolerance_deg"])
        self.min_counts.setValue(int(s["quality"]["min_max_counts"]))
        self.regex.setText(s.get("io", {}).get("filename_date_regex", ""))
        self.library.setPlainText(library_text)
        self._test_regex()

    def reset_defaults(self) -> None:
        self._load(default_settings(), default_library_text())

    def _test_regex(self) -> None:
        rx = self.regex.text().strip()
        if rx:
            try:
                re.compile(rx)
            except re.error as e:
                self.test_result.setText(f"정규식 오류: {e}")
                return
        d = date_from_filename(self.test_name.text(), rx or None)
        self.test_result.setText(d.isoformat() if d else "날짜를 찾지 못함")

    def overrides(self) -> dict:
        """기본값과 다른 값만 돌려준다(사용자 설정 파일에 저장)."""
        d = default_settings()
        cur = {
            ("instrument_fwhm_deg",): round(self.inst_fwhm.value(), 4),
            ("z_detect",): round(self.z_detect.value(), 3),
            ("z_suspect",): round(self.z_suspect.value(), 3),
            ("phase_match", "tolerance_deg"): round(self.match_tol.value(), 4),
            ("quality", "min_max_counts"): self.min_counts.value(),
            ("io", "filename_date_regex"): self.regex.text().strip(),
        }
        out: dict = {}
        for path, value in cur.items():
            base = d
            for k in path:
                base = base[k]
            if base != value:
                node = out
                for k in path[:-1]:
                    node = node.setdefault(k, {})
                node[path[-1]] = value
        return out

    def library_text(self) -> str:
        return self.library.toPlainText()

    def validate(self) -> str | None:
        if self.z_suspect.value() > self.z_detect.value():
            return "의심 기준 z는 검출 기준 z보다 클 수 없습니다."
        rx = self.regex.text().strip()
        if rx:
            try:
                re.compile(rx)
            except re.error as e:
                return f"파일명 정규식 오류: {e}"
        if err := validate_library_text(self.library_text()):
            return f"상 라이브러리: {err}"
        return None

    def accept(self) -> None:
        if err := self.validate():
            QMessageBox.warning(self, "설정 확인", err)
            return
        super().accept()
