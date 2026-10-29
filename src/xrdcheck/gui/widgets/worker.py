"""분석을 백그라운드 스레드에서 실행해 화면이 멈추지 않게 한다."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from xrdcheck.analysis.pipeline import analyze_file
from xrdcheck.review import result_file_key


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
                r = analyze_file(f, self.settings, self.library)
                result_file_key(r)  # 검토 기록용 파일 해시를 여기서 미리 계산(화면 스레드가 파일을 다시 읽지 않게)
                self.result_ready.emit(r)
            except Exception as e:  # 한 파일이 실패해도 나머지는 계속
                self.failed.emit(str(f), str(e))
            self.progress.emit(k, total)
