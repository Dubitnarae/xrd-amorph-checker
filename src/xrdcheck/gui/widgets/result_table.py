"""왼쪽 시료 목록: 시료명 | 판정 배지 | 나노결정 | 검토 | halo 중심 | FWHM | z최대 | 경고."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from xrdcheck.model import AnalysisResult
from xrdcheck.report.figure import VERDICT_COLORS
from xrdcheck.review import status_text

KEY_ROLE = Qt.UserRole
SORT_ROLE = Qt.UserRole + 1
COLUMNS = ["시료명", "판정", "나노결정", "검토", "halo 2θ", "FWHM", "z최대", "경고"]
COL_REVIEW, COL_WARN = 3, 7
REVIEW_ORDER = {"추천": 0, "": 3}  # ✗(틀림) 1, ✓(맞음) 2
VERDICT_ORDER = {"비정질": 0, "결정상 의심": 1, "나노결정상 후보": 2, "결정상 검출": 3, "판정 불가": 4}
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


def _tint(color: str, keep: float = 0.22) -> QColor:
    """배지 배경: 판정 색을 흰색과 섞어 연하게(글자가 잘 읽히도록)."""
    c = QColor(color)
    return QColor(*(round(255 - (255 - ch) * keep) for ch in (c.red(), c.green(), c.blue())))


def _nano_short(r: AnalysisResult) -> str:
    from xrdcheck.analysis.nano import size_short

    return size_short(r)


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

    def upsert(self, r: AnalysisResult, review: dict | None = None) -> int:
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
            (status_text(r, review, r.review_hints), None),
            (f"{h.center:.2f}" if h else "-", h.center if h else None),
            (f"{h.fwhm:.2f}" if h else "-", h.fwhm if h else None),
            (f"{r.z_max:.1f}" if r.z_max is not None else "-", r.z_max),
            (str(len(r.warnings)) if r.warnings else "", len(r.warnings)),
        ]
        for col, (text, sort) in enumerate(cells):
            item = SortItem(text)
            item.setData(SORT_ROLE, sort)
            if col > COL_REVIEW:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(row, col, item)
        self.item(row, 0).setData(KEY_ROLE, key)
        self.item(row, 0).setToolTip(str(r.pattern.source_path))
        badge = self.item(row, 1)
        badge.setIcon(verdict_icon(v))
        badge.setBackground(QBrush(_tint(VERDICT_COLORS.get(v, "#616161"))))
        if r.nano:
            self.item(row, 2).setToolTip(r.nano["label"])
        self._style_review(row, r, review)
        if r.warnings:
            self.item(row, COL_WARN).setToolTip("\n".join(f"• {w}" for w in r.warnings))
            self.item(row, COL_WARN).setForeground(QBrush(QColor("#ef6c00")))
        self.setSortingEnabled(True)
        return self._row_of(key)

    def _style_review(self, row: int, r: AnalysisResult, review: dict | None) -> None:
        item = self.item(row, COL_REVIEW)
        text = item.text()
        item.setData(SORT_ROLE, REVIEW_ORDER.get(text, 1 if text.startswith("✗") else 2))
        tips = []
        if review:
            tips.append(f"내 판정: {review['user_verdict']} (검토 {review['reviewed_at'][:10]}, "
                        f"당시 프로그램 판정 {review['program_verdict']})")
            if review.get("memo"):
                tips.append(f"메모: {review['memo']}")
            item.setForeground(QBrush(QColor("#2e7d32" if text.startswith("✓") else "#c62828")))
        elif r.review_hints:
            item.setForeground(QBrush(QColor("#1565c0")))
        if r.review_hints:
            tips.append("검토 추천 이유:\n" + "\n".join(f"• {h}" for h in r.review_hints))
        item.setToolTip("\n".join(tips))

    def set_review(self, r: AnalysisResult, review: dict | None) -> None:
        """검토 칸만 다시 쓴다(분석을 다시 하지 않음)."""
        row = self._row_of(result_key(r))
        if row < 0:
            return
        self.setSortingEnabled(False)
        self.item(row, COL_REVIEW).setText(status_text(r, review, r.review_hints))
        self._style_review(row, r, review)
        self.setSortingEnabled(True)

    def apply_filter(self, keep) -> int:
        """keep(key)가 True인 행만 보인다(None이면 모두). 보이는 행 수를 돌려준다."""
        shown = 0
        for row in range(self.rowCount()):
            hide = keep is not None and not keep(self.item(row, 0).data(KEY_ROLE))
            self.setRowHidden(row, hide)
            shown += not hide
        return shown

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
