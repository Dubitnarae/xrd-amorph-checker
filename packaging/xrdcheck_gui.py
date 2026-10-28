"""PyInstaller 진입점: exe를 실행하면 GUI를 띄운다. exe에 파일·폴더를 끌어다 놓으면 그것을 연다.

`--apply-update <설치 폴더> <PID>`로 실행되면 화면 없이 업데이트 설치만 한다(xrdcheck.updater 참고).
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-update":
        from xrdcheck.updater import apply_update_main

        sys.exit(apply_update_main(sys.argv[2:]))
    from xrdcheck.gui.app import run

    sys.exit(run(sys.argv[1:]))
