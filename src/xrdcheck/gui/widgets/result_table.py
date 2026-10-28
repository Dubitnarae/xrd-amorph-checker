"""왼쪽 시료 목록: 시료명 | 판정 배지 | halo 중심 | FWHM | z최대 | 경고."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from xrdcheck.model import AnalysisResult
from xrdcheck.report.figure import VERDICT_COLORS

KEY_ROLE = Qt.UserRole
SORT_ROLE = Qt.UserRole + 1
COLUMNS = ["시료명", "판정", "나노결정", "halo 2θ", "FWHM", "z최대", "경고"]
VERDICT_ORDER = {"비정질": 0, "결정상 의심": 1, "결정상 검출": 2, "판정 불가": 3}
_ICONS: dict[str, QIcon] = {}


def verdict_icon(verdict: str) -> QIcon:
    if verdict not in _ICONS:
        pm = QPixmap(14, 14)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(VERDICT_COLORS.get(verdict, "#616161")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 12, 12)
        p.end()
        _ICONS[verdict] = QIcon(pm)
    return _ICONS[verdict]


class SortItem(QTableWidgetItem):
    """표시 문자열과 별개로 숫자 값으로 정렬한다(값이 없으면 맨 뒤)."""

    def __lt__(self, other):
        a, b = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if a is None or b is None:
            return b is None and a is not None
        return a < b


def _nano_short(r: AnalysisResult) -> str:
    """목록용 짧은 표기: 후보 / 의심 / 아님 / 빈칸."""
    if not r.nano:
        return ""
    s = r.nano.get("size")
    if s and s["size_nm"] is not None:
        prefix = {"분해능 한계(이상)": ">", "폭 상한(이하)": "≤"}.get(s["limit"], "")
        return f"후보 {prefix}{s['size_nm']:.0f} nm"
    return {"나노결정 후보": "후보", "나노결정 의심": "의심"}.get(r.nano["label"], "아님")


def result_key(r: AnalysisResult) -> str:
    return str(r.pattern.source_path.resolve())


class ResultTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self.setHorizontalHeaderLabels(COLUMNS)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Interactive)  # 시료명은 고정 폭(끌어서 조절)
        self.setColumnWidth(0, 150)
        for i in range(1, len(COLUMNS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        self.setSortingEnabled(True)

    def _row_of(self, key: str) -> int:
        for row in range(self.rowCount()):
            if self.item(row, 0).data(KEY_ROLE) == key:
                return row
        return -1

    def upsert(self, r: AnalysisResult) -> int:
        key = result_key(r)
        self.setSortingEnabled(False)
        row = self._row_of(key)
        if row < 0:
            row = self.rowCount()
            self.insertRow(row)
        h = r.halo
        v = r.verdict.value
        cells = [
            (r.pattern.sample_name, r.pattern.sample_name.lower()),
            (v, VERDICT_ORDER.get(v, 9)),
            (_nano_short(r), _nano_short(r)),
            (f"{h.center:.2f}" if h else "-", h.center if h else None),
            (f"{h.fwhm:.2f}" if h else "-", h.fwhm if h else None),
            (f"{r.z_max:.1f}" if r.z_max is not None else "-", r.z_max),
            (str(len(r.warnings)) if r.warnings else "", len(r.warnings)),
        ]
        for col, (text, sort) in enumerate(cells):
            item = SortItem(text)
            item.setData(SORT_ROLE, sort)
            if col > 2:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(row, col, item)
        self.item(row, 0).setData(KEY_ROLE, key)
        self.item(row, 0).setToolTip(str(r.pattern.source_path))
        badge = self.item(row, 1)
        badge.setIcon(verdict_icon(v))
        badge.setBackground(QBrush(QColor(VERDICT_COLORS.get(v, "#616161")).lighter(185)))
        if r.nano:
            self.item(row, 2).setToolTip(r.nano["label"])
        if r.warnings:
            self.item(row, 6).setToolTip("\n".join(f"• {w}" for w in r.warnings))
            self.item(row, 6).setForeground(QBrush(QColor("#ef6c00")))
        self.setSortingEnabled(True)
        return self._row_of(key)

    def keys_in_order(self) -> list[str]:
        return [self.item(r, 0).data(KEY_ROLE) for r in range(self.rowCount())]

    def selected_keys(self) -> list[str]:
        rows = sorted({i.row() for i in self.selectedIndexes()})
        return [self.item(r, 0).data(KEY_ROLE) for r in rows]

    def select_key(self, key: str) -> None:
        row = self._row_of(key)
        if row >= 0:
            self.selectRow(row)

    def remove_keys(self, keys: list[str]) -> None:
        for key in keys:
            row = self._row_of(key)
            if row >= 0:
                self.removeRow(row)
