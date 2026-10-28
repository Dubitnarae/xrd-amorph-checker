"""`python -m xrdcheck` 진입점. CLI는 Phase 2에서 구현한다."""

import sys

from xrdcheck import __version__


def main() -> int:
    print(f"XRD 비정질 판정 도우미 v{__version__}")
    print("아직 명령이 구현되지 않았습니다(Phase 2에서 CLI 추가 예정).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
