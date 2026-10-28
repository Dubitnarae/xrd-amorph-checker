# XRD 비정질 판정 도우미 — 배포(GitHub 릴리스 또는 공유 폴더)
#   사용: 먼저 .\build.ps1 → dist\RELEASE_NOTES_v<버전>.md 작성 → 아래 중 하나
#     .\publish.ps1                       GitHub: (처음이면) 비공개 저장소 만들기 → master 푸시 → 태그 → 릴리스
#     .\publish.ps1 -Public               위와 같지만 저장소를 공개로 만든다(프로그램 안 자동 업데이트가 GitHub를 쓰려면 공개 필요)
#     .\publish.ps1 -Folder \\NAS\공유\XRD_Checker   공유 폴더에 zip·sha256·노트만 복사(자동 업데이트 folder 출처용)
#   자동 업데이트는 XRD_Checker_v<버전>.zip과 .zip.sha256을 읽는다 — 두 파일 이름을 바꾸지 말 것.
#   주의: local-full-history 브랜치(실측 데이터가 든 옛 기록)는 절대 푸시하지 않는다. 이 스크립트는 master와 태그만 올린다.
param([switch]$Public, [string]$Folder = "")
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$repo = "Dubitnarae/xrd-amorph-checker"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) { $gh = "gh" }
$version = (& .\.venv\Scripts\python.exe -c "import xrdcheck; print(xrdcheck.__version__)").Trim()
$tag = "v$version"
$zip = "dist\XRD_Checker_v$version.zip"
$notes = "dist\RELEASE_NOTES_v$version.md"
foreach ($f in @($zip, "$zip.sha256", $notes)) { if (-not (Test-Path $f)) { throw "없음: $f (build.ps1과 릴리스 노트를 먼저)" } }
if ($Folder) {
    if (-not (Test-Path $Folder)) { New-Item -ItemType Directory -Path $Folder | Out-Null }
    foreach ($f in @($zip, "$zip.sha256", $notes)) { Copy-Item $f $Folder -Force }
    Write-Host "완료: $Folder 에 v$version 복사"
    exit 0
}
if (git status --porcelain) { throw "커밋하지 않은 변경이 있습니다. 먼저 커밋하세요." }
if ((git branch --show-current) -ne "master") { throw "master 브랜치에서 실행하세요." }

& $gh repo view $repo *> $null
if ($LASTEXITCODE -ne 0) {
    $vis = if ($Public) { "--public" } else { "--private" }
    & $gh repo create $repo $vis --description "XRD 비정질 판정 도우미"
    if ($LASTEXITCODE -ne 0) { throw "저장소 만들기 실패" }
}
elseif ($Public) {
    & $gh repo edit $repo --visibility public --accept-visibility-change-consequences
    if ($LASTEXITCODE -ne 0) { throw "공개 전환 실패" }
}
if (-not (git remote | Select-String -SimpleMatch "origin")) { git remote add origin "https://github.com/$repo.git" }
git push -u origin master
if ($LASTEXITCODE -ne 0) { throw "푸시 실패" }
if (-not (git tag -l $tag)) { git tag -a $tag -m "$tag" }
git push origin $tag
& $gh release create $tag $zip "$zip.sha256" --repo $repo --title "XRD 비정질 판정 도우미 $tag" --notes-file $notes --latest --verify-tag
if ($LASTEXITCODE -ne 0) { throw "릴리스 게시 실패" }
Write-Host "완료: https://github.com/$repo/releases/tag/$tag"
