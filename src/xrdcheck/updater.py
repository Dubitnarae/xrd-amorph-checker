"""자동 업데이트: 새 버전 확인 → 내려받기(SHA256 확인) → 프로그램을 닫고 폴더의 파일을 바꾼 뒤 다시 실행.

업데이트 출처(둘 중 하나)
- GitHub 릴리스: `https://api.github.com/repos/<저장소>/releases/latest`. 토큰 없이 읽으므로 **공개 저장소**여야 한다.
- 공유 폴더(NAS 등): 폴더 안의 `XRD_Checker_v<버전>.zip` + `.zip.sha256`(+ `RELEASE_NOTES_v<버전>.md`) 중 가장 높은 버전.
기본값은 패키지 안 `data/update.json`, 사용자가 바꾼 값은 `%APPDATA%\\xrdcheck\\update.json`(folder를 채우면 폴더 우선).

설치 순서(배포판 exe에서만)
1. 내려받은 zip의 SHA256을 `.sha256` 파일과 비교 — 다르거나 `.sha256`이 없으면 설치하지 않는다.
2. 임시 폴더(%LOCALAPPDATA%\\xrdcheck\\update)에 압축을 풀고, **새 버전 exe**를 `--apply-update`로 실행한 뒤 지금 프로그램은 끝낸다.
3. 새 exe가 옛 프로그램이 끝나기를 기다렸다가, 설치 폴더의 프로그램 파일(exe·_internal·README·CHANGELOG)만
   백업 폴더로 옮기고 새 파일을 복사한다. 실패하면 백업을 되돌린다. 설치 폴더의 다른 파일(사용자 파일)은 건드리지 않는다.
4. 바뀐 설치 폴더의 exe를 다시 실행한다. 다음 실행 때 임시·백업 폴더를 지운다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from xrdcheck import __version__

APP_DIR_NAME = "XRD_Checker"  # zip 안의 폴더 이름 = build.ps1 --name
EXE_NAME = APP_DIR_NAME + ".exe"
ZIP_RE = re.compile(r"^XRD_Checker_v(\d+(?:\.\d+)*)\.zip$", re.I)
APPLY_FLAG = "--apply-update"
USER_AGENT = f"xrdcheck/{__version__}"


@dataclass
class Release:
    version: str
    zip_name: str
    zip_url: str  # http(s) 주소 또는 로컬 경로
    sha256_url: str | None
    notes: str = ""
    page_url: str = ""


class UpdateError(Exception):
    """사용자에게 그대로 보여 줄 한국어 문구를 담는다."""


# ------------------------------------------------------------ 설정·버전
def version_tuple(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.lstrip("vV"))
    return tuple(int(n) for n in nums) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = version_tuple(candidate), version_tuple(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def update_root() -> Path:
    """임시 파일(내려받은 zip, 푼 폴더, 백업) 위치."""
    if env := os.environ.get("XRDCHECK_UPDATE_DIR"):
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "xrdcheck" / "update"


def load_config(config_dir: str | Path | None = None) -> dict:
    cfg = json.loads(resources.files("xrdcheck").joinpath("data/update.json").read_text(encoding="utf-8"))
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    if config_dir is not None:
        p = Path(config_dir) / "update.json"
        if p.exists():
            try:
                user = json.loads(p.read_text(encoding="utf-8"))
                cfg.update({k: v for k, v in user.items() if k in cfg})
            except (OSError, json.JSONDecodeError):
                pass  # 깨진 사용자 설정은 무시
    return cfg


def source_label(cfg: dict) -> str:
    return f"공유 폴더 {cfg['folder']}" if cfg.get("folder") else f"GitHub {cfg.get('github_repo')}"


# ------------------------------------------------------------ 새 버전 찾기
def _get(url: str, timeout: float, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_from_github(repo: str, timeout: float = 8) -> Release | None:
    import urllib.error

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        data = json.loads(_get(url, timeout, "application/vnd.github+json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError(f"GitHub 저장소 {repo}의 릴리스를 찾을 수 없습니다(비공개 저장소이거나 릴리스가 없음).") from e
        raise UpdateError(f"GitHub 응답 오류 {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"업데이트 서버에 연결할 수 없습니다: {getattr(e, 'reason', e)}") from e
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    for name, link in assets.items():
        m = ZIP_RE.match(name)
        if m:
            return Release(m.group(1), name, link, assets.get(name + ".sha256"),
                           data.get("body") or "", data.get("html_url") or "")
    return None


def latest_from_folder(folder: str | Path) -> Release | None:
    folder = Path(folder)
    if not folder.is_dir():
        raise UpdateError(f"업데이트 폴더에 접근할 수 없습니다: {folder}")
    found = [(version_tuple(m.group(1)), m.group(1), p) for p in folder.iterdir() if (m := ZIP_RE.match(p.name))]
    if not found:
        return None
    _, ver, zp = max(found)
    sha = zp.with_name(zp.name + ".sha256")
    notes_p = folder / f"RELEASE_NOTES_v{ver}.md"
    notes = notes_p.read_text(encoding="utf-8", errors="replace") if notes_p.exists() else ""
    return Release(ver, zp.name, str(zp), str(sha) if sha.exists() else None, notes, str(folder))


def check(cfg: dict, current: str = __version__) -> Release | None:
    """현재보다 새 버전이 있으면 Release, 없으면 None. 연결 실패는 UpdateError."""
    rel = latest_from_folder(cfg["folder"]) if cfg.get("folder") else latest_from_github(cfg["github_repo"])
    return rel if rel and is_newer(rel.version, current) else None


# ------------------------------------------------------------ 내려받기·검증·풀기
def _read(src: str, timeout: float = 30) -> bytes:
    if re.match(r"^https?://", src, re.I):
        return _get(src, timeout)
    return Path(src).read_bytes()


def download(rel: Release, dest_dir: Path, progress=None) -> Path:
    """zip을 dest_dir에 받고 SHA256을 확인한다. progress(받은 바이트, 전체 바이트)."""
    if not rel.sha256_url:
        raise UpdateError("릴리스에 SHA256 파일이 없어 설치하지 않습니다.")
    expected = _read(rel.sha256_url).decode("ascii", "replace").split()[0].strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError("SHA256 파일 형식이 잘못되었습니다.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / rel.zip_name
    h = hashlib.sha256()
    try:
        if re.match(r"^https?://", rel.zip_url, re.I):
            req = urllib.request.Request(rel.zip_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r, open(out, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while chunk := r.read(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        else:
            total = Path(rel.zip_url).stat().st_size
            done = 0
            with open(rel.zip_url, "rb") as src, open(out, "wb") as f:
                while chunk := src.read(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except OSError as e:
        out.unlink(missing_ok=True)
        raise UpdateError(f"내려받기 실패: {e}") from e
    if h.hexdigest() != expected:
        out.unlink(missing_ok=True)
        raise UpdateError("내려받은 파일의 SHA256이 맞지 않습니다(파일 손상 또는 변조). 설치하지 않습니다.")
    return out


def extract(zip_path: Path, dest_dir: Path) -> Path:
    """zip을 풀고 새 버전 폴더(…/XRD_Checker)를 돌려준다. 폴더 밖으로 나가는 경로가 있으면 거부."""
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    root = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = (dest_dir / name).resolve()
            if root != target and root not in target.parents:
                raise UpdateError(f"압축 파일에 잘못된 경로가 있습니다: {name}")
        z.extractall(dest_dir)
    app = dest_dir / APP_DIR_NAME
    if not (app / EXE_NAME).is_file():
        raise UpdateError(f"압축 파일에 {APP_DIR_NAME}\\{EXE_NAME}이 없습니다.")
    return app


# ------------------------------------------------------------ 설치
def install_dir() -> Path | None:
    """배포판(exe)으로 실행 중이면 설치 폴더, 개발 환경이면 None."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def can_self_update() -> tuple[bool, str]:
    d = install_dir()
    if d is None:
        return False, "개발 환경(python)에서는 자동 설치하지 않습니다. 릴리스 페이지에서 받으세요."
    probe = d / ".xrdcheck_write_test"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return False, f"설치 폴더에 쓸 권한이 없습니다: {d}\n압축을 쓰기 가능한 폴더(예: 문서)에 풀어 쓰면 자동 업데이트가 됩니다."
    return True, ""


