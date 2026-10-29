# XRD 비정질 판정 도우미 (xrdcheck)

X'Pert PRO·Rigaku SmartLab 등에서 받은 XRD 결과(.xrdml / .rasx / X'Pert .csv / 2열 텍스트)를 넣으면
비정질 halo를 피팅하고 결정 피크를 통계적으로 찾아 판정하는 Windows 프로그램입니다.

| 판정 | 뜻 |
|---|---|
| 비정질 | 의심 기준(z 4.5) 이상의 좁은 결정 피크가 없음 |
| 결정상 의심 | 의심 구간 피크, 또는 상 라이브러리와 맞지 않는 단일 피크 |
| 결정상 검출 | 검출 기준(z 5.0) 이상 피크가 상과 매칭되거나 2개 이상 |
| 나노결정상 후보 | 결정상 검출 중 **주 halo 위** 피크의 Scherrer 결정립 크기가 **10–90 nm** |
| 판정 불가 | 측정 범위 부족, 피팅 실패, 계수가 너무 낮음 |

개발자: KIM YEONGDO

판정은 보조 수단입니다. 근거(그래프·z·검출한계·결정립 크기)를 함께 보여 주므로 최종 판단은 사람이 합니다.

## 설치와 실행 (배포판)

1. [Releases](../../releases)에서 `XRD_Checker_v<버전>.zip`을 받습니다.
2. 압축을 풀고 `XRD_Checker\XRD_Checker.exe`를 실행합니다(설치 필요 없음).
3. 파일이나 폴더를 창에 끌어다 놓으면 분석합니다. Excel·그래프 PNG·처리 데이터 CSV로 내보낼 수 있습니다.

- 사용자 설정은 `%APPDATA%\xrdcheck\`에 저장됩니다(판정 기준, 상 라이브러리, 창 상태).
- v0.7.0부터는 **도움말 > 업데이트 확인**으로 프로그램 안에서 새 버전을 설치합니다(시작할 때 하루 한 번 자동 확인, 끌 수 있음).
  압축은 쓰기 가능한 폴더(예: 문서, 바탕화면)에 풀어 두세요. `Program Files`처럼 쓰기 권한이 없는 곳이면 릴리스 위치만 열어 줍니다.
- 업데이트 출처는 기본이 GitHub 릴리스입니다. 회사 공유 폴더를 쓰려면 `%APPDATA%\xrdcheck\update.json`에
  `{"folder": "\\\\NAS\\공유\\XRD_Checker"}`처럼 적습니다(JSON이라 역슬래시를 두 번씩). 그 폴더에 `XRD_Checker_v<버전>.zip`과 `.zip.sha256`을 두면 됩니다.
- 업데이트 기록은 `%LOCALAPPDATA%\xrdcheck\update\update.log`에 남습니다.

## 나노결정상 후보와 결정립 크기

- 주 halo 범위(중심 ± 0.5 × FWHM) 위에 검출 피크가 있어야 합니다.
- Scherrer 식은 약 100 nm까지만 쓸 수 있어서, 피크 폭이 100 nm에 해당하는 폭보다 좁으면 크기를 내지 않고 `> 100 nm`로 표시합니다.
- D = 0.9 λ / (β cos θ), β = √(B² − b²). B는 Kα1 피크 FWHM, b는 기기 폭입니다.
  기기 폭은 아직 표준시료(Si·LaB6)로 측정하지 않은 추정값(45°에서 0.10°)입니다.
- 약 6 nm 이하는 halo와 구분하기 어렵고, 40 nm 이상은 약한 피크에서 오차가 커집니다. 오차(±)를 함께 보세요.
- 결정 분율 Xc는 산란인자 차이를 보정하지 않은 참고값입니다.

## 판정 검토(맞음/틀림)

- 결과 패널 아래 **[✓ 판정 맞음] [✗ 판정 틀림 ▾]**로 내 판정을 기록합니다(여러 시료를 골라 한 번에 가능, 단축키 Ctrl+Enter).
- 목록 **검토** 칸의 `추천`은 판정이 경계에 있거나 근거가 약해 사람이 한 번 보면 좋은 시료입니다. 이유는 결과 패널에 나옵니다.
- **검토 > 검토할 시료만 보기**(Ctrl+R)로 추천 시료만 차례로 보고, **검토 > 판정 정확도**에서 혼동표를 봅니다.
- 기록은 `%APPDATA%\xrdcheck\reviews.json`(파일 내용 기준)에 남고, 기준값·상 카드를 고칠 때 근거로 씁니다.

## 격자상수 · Si 함량 (참고)

- α-Fe(Si)·Fe3Si(DO3)에 매칭된 피크로 bcc 격자상수 a를 냅니다(Fe3Si는 a/2로 환산).
- Si 함량은 Fe–Si 2원계 문헌값을 이은 보정표로 환산합니다:
  a = 2.8665 Å(0 at%), 2.8617 Å(7 at%, 저Si 기울기 −0.00069 Å/at%), 2.840 Å(18 at%, FINEMET 나노결정), 2.8275 Å(25 at%, Fe3Si 5.655 Å ÷ 2).
  표는 `default_settings.json`의 `lattice.si_calibration`에서 바꿀 수 있습니다.
- 2θ 영점·시료 높이 오차 0.02°가 약 0.5 at%에 해당합니다. Co·Ni·Al·P 등이 함께 고용되면 맞지 않습니다.

## 상 라이브러리

- 기본 상: α-Fe, α-Fe(Si)(격자상수 범위), Fe3Si(DO3), fcc-Al(Al계), 석영(오염·홀더 — 판정 제외)
- 2차 상(`role: secondary`): Fe2B, (Fe,Nb)23B6, 준안정 Fe3B(I-4), Fe3C, Fe5PB2, Fe2P, fcc(γ-Fe/Cu), Fe3O4.
  결정 판정에는 쓰지만 나노결정상 후보 판단에서는 뺍니다.
- 2차 상의 회절선은 COD 문헌 구조(`tools/cards/*.cif`)로 `tools/make_phase_cards.py`가 계산합니다(`pip install -e .[cards]`).

## 개발자용

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev,build]
pytest -q                      # 테스트
python -m xrdcheck gui         # 화면
python -m xrdcheck analyze <파일|폴더> --out out\result.xlsx --png out\figs
.\build.ps1                    # 배포 zip 만들기 (dist\)
```

- 기준값은 `src/xrdcheck/data/default_settings.json`, 상 라이브러리는 `src/xrdcheck/data/phases.json`에 있습니다.
- 실측 데이터는 저장소에 없습니다. 실측 파일이 필요한 테스트는 파일이 없으면 건너뜁니다.
