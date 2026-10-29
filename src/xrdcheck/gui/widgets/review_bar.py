"""결과 패널 아래 검토 막대: [판정 맞음] [판정 틀림 ▾] [메모…] [검토 지우기]."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget

from xrdcheck.review import VERDICTS


class ReviewBar(QWidget):
    marked = Signal(object)  # 사용자 판정 문자열, 또는 None(= 프로그램 판정이 맞음)
    memo_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(QLabel("검토:"))
        self.btn_ok = QPushButton("✓ 판정 맞음")
        self.btn_ok.setToolTip("프로그램 판정이 맞다고 기록합니다(선택한 시료 모두). 단축키 Ctrl+Enter")
        self.btn_ok.clicked.connect(lambda: self.marked.emit(None))
        self.btn_wrong = QToolButton()
        self.btn_wrong.setText("✗ 판정 틀림 ▾")
        self.btn_wrong.setToolTip("실제 판정을 고르면 '틀림'으로 기록합니다")
        self.btn_wrong.setPopupMode(QToolButton.InstantPopup)
        self.wrong_menu = QMenu(self)
        self.verdict_actions = {}
        for v in VERDICTS:
            a = self.wrong_menu.addAction(f"실제는 '{v}'")
            a.triggered.connect(lambda _=False, v=v: self.marked.emit(v))
            self.verdict_actions[v] = a
        self.btn_wrong.setMenu(self.wrong_menu)
        self.btn_memo = QPushButton("메모…")
        self.btn_memo.clicked.connect(self.memo_requested)
        self.btn_clear = QPushButton("검토 지우기")
        self.btn_clear.clicked.connect(self.clear_requested)
        for b in (self.btn_ok, self.btn_wrong, self.btn_memo, self.btn_clear):
            lay.addWidget(b)
        lay.addStretch(1)
        self.set_state(None, None)

    def set_state(self, program_verdict: str | None, review: dict | None) -> None:
        """선택이 없으면 모두 끈다. 프로그램 판정과 같은 항목은 '틀림' 메뉴에서 끈다."""
        on = program_verdict is not None
        for b in (self.btn_ok, self.btn_wrong):
            b.setEnabled(on)
        self.btn_memo.setEnabled(on and review is not None)
        self.btn_clear.setEnabled(on and review is not None)
        for v, a in self.verdict_actions.items():
            a.setEnabled(v != program_verdict)