def prepare(rel: Release, progress=None) -> Path:
    """내려받고 풀어서 새 버전 폴더를 돌려준다."""
    work = update_root() / f"v{rel.version}"
    zp = download(rel, work, progress)
    app = extract(zp, work / "app")
    zp.unlink(missing_ok=True)
    return app


def launch_apply(new_app: Path, target: Path) -> None:
    """새 버전 exe를 설치 모드로 실행한다. 호출한 쪽은 곧바로 프로그램을 끝내야 한다."""
    args = [str(new_app / EXE_NAME), APPLY_FLAG, str(target), str(os.getpid())]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, cwd=str(new_app), creationflags=flags, close_fds=True)


def _wait_pid(pid: int, timeout_s: float) -> None:
    if os.name != "nt" or pid <= 0:
        return
    import ctypes

    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if h:
        k32.WaitForSingleObject(h, int(timeout_s * 1000))
        k32.CloseHandle(h)


def _retry(fn, tries: int = 40, delay: float = 0.5):
    for k in range(tries):
        try:
            return fn()
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(delay)


def replace_files(src: Path, dst: Path, backup: Path) -> None:
    """dst의 프로그램 파일(src에 있는 이름들)을 backup으로 옮기고 src를 복사한다. 실패하면 되돌린다."""
    names = [p.name for p in src.iterdir()]
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True)
    moved: list[str] = []
    copied: list[str] = []
    try:
        for n in names:
            if (dst / n).exists():
                _retry(lambda n=n: shutil.move(str(dst / n), str(backup / n)))
                moved.append(n)
        for n in names:
            copied.append(n)  # 복사 도중 실패해도 지우도록 먼저 기록
            s = src / n
            if s.is_dir():
                shutil.copytree(s, dst / n)
            else:
                shutil.copy2(s, dst / n)
    except Exception:
        for n in copied:  # 새로 복사한 것을 지우고 백업을 되돌린다
            p = dst / n
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink(missing_ok=True)
        for n in moved:
            shutil.move(str(backup / n), str(dst / n))
        raise


