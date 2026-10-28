"""업데이트 확인·내려받기를 백그라운드 스레드에서 실행해 화면이 멈추지 않게 한다."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from xrdcheck import updater


class UpdateCheckWorker(QThread):
    found = Signal(object)  # Release 또는 None(최신)
    failed = Signal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self) -> None:
        try:
            self.found.emit(updater.check(self.cfg))
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:  # 예상 못 한 오류도 화면을 죽이지 않는다
            self.failed.emit(f"업데이트 확인 오류: {e}")


class UpdateDownloadWorker(QThread):
    progress = Signal(int, int)  # 받은 KB, 전체 KB
    ready = Signal(str)  # 새 버전 폴더
    failed = Signal(str)

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        try:
            app = updater.prepare(self.release, lambda d, t: self.progress.emit(d // 1024, t // 1024))
            self.ready.emit(str(app))
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"업데이트 준비 오류: {e}")
