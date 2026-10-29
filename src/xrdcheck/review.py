"""사용자 검토(판정 맞음/틀림) 기록과 검토 추천.

- 기록: %APPDATA%\\xrdcheck\\reviews.json. 키는 파일 내용 해시(SHA1 앞 16자리) — 파일을 옮기거나 이름을 바꿔도 이어진다
  (tools/survey.py의 sha1 열과 같은 값).
- 검토 추천: 판정이 경계에 있거나 근거가 약해 사람이 한 번 보면 좋은 시료와 그 이유(review_hints).
- 혼동표: 사용자 판정(정답) × 프로그램 판정으로 정확도를 본다(confusion).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from xrdcheck import __version__
from xrdcheck.model import AnalysisResult, Verdict

REVIEW_FILE = "reviews.json"
VERDICTS = [v.value for v in Verdict]


def file_key(path: str | Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


def result_file_key(r: AnalysisResult) -> str:
    """분석 결과의 파일 키(한 번 계산해 pattern.meta에 둔다)."""
    key = r.pattern.meta.get("sha1")
    if not key:
        key = r.pattern.meta["sha1"] = file_key(r.pattern.source_path)
    return key


class ReviewStore:
    def __init__(self, directory: str | Path):
        self.path = Path(directory) / REVIEW_FILE
        self.data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8")).get("reviews", {})
            except (OSError, json.JSONDecodeError):
                backup = self.path.with_suffix(".broken.json")  # 깨진 파일은 덮어쓰기 전에 남겨 둔다
                self.path.replace(backup)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "reviews": self.data}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, r: AnalysisResult) -> dict | None:
        return self.data.get(result_file_key(r))

    def set(self, r: AnalysisResult, user_verdict: str, memo: str | None = None) -> dict:
        if user_verdict not in VERDICTS:
            raise ValueError(f"알 수 없는 판정: {user_verdict}")
        key = result_file_key(r)
        old = self.data.get(key, {})
        entry = {
            "file": r.pattern.source_path.name,
            "path": str(r.pattern.source_path),
            "user_verdict": user_verdict,
            "program_verdict": r.verdict.value,  # 검토할 때의 프로그램 판정
            "program_version": __version__,
            "nano": (r.nano or {}).get("label", ""),
            "memo": old.get("memo", "") if memo is None else memo,
            "reviewed_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        self.data[key] = entry
        self.save()
        return entry

    def set_memo(self, r: AnalysisResult, memo: str) -> None:
        entry = self.get(r)
        if entry is None:
            raise KeyError("판정을 먼저 표시하세요.")
        entry["memo"] = memo
        self.save()

    def remove(self, r: AnalysisResult) -> None:
        if self.data.pop(result_file_key(r), None) is not None:
            self.save()


def status_text(r: AnalysisResult, entry: dict | None, hints: list[str]) -> str:
    """목록 '검토' 칸: ✓ 맞음 / ✗ → (사용자 판정) / 추천 / 빈칸."""
    if entry:
        return "✓ 맞음" if entry["user_verdict"] == r.verdict.value else f"✗ → {entry['user_verdict']}"
    return "추천" if hints else ""


def review_hints(r: AnalysisResult) -> list[str]:
    """사람이 확인하면 판정 정확도에 도움이 되는 이유 목록(없으면 빈 목록)."""
    out: list[str] = []
    s = r.settings
    if r.halo is None:
        return ["판정 불가 — 파일·측정 상태 확인"]
    v = r.verdict
    counted = r.counted_peaks
    if r.z_max is not None and s["z_suspect"] <= r.z_max < s["z_detect"] + 1.0:
        out.append(f"검출 기준 경계(z최대 {r.z_max:.1f}, 기준 {s['z_suspect']:g}/{s['z_detect']:g})")
    unmatched = [p for p in counted if p.significant and not p.accepted_match]
    single65 = [p for p in unmatched if 64.5 <= p.two_theta <= 66.0 and len([q for q in counted if q.significant]) == 1]
    if single65:
        out.append(f"{single65[0].two_theta:.2f}° 단일 피크 — 시료 홀더(Al(220) 65.1°) 또는 배향된 α-Fe(200)인지 확인")
    elif unmatched and not any(p.significant and p.accepted_match for p in counted):
        # 매칭된 피크가 하나도 없어 판정이 미매칭 피크에만 기대는 경우(이미 상이 확인된 시료의 추가 피크는 판정을 바꾸지 않음)
        out.append("상과 매칭되지 않은 검출 피크: " + ", ".join(f"{p.two_theta:.2f}°" for p in unmatched[:4]))
    if r.nano:
        cp = r.nano.get("secondary_peaks") or []
        if cp:
            out.append("주 halo 위 2차 상(붕화물·fcc 등) 피크: " + ", ".join(f"{t:.2f}° {m}" for t, m in cp[:3]))
        size = r.nano.get("size")
        if size and size.get("size_nm"):
            d = size["size_nm"]
            lo, hi = s["nanocrystal"]["size_range_nm"]
            err = size.get("size_err_nm") or 0
            # 경계(10·90 nm)가 D ± 2σ 안에 있거나 D가 경계의 ±10% 안 → 판정이 쉽게 뒤집힐 수 있음
            edge = sorted((b for b in (lo, hi) if abs(d - b) <= max(2 * err, 0.1 * b)), key=lambda b: abs(d - b))
            if edge:
                out.append(f"결정립 크기 {d:.0f} ± {err:.0f} nm — 나노결정 범위 경계({edge[0]:g} nm) 근처")
    if v == Verdict.SUSPECT and not out:
        out.append("결정상 의심 — 그래프로 확인")
    if r.halo.chi2_red > s["chi2_red_warn"]:
        out.append(f"모델 적합도 낮음(χ²red {r.halo.chi2_red:.1f})")
    if any("준비되지 않아" in w for w in r.warnings):
        out.append(f"{r.alloy_system} — 판정 기준 미준비")
    return out


def confusion(store: ReviewStore, results: list[AnalysisResult] | None = None) -> dict:
    """혼동표. results가 있으면 그 시료들의 '현재' 프로그램 판정으로, 없으면 검토 당시 판정으로 센다.

    반환: {"matrix": {사용자 판정: {프로그램 판정: 개수}}, "n", "correct", "accuracy", "disagree": [(파일, 프로그램, 사용자, 메모)]}
    """
    pairs = []
    if results is not None:
        for r in results:
            e = store.get(r)
            if e:
                pairs.append((e["file"], r.verdict.value, e["user_verdict"], e.get("memo", "")))
    else:
        pairs = [(e["file"], e["program_verdict"], e["user_verdict"], e.get("memo", "")) for e in store.data.values()]
    matrix = {u: {p: 0 for p in VERDICTS} for u in VERDICTS}
    for _, prog, user, _ in pairs:
        matrix[user][prog] += 1
    correct = sum(prog == user for _, prog, user, _ in pairs)
    return {"matrix": matrix, "n": len(pairs), "correct": correct,
            "accuracy": correct / len(pairs) if pairs else None,
            "disagree": [p for p in pairs if p[1] != p[2]]}
