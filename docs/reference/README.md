# 참고 구현

`prototype_analysis.py`는 계획을 세울 때 판정 방법과 기대값을 검증하려고 만든 단일 스크립트입니다.

- 실제 프로그램은 `docs/PLAN.md`의 구조(`src/xrdcheck/...`)로 나눠 새로 구현합니다.
- `tests/expected/<시료>.json`의 기대값은 이 스크립트의 출력에서 나왔습니다.
- 실행: `python docs/reference/prototype_analysis.py samples/<시료>.xrdml`
- 가상 피크 주입: `--inject 44.67:40,65.02:15` (위치:높이[counts], FWHM 0.15°)
- 필요 패키지: numpy, scipy
