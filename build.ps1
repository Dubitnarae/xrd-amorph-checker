# XRD 비정질 판정 도우미 — 배포용 빌드 (PyInstaller onedir → zip + sha256)
#   사용: 프로젝트 폴더에서  .\build.ps1
#   결과: dist\XRD_Checker\XRD_Checker.exe, dist\XRD_Checker_v<버전>.zip, .zip.sha256
# PowerShell 5.1은 외부 프로그램의 stderr 출력(PyInstaller INFO 등)을 "Stop"이면 오류로 멈추므로 Continue로 두고
# 각 단계는 $LASTEXITCODE로 확인한다.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv가 없습니다. CLAUDE.md의 '처음 설치'를 먼저 하세요." }

$version = (& $py -c "import xrdcheck; print(xrdcheck.__version__)").Trim()
$toml = Select-String -Path pyproject.toml -Pattern '^version = "(.+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value }
if ($version -ne $toml) { throw "버전 불일치: __init__.py $version / pyproject.toml $toml" }
Write-Host "버전 $version 빌드 시작"

& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "테스트 실패 — 빌드 중단" }

& $py packaging\make_version_info.py build\version_info.txt
if ($LASTEXITCODE -ne 0) { throw "버전 정보 만들기 실패" }
& $py -m PyInstaller --noconfirm --clean --onedir --windowed `
    --version-file build\version_info.txt `
    --name XRD_Checker `
    --icon src\xrdcheck\data\icon.ico `
    --collect-data xrdcheck `
    --exclude-module tkinter --exclude-module pytest --exclude-module pytestqt `
    --distpath dist --workpath build `
    packaging\xrdcheck_gui.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패" }

Copy-Item README.md dist\XRD_Checker\README.md -Force
Copy-Item CHANGELOG.md dist\XRD_Checker\CHANGELOG.md -Force

$zip = "dist\XRD_Checker_v$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path dist\XRD_Checker -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  XRD_Checker_v$version.zip" | Out-File "$zip.sha256" -Encoding ascii
Write-Host "완료: $zip"
Write-Host "SHA256: $hash"
