"""명령줄 배치 처리.

    python -m xrdcheck analyze <파일|폴더> ... --out 결과.xlsx --png figs/ [--csv data/]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xrdcheck import __version__
from xrdcheck.io import SUPPORTED_SUFFIXES


def _fix_stdout() -> None:
    """파이프·리디렉션일 때 cp949로 못 쓰는 문자(—, Kα 등)로 죽지 않도록 UTF-8로 바꾼다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")


def collect_files(paths: list[str], recursive: bool = False) -> tuple[list[Path], list[str]]:
    """폴더는 지원 확장자 파일을 모으고, 같은 이름의 .xrdml이 있으면 .csv는 건너뛴다(같은 데이터)."""
    files: list[Path] = []
    notes: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            found = sorted(f for f in p.glob(pattern) if f.is_file() and f.suffix.lower() in SUPPORTED_SUFFIXES)
            found = [f for f in found if f.name.lower() not in ("readme.txt",)]
            files += found
        elif p.is_file():
            files.append(p)
        else:
            notes.append(f"찾을 수 없음: {raw}")
    xrdml_stems = {(f.parent, f.stem.lower()) for f in files if f.suffix.lower() == ".xrdml"}
    out = []
    for f in dict.fromkeys(files):
        if f.suffix.lower() == ".csv" and (f.parent, f.stem.lower()) in xrdml_stems:
            notes.append(f"건너뜀(같은 이름의 .xrdml 사용): {f.name}")
            continue
        out.append(f)
    return out, notes


def cmd_analyze(args) -> int:
    from xrdcheck.analysis.pipeline import analyze_file
    from xrdcheck.analysis.phases import load_library
    from xrdcheck.settings import load_settings

    settings = load_settings(args.settings)
    library = load_library(args.phases)
    files, notes = collect_files(args.paths, args.recursive)
    for n in notes:
        print(n)
    if not files:
        print("분석할 파일이 없습니다.")
        return 1

    if args.png:
        from xrdcheck.report.figure import font_family

        if warn := font_family()[1]:
            print("경고:", warn)

    results, failed = [], 0
    for f in files:
        try:
            r = analyze_file(f, settings, library)
        except Exception as e:  # 한 파일이 실패해도 나머지는 계속
            failed += 1
            print(f"[오류] {f.name}: {e}")
            continue
        results.append(r)
        print(f"[{r.verdict.value}] {f.name}: {r.sentence}")
        for w in r.warnings:
            print(f"    경고: {w}")
        if args.png:
            from xrdcheck.report.figure import save_png

            save_png(r, Path(args.png) / f"{f.stem}.png", yscale=args.yscale)
        if args.csv:
            from xrdcheck.report.data_csv import write_processed_csv

            write_processed_csv(r, Path(args.csv) / f"{f.stem}_processed.csv")

    if args.out and results:
        from xrdcheck.report.excel import write_excel

        try:
            out = write_excel(results, args.out)
        except PermissionError:
            print(f"[오류] {args.out}에 쓸 수 없습니다 — Excel에서 열려 있으면 닫고 다시 실행하세요.")
            return 1
        print(f"Excel 저장: {out}")
    if args.png and results:
        print(f"그래프 저장: {Path(args.png)}")
    print(f"완료: {len(results)}개 분석, {failed}개 실패")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="xrdcheck", description=f"XRD 비정질 판정 도우미 v{__version__}")
    ap.add_argument("--version", action="version", version=f"xrdcheck {__version__}")
    sub = ap.add_subparsers(dest="command")

    a = sub.add_parser("analyze", help="파일·폴더를 분석해 판정 결과를 출력")
    a.add_argument("paths", nargs="+", help=".xrdml / .csv / .xy / .txt 파일 또는 폴더")
    a.add_argument("--out", help="Excel 보고서 경로(.xlsx)")
    a.add_argument("--png", help="그래프 PNG를 저장할 폴더")
    a.add_argument("--csv", help="처리 데이터 CSV를 저장할 폴더")
    a.add_argument("--yscale", choices=["sqrt", "linear", "log"], default="sqrt", help="그래프 y축(기본 sqrt)")
    a.add_argument("--settings", help="기본 설정을 덮어쓸 JSON 파일")
    a.add_argument("--phases", help="상 라이브러리 JSON 파일(기본: 내장)")
    a.add_argument("-r", "--recursive", action="store_true", help="하위 폴더까지 찾기")
    a.set_defaults(func=cmd_analyze)

    g = sub.add_parser("gui", help="화면 실행(Phase 3에서 구현)")
    g.set_defaults(func=lambda _a: print("GUI는 아직 구현되지 않았습니다(Phase 3).") or 1)
    return ap


def main(argv: list[str] | None = None) -> int:
    _fix_stdout()
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(args)
