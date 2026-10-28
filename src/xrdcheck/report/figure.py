"""분석 그래프(matplotlib). 화면과 보고서가 같은 그림을 쓴다."""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
from matplotlib import font_manager
from matplotlib.figure import Figure

from xrdcheck.model import AnalysisResult

FONT = "Malgun Gothic"
VERDICT_COLORS = {"비정질": "#2e7d32", "결정상 의심": "#ef6c00", "결정상 검출": "#c62828", "나노결정상 후보": "#6a1b9a",
                  "판정 불가": "#616161"}
COMPONENT_STYLES = {"배경": ("#8d6e63", ":"), "주 halo": ("#1565c0", "--"), "제2 halo": ("#6a1b9a", "--")}


def font_family() -> tuple[str, str | None]:
    """(글꼴 이름, 경고 문구 또는 None)."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    if FONT in names:
        return FONT, None
    return "sans-serif", f"'{FONT}' 글꼴이 없어 기본 글꼴로 그렸습니다 — 한글이 깨질 수 있습니다."


def _rc() -> dict:
    return {"font.family": font_family()[0], "axes.unicode_minus": False}


def _set_yscale(ax, yscale: str) -> None:
    if yscale == "sqrt":
        ax.set_yscale("function", functions=(lambda v: np.sqrt(np.maximum(v, 0)), lambda v: np.square(v)))
    elif yscale == "log":
        ax.set_yscale("log")
    if yscale in ("sqrt", "linear"):
        ax.set_ylim(bottom=0)


def _prepare(fig: Figure | None, figsize) -> Figure:
    """새 Figure를 만들거나(보고서), 화면 캔버스의 Figure를 비워서 다시 쓴다(GUI)."""
    if fig is None:
        return Figure(figsize=figsize, layout="constrained")
    fig.clear()
    fig.set_layout_engine("constrained")
    return fig


def make_figure(r: AnalysisResult, yscale: str = "sqrt", show_phases: bool = True,
                figsize=(10, 6.5), fig: Figure | None = None) -> Figure:
    import matplotlib

    with matplotlib.rc_context(_rc()):
        fig = _prepare(fig, figsize)
        ax, axz = fig.subplots(2, 1, sharex=True, height_ratios=[3, 1])
        p = r.pattern
        x, y = p.two_theta, p.counts
        ax.plot(x, y, color="#9e9e9e", lw=0.7, label="측정")
        if r.halo is not None:
            for name, comp in r.halo.components.items():
                color, ls = COMPONENT_STYLES.get(name, ("#455a64", "--"))
                ax.plot(x, comp, color=color, ls=ls, lw=1.0, label=name)
            ax.plot(x, r.halo.mu, color="#d32f2f", lw=1.2, label="모델")
            if r.fit_mask is not None and not r.fit_mask.all():
                for a in (ax, axz):
                    a.fill_between(x, 0, 1, where=~r.fit_mask, transform=a.get_xaxis_transform(),
                                   color="#ffe082", alpha=0.35, lw=0)
        if show_phases and r.phase_lines:
            matched = {m for pk in r.peaks for m in pk.matches}
            for ln in r.phase_lines:
                hit = ln["label"] in matched
                if ln.get("two_theta_max", ln["two_theta"]) - ln.get("two_theta_min", ln["two_theta"]) > 0.05:
                    ax.axvspan(ln["two_theta_min"], ln["two_theta_max"], color="#c62828" if hit else "#90a4ae",
                               alpha=0.12 if hit else 0.06, lw=0)
                    if not hit:
                        continue
                ax.axvline(ln["two_theta"], color="#c62828" if hit else "#90a4ae", lw=0.8 if hit else 0.5,
                           ls="-" if hit else ":", alpha=0.9 if hit else 0.6)
                if hit:
                    ax.text(ln["two_theta"], 1.0, ln["label"], rotation=90, va="top", ha="right", fontsize=7,
                            color="#c62828", transform=ax.get_xaxis_transform())
        for pk in r.peaks:
            i = int(np.argmin(np.abs(x - pk.two_theta)))
            color = "#c62828" if pk.significant else "#ef6c00"
            face = "none" if not pk.counted else color
            ax.plot(pk.two_theta, y[i] * 1.08 + 2, marker="v", ms=7, color=color, mfc=face, ls="none")
        _set_yscale(ax, yscale)
        ax.set_ylabel("강도 (counts)")
        ax.legend(loc="upper right", fontsize=8, ncols=2)
        title = f"{p.sample_name}   [{r.verdict.value}]"
        ax.set_title(title, loc="left", fontsize=11, color=VERDICT_COLORS.get(r.verdict.value, "black"),
                     fontweight="bold")
        fig.suptitle("\n".join(textwrap.wrap(r.sentence, 95)), fontsize=8, x=0.01, ha="left", color="#37474f")

        if r.z is not None:
            s = r.settings
            axz.plot(x, r.z, color="#37474f", lw=0.7)
            axz.axhline(s["z_detect"], color="#c62828", lw=0.8, ls="--", label=f"검출 z={s['z_detect']:g}")
            axz.axhline(s["z_suspect"], color="#ef6c00", lw=0.8, ls=":", label=f"의심 z={s['z_suspect']:g}")
            axz.legend(loc="upper right", fontsize=7, ncols=2)
        axz.set_ylabel("z")
        axz.set_xlabel("2θ (°)")
        axz.set_xlim(x[0], x[-1])
        fig.text(0.995, 0.002, f"xrdcheck v{r.version}", ha="right", va="bottom", fontsize=6, color="#9e9e9e")
    return fig


def halo_height(r: AnalysisResult) -> float:
    """정규화 기준: 주 halo 성분의 최대값(없으면 최대 counts)."""
    if r.halo is not None:
        return float(np.max(r.halo.components["주 halo"])) or 1.0
    return max(r.pattern.max_counts, 1.0)


def make_compare_figure(results: list[AnalysisResult], mode: str = "overlay", normalize: bool = True,
                        yscale: str = "linear", figsize=(10, 6.5), fig: Figure | None = None) -> Figure:
    """여러 시료 비교. mode = "overlay"(겹치기) | "stack"(세로로 나눠 보기). normalize면 halo 높이로 나눈다."""
    import matplotlib

    with matplotlib.rc_context(_rc()):
        fig = _prepare(fig, figsize)
        n = max(len(results), 1)
        axes = [fig.add_subplot(1, 1, 1)] if mode == "overlay" else list(fig.subplots(n, 1, sharex=True, squeeze=False)[:, 0])
        colors = matplotlib.colormaps["tab10"]
        ylabel = "강도 / halo 높이" if normalize else "강도 (counts)"
        for i, r in enumerate(results):
            ax = axes[0] if mode == "overlay" else axes[i]
            scale = halo_height(r) if normalize else 1.0
            x = r.pattern.two_theta
            label = f"{r.pattern.sample_name} [{r.verdict.value}]"
            ax.plot(x, r.pattern.counts / scale, color=colors(i % 10), lw=0.7, label=label)
            for pk in r.counted_peaks:
                j = int(np.argmin(np.abs(x - pk.two_theta)))
                ax.plot(pk.two_theta, r.pattern.counts[j] / scale * 1.05, marker="v", ms=6, ls="none",
                        color=colors(i % 10), mfc=colors(i % 10) if pk.significant else "none")
            if mode == "stack":
                ax.legend(loc="upper right", fontsize=8)
                ax.set_ylabel(ylabel if n == 1 else "")
        for ax in axes:
            _set_yscale(ax, yscale)
        if mode == "overlay":
            axes[0].legend(loc="upper right", fontsize=8)
            axes[0].set_ylabel(ylabel)
        else:
            fig.supylabel(ylabel, fontsize=10)
        axes[-1].set_xlabel("2θ (°)")
        if results:
            axes[-1].set_xlim(min(r.pattern.two_theta[0] for r in results), max(r.pattern.two_theta[-1] for r in results))
        fig.suptitle(f"시료 비교 ({len(results)}개{', halo 높이로 정규화' if normalize else ''})", fontsize=10,
                     x=0.01, ha="left")
    return fig


def save_figure(fig: Figure, path: str | Path, dpi: int = 300) -> Path:
    import matplotlib

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context(_rc()):
        fig.savefig(path, dpi=dpi)
    return path


def save_png(r: AnalysisResult, path: str | Path, yscale: str = "sqrt", dpi: int = 300) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib

    with matplotlib.rc_context(_rc()):  # 저장할 때도 글꼴·마이너스 설정이 적용되도록
        fig = make_figure(r, yscale=yscale)
        fig.savefig(path, dpi=dpi)
    return path
