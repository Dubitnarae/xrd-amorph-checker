"""판정 정확도 창: 내 판정(정답) × 프로그램 판정 혼동표와 서로 다른 시료 목록."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from xrdcheck.review import VERDICTS


def _table(rows: int, cols: int, headers: list[str]) -> QTableWidget:
    t = QTableWidget(rows, cols)
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return t


class AccuracyDialog(QDialog):
    def __init__(self, conf_now: dict, conf_all: dict, export_slot=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("판정 정확도 (내 검토 기준)")
        self.resize(820, 560)
        lay = QVBoxLayout(self)

        def acc(c):
            return "-" if c["accuracy"] is None else f"{c['accuracy'] * 100:.0f}% ({c['correct']}/{c['n']})"

        lay.addWidget(QLabel(
            f"<b>목록의 검토한 시료 {conf_now['n']}개</b> — 지금 판정 기준 정확도 {acc(conf_now)}<br>"
            f"<span style='color:#607d8b'>저장된 검토 전체 {conf_all['n']}개 — 검토할 때 판정 기준 정확도 {acc(conf_all)}</span>"))
        lay.addWidget(QLabel("혼동표: 행 = 내 판정(정답), 열 = 프로그램 판정(목록의 지금 결과). 대각선이 맞은 수입니다."))
        m = conf_now["matrix"]
        t = _table(len(VERDICTS), len(VERDICTS), VERDICTS)
        t.setVerticalHeaderLabels(VERDICTS)
        for i, u in enumerate(VERDICTS):
            for j, p in enumerate(VERDICTS):
                n = m[u][p]
                it = QTableWidgetItem(str(n) if n else "")
                it.setTextAlignment(Qt.AlignCenter)
                if n:
                    it.setBackground(QBrush(QColor("#c8e6c9" if i == j else "#ffcdd2")))
                t.setItem(i, j, it)
        t.setMaximumHeight(190)
        lay.addWidget(t)
        self.matrix = t

        lay.addWidget(QLabel(f"프로그램 판정과 내 판정이 다른 시료 {len(conf_now['disagree'])}개 — 기준값·상 카드 개선에 씁니다."))
        d = _table(len(conf_now["disagree"]), 4, ["파일", "프로그램 판정", "내 판정", "메모"])
        for i, row in enumerate(conf_now["disagree"]):
            for j, v in enumerate(row):
                d.setItem(i, j, QTableWidgetItem(str(v)))
        d.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(d, 1)
        self.disagree = d

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        if export_slot:
            b = QPushButton("검토 기록 Excel로 저장…")
            b.clicked.connect(export_slot)
            bb.addButton(b, QDialogButtonBox.ActionRole)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
