"""자동 업데이트: 버전 비교, 공유 폴더 출처, SHA256 검증, 압축 풀기, 파일 교체·되돌리기, 화면 연결."""

import hashlib
import zipfile

import pytest

from xrdcheck import __version__, updater


def _make_release(folder, version, files=None, sha_ok=True, with_sha=True):
    """folder에 XRD_Checker_v<버전>.zip(+ .sha256)을 만든다."""
    files = files or {"XRD_Checker/XRD_Checker.exe": b"new exe", "XRD_Checker/_internal/lib.txt": b"new lib"}
    zp = folder / f"XRD_Checker_v{version}.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    if with_sha:
        h = hashlib.sha256(zp.read_bytes()).hexdigest() if sha_ok else "0" * 64
        (folder / (zp.name + ".sha256")).write_text(f"{h}  {zp.name}\n", encoding="ascii")
    return zp


@pytest.fixture(autouse=True)
def _update_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XRDCHECK_UPDATE_DIR", str(tmp_path / "upd"))


def test_version_compare():
    assert updater.is_newer("0.7.0", "0.6.0")
    assert updater.is_newer("v0.10.0", "0.9.9")
    assert updater.is_newer("1.0", "0.9.9")
    assert not updater.is_newer("0.6.0", "0.6.0")
    assert not updater.is_newer("0.6", "0.6.0")
    assert not updater.is_newer("0.5.9", "0.6.0")


def test_config_default_and_user_override(tmp_path):
    cfg = updater.load_config(tmp_path)
    assert cfg["github_repo"] and cfg["folder"] == ""
    (tmp_path / "update.json").write_text('{"folder": "\\\\\\\\NAS\\\\x", "unknown": 1}', encoding="utf-8")
    cfg = updater.load_config(tmp_path)
    assert cfg["folder"] == "\\\\NAS\\x" and "unknown" not in cfg
    assert updater.source_label(cfg).startswith("공유 폴더")


def test_folder_source_picks_highest(tmp_path):
    rel_dir = tmp_path / "rel"
    rel_dir.mkdir()
    _make_release(rel_dir, "0.9.0")
    _make_release(rel_dir, "0.10.0")
    (rel_dir / "RELEASE_NOTES_v0.10.0.md").write_text("### 새 기능\n- 시험", encoding="utf-8")
    rel = updater.check({"folder": str(rel_dir), "github_repo": ""}, current="0.6.0")
    assert rel.version == "0.10.0" and "시험" in rel.notes and rel.sha256_url
    assert updater.check({"folder": str(rel_dir), "github_repo": ""}, current="0.10.0") is None


def test_missing_folder_is_error(tmp_path):
    with pytest.raises(updater.UpdateError):
        updater.check({"folder": str(tmp_path / "없음"), "github_repo": ""})


def test_prepare_verifies_sha_and_extracts(tmp_path):
    rel_dir = tmp_path / "rel"
    rel_dir.mkdir()
    _make_release(rel_dir, "9.0.0")
    rel = updater.latest_from_folder(rel_dir)
    seen = []
    app = updater.prepare(rel, lambda d, t: seen.append((d, t)))
    assert (app / "XRD_Checker.exe").read_bytes() == b"new exe"
    assert seen and seen[-1][0] == seen[-1][1]


@pytest.mark.parametrize("kind", ["bad_sha", "no_sha"])
def test_prepare_refuses_unverified(tmp_path, kind):
    rel_dir = tmp_path / "rel"
    rel_dir.mkdir()
    _make_release(rel_dir, "9.0.0", sha_ok=kind != "bad_sha", with_sha=kind != "no_sha")
    rel = updater.latest_from_folder(rel_dir)
    with pytest.raises(updater.UpdateError, match="SHA256"):
        updater.prepare(rel)
    assert not list((tmp_path / "upd").rglob("*.exe"))  # 검증 실패 파일은 남기지 않음


def test_extract_rejects_path_traversal(tmp_path):
    zp = _make_release(tmp_path, "9.0.0", files={"../evil.txt": b"x", "XRD_Checker/XRD_Checker.exe": b"e"})
    with pytest.raises(updater.UpdateError, match="잘못된 경로"):
        updater.extract(zp, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def _tree(src, files):
    for name, data in files.items():
        p = src / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def test_replace_files_keeps_user_files(tmp_path):
    src, dst = tmp_path / "new", tmp_path / "inst"
    _tree(src, {"XRD_Checker.exe": b"new", "_internal/a.dll": b"new a"})
    _tree(dst, {"XRD_Checker.exe": b"old", "_internal/a.dll": b"old a", "_internal/old_only.dll": b"o",
                "내 결과.xlsx": b"user"})
    updater.replace_files(src, dst, tmp_path / "backup")
    assert (dst / "XRD_Checker.exe").read_bytes() == b"new"
    assert not (dst / "_internal/old_only.dll").exists()  # 옛 라이브러리는 남기지 않음
    assert (dst / "내 결과.xlsx").read_bytes() == b"user"  # 사용자 파일은 그대로
    assert (tmp_path / "backup/XRD_Checker.exe").read_bytes() == b"old"


def test_replace_files_rolls_back_on_failure(tmp_path, monkeypatch):
    src, dst = tmp_path / "new", tmp_path / "inst"
    _tree(src, {"XRD_Checker.exe": b"new", "_internal/a.dll": b"new a"})
    _tree(dst, {"XRD_Checker.exe": b"old", "_internal/a.dll": b"old a"})

    def boom(*a, **k):
        raise OSError("디스크 가득 참")

    monkeypatch.setattr(updater.shutil, "copytree", boom)
    with pytest.raises(OSError):
        updater.replace_files(src, dst, tmp_path / "backup")
    assert (dst / "XRD_Checker.exe").read_bytes() == b"old"
    assert (dst / "_internal/a.dll").read_bytes() == b"old a"


def test_dev_environment_does_not_self_update():
    ok, why = updater.can_self_update()
    assert not ok and "개발 환경" in why


def test_gui_check_finds_folder_release(qtbot, tmp_path):
    from xrdcheck.gui.main_window import MainWindow

    rel_dir = tmp_path / "rel"
    rel_dir.mkdir()
    major = int(__version__.split(".")[0]) + 1
    _make_release(rel_dir, f"{major}.0.0")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "update.json").write_text('{"folder": "%s"}' % str(rel_dir).replace("\\", "\\\\"), encoding="utf-8")
    w = MainWindow(config_dir=cfg, show_dialogs=False)
    qtbot.addWidget(w)
    worker = w.check_updates(silent=False)
    qtbot.waitUntil(lambda: not worker.isRunning() and w.available_release is not None, timeout=10000)
    assert w.available_release.version == f"{major}.0.0"
    assert "새 버전" in w.status.text()


def test_gui_check_failure_is_quiet(qtbot, tmp_path):
    from xrdcheck.gui.main_window import MainWindow

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "update.json").write_text('{"folder": "%s"}' % str(tmp_path / "없음").replace("\\", "\\\\"),
                                     encoding="utf-8")
    w = MainWindow(config_dir=cfg, show_dialogs=False)
    qtbot.addWidget(w)
    worker = w.check_updates(silent=True)
    qtbot.waitUntil(lambda: not worker.isRunning() and w.update_error is not None, timeout=10000)
    assert w.available_release is None