def _log(msg: str) -> None:
    try:
        update_root().mkdir(parents=True, exist_ok=True)
        with open(update_root() / "update.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _message_box(text: str) -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "XRD 비정질 판정 도우미 — 업데이트", 0x10)


def apply_update_main(argv: list[str]) -> int:
    """`XRD_Checker.exe --apply-update <설치 폴더> <옛 프로그램 PID>` — 새 버전 exe(임시 폴더)에서 실행된다."""
    try:
        target, pid = Path(argv[0]), int(argv[1])
    except (IndexError, ValueError):
        return 2
    src = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(argv[2])
    _log(f"설치 시작 v{__version__}: {src} → {target}")
    _wait_pid(pid, 60)
    try:
        replace_files(src, target, update_root() / "backup")
    except Exception as e:
        _log(f"설치 실패: {e!r}")
        _message_box(f"업데이트를 설치하지 못했습니다. 이전 버전은 그대로입니다.\n\n{e}\n\n기록: {update_root() / 'update.log'}")
        exe = target / EXE_NAME
        if exe.is_file():
            subprocess.Popen([str(exe)], cwd=str(target), close_fds=True)
        return 1
    _log("설치 완료")
    subprocess.Popen([str(target / EXE_NAME)], cwd=str(target), close_fds=True)
    return 0


def cleanup() -> None:
    """지난 업데이트의 임시·백업 폴더를 지운다(프로그램 시작 때). 쓰는 중이면 다음에 다시."""
    root = update_root()
    if not root.is_dir() or getattr(sys, "frozen", False) and root in Path(sys.executable).resolve().parents:
        return  # 지금 임시 폴더의 exe로 설치 중
    for p in root.iterdir():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
