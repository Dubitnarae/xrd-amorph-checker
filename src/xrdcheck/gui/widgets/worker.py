"""분석을 백그라운드 스레드에서 실행해 화면이 멈추지 않게 한다."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from xrdcheck.analysis.pipeline import analyze_file


class AnalysisWorker(QThread):
    result_ready = Signal(object)  # AnalysisResult
    failed = Signal(str, str)  # 경로, 오류 문구
    progress = Signal(int, int)  # 완료 수, 전체 수

    def __init__(self, files: list[Path], settings: dict, library: list[dict], parent=None):
        super().__init__(parent)
        self.files, self.settings, self.library = list(files), settings, library

    def run(self) -> None:
        total = len(self.files)
        for k, f in enumerate(self.files, 1):
            if self.isInterruptionRequested():
                break
            try:
                self.result_ready.emit(analyze_file(f, self.settings, self.library))
            except Exception as e:  # 한 파일이 실패해도 나머지는 계속
                self.failed.emit(str(f), str(e))
            self.progress.emit(k, total)
